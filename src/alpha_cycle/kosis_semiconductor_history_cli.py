"""Capture revision-sensitive KOSIS semiconductor history and derive diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.providers.kosis import KosisParameterQuery, KosisParameterRow, KosisReadOnlyClient

KOSIS_ORG_ID = "101"
INDEX_TABLE_ID = "DT_1F02001"
INDEX_TABLE_NAME = "시도/산업별 광공업생산지수(2020=100)"
CAPACITY_TABLE_ID = "DT_1F32001"
CAPACITY_TABLE_NAME = "제조업 생산능력 및 가동률지수(2020=100)"
DEFAULT_MONTHS = 180
MAX_MONTHS = 600
HEURISTIC_SPREAD_DEADBAND_PP = 1.0
DEFAULT_OUTPUT_ROOT = Path(
    "data/private/live-research/kosis-semiconductor-history"
)
LATEST_POINTER_NAME = "latest_kosis_semiconductor_history.json"


@dataclass(frozen=True)
class TableBinding:
    role: str
    table_id: str
    table_name: str
    object_codes: tuple[str, ...]
    classification_names: tuple[str, ...]


@dataclass(frozen=True)
class SeriesSpec:
    metric: str
    table_id: str
    table_name: str
    object_codes: tuple[str, ...]
    classification_names: tuple[str, ...]
    item_id: str
    item_name: str
    frequency: str = "M"


INDEX_BINDING = TableBinding(
    role="industry_production_shipment_inventory",
    table_id=INDEX_TABLE_ID,
    table_name=INDEX_TABLE_NAME,
    object_codes=("00", "C261"),
    classification_names=("전국", "반도체 제조업"),
)
CAPACITY_BINDING = TableBinding(
    role="capacity_utilization",
    table_id=CAPACITY_TABLE_ID,
    table_name=CAPACITY_TABLE_NAME,
    object_codes=("C261",),
    classification_names=("반도체 제조업",),
)
TABLE_BINDINGS = (INDEX_BINDING, CAPACITY_BINDING)

SERIES_SPECS = (
    SeriesSpec(
        "production_raw",
        INDEX_TABLE_ID,
        INDEX_TABLE_NAME,
        INDEX_BINDING.object_codes,
        INDEX_BINDING.classification_names,
        "T10",
        "생산지수(원지수)",
    ),
    SeriesSpec(
        "shipment_raw",
        INDEX_TABLE_ID,
        INDEX_TABLE_NAME,
        INDEX_BINDING.object_codes,
        INDEX_BINDING.classification_names,
        "T11",
        "생산자제품 출하지수(원지수)",
    ),
    SeriesSpec(
        "inventory_raw",
        INDEX_TABLE_ID,
        INDEX_TABLE_NAME,
        INDEX_BINDING.object_codes,
        INDEX_BINDING.classification_names,
        "T12",
        "생산자제품 재고지수(원지수)",
    ),
    SeriesSpec(
        "production_sa",
        INDEX_TABLE_ID,
        INDEX_TABLE_NAME,
        INDEX_BINDING.object_codes,
        INDEX_BINDING.classification_names,
        "T20",
        "생산지수(계절조정)",
    ),
    SeriesSpec(
        "shipment_sa",
        INDEX_TABLE_ID,
        INDEX_TABLE_NAME,
        INDEX_BINDING.object_codes,
        INDEX_BINDING.classification_names,
        "T21",
        "생산자제품 출하지수(계절조정)",
    ),
    SeriesSpec(
        "inventory_sa",
        INDEX_TABLE_ID,
        INDEX_TABLE_NAME,
        INDEX_BINDING.object_codes,
        INDEX_BINDING.classification_names,
        "T22",
        "생산자제품 재고지수(계절조정)",
    ),
    SeriesSpec(
        "capacity_raw",
        CAPACITY_TABLE_ID,
        CAPACITY_TABLE_NAME,
        CAPACITY_BINDING.object_codes,
        CAPACITY_BINDING.classification_names,
        "T10",
        "생산능력지수",
    ),
    SeriesSpec(
        "utilization_raw",
        CAPACITY_TABLE_ID,
        CAPACITY_TABLE_NAME,
        CAPACITY_BINDING.object_codes,
        CAPACITY_BINDING.classification_names,
        "T20",
        "가동률지수(원지수)",
    ),
    SeriesSpec(
        "utilization_sa",
        CAPACITY_TABLE_ID,
        CAPACITY_TABLE_NAME,
        CAPACITY_BINDING.object_codes,
        CAPACITY_BINDING.classification_names,
        "T30",
        "가동률지수(계절조정)",
    ),
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value: object, *, ensure_ascii: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=ensure_ascii, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _canonical_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _parse_numeric(value: str) -> float | None:
    cleaned = _canonical_text(value).replace(",", "")
    if cleaned.casefold() in {"", "-", "--", "…", "...", "na", "n/a"}:
        return None
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"KOSIS semiconductor value is not numeric: {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError("KOSIS semiconductor value must be finite")
    return parsed


def _month_shift(period: str, months: int) -> str:
    if len(period) != 6 or not period.isdigit():
        raise ValueError(f"Invalid monthly period: {period}")
    year = int(period[:4])
    month = int(period[4:])
    if month < 1 or month > 12:
        raise ValueError(f"Invalid monthly period: {period}")
    absolute = year * 12 + (month - 1) + months
    shifted_year, shifted_month_zero = divmod(absolute, 12)
    return f"{shifted_year:04d}{shifted_month_zero + 1:02d}"


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - 1.0) * 100.0


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _heuristic_phase(shipment_yoy: float | None, inventory_yoy: float | None) -> str | None:
    if shipment_yoy is None or inventory_yoy is None:
        return None
    if shipment_yoy >= 0 and inventory_yoy < 0:
        return "recovery_destocking"
    if shipment_yoy >= 0 and inventory_yoy >= 0:
        spread = shipment_yoy - inventory_yoy
        if spread > HEURISTIC_SPREAD_DEADBAND_PP:
            return "expansion_inventory_controlled"
        if spread < -HEURISTIC_SPREAD_DEADBAND_PP:
            return "expansion_inventory_build"
        return "expansion_inventory_balanced"
    if shipment_yoy < 0 and inventory_yoy < 0:
        return "contraction_destocking"
    return "demand_slowdown_inventory_build"


def _verify_table_bindings(
    client: KosisReadOnlyClient,
) -> tuple[dict[str, object], dict[str, tuple[object, object]]]:
    verification: dict[str, object] = {}
    raw: dict[str, tuple[object, object]] = {}
    for binding in TABLE_BINDINGS:
        identity, search_payload, meta_payload = client.verify_exact_table(
            binding.table_name,
            org_id=KOSIS_ORG_ID,
        )
        candidate = identity.candidate
        if not identity.verified:
            raise ValueError(f"KOSIS table binding is not verified: {binding.role}")
        if candidate.table_id != binding.table_id:
            raise ValueError(
                "KOSIS verified table ID changed: "
                f"role={binding.role} expected={binding.table_id} actual={candidate.table_id}"
            )
        verification[binding.role] = {
            "table_id": binding.table_id,
            "table_name": binding.table_name,
            "object_codes": binding.object_codes,
            "classification_names": binding.classification_names,
            "exact_title_match": identity.exact_title_match,
            "metadata_title_verified": identity.metadata_title_verified,
        }
        raw[binding.role] = (search_payload, meta_payload)
    return verification, raw


def _fetch_series(
    client: KosisReadOnlyClient,
    spec: SeriesSpec,
    *,
    months: int,
) -> tuple[tuple[KosisParameterRow, ...], object]:
    query = KosisParameterQuery(
        org_id=KOSIS_ORG_ID,
        table_id=spec.table_id,
        object_codes=spec.object_codes,
        item_id=spec.item_id,
        period=spec.frequency,
        latest_count=months,
    )
    rows, raw_payload = client.fetch_parameter_data(query)
    titles = {_canonical_text(row.table_name) for row in rows}
    if titles != {_canonical_text(spec.table_name)}:
        raise ValueError(f"KOSIS table title alias changed for metric {spec.metric}: {sorted(titles)}")
    units = {_canonical_text(row.unit_name) for row in rows}
    if units != {"2020=100"}:
        raise ValueError(f"Unexpected KOSIS unit for metric {spec.metric}: {sorted(units)}")
    for row in rows:
        if row.classification_ids != spec.object_codes:
            raise ValueError(f"KOSIS classification ID drift for metric {spec.metric}")
        if row.classification_names != spec.classification_names:
            raise ValueError(f"KOSIS classification name drift for metric {spec.metric}")
        if row.item_id != spec.item_id or row.item_name != spec.item_name:
            raise ValueError(f"KOSIS item binding drift for metric {spec.metric}")
    ordered = tuple(sorted(rows, key=lambda row: row.period))
    return ordered, raw_payload


def _normalize_series_rows(
    rows_by_metric: dict[str, tuple[KosisParameterRow, ...]],
) -> tuple[list[dict[str, object]], dict[str, dict[str, float]]]:
    normalized: list[dict[str, object]] = []
    values: dict[str, dict[str, float]] = {}
    for spec in SERIES_SPECS:
        metric_rows = rows_by_metric[spec.metric]
        series_values: dict[str, float] = {}
        for row in metric_rows:
            numeric = _parse_numeric(row.value_text)
            row_payload = asdict(row)
            row_payload["metric"] = spec.metric
            row_payload["value"] = numeric
            normalized.append(row_payload)
            if numeric is not None:
                series_values[row.period] = numeric
        values[spec.metric] = series_values
    normalized.sort(key=lambda row: (str(row["period"]), str(row["metric"])))
    return normalized, values


def build_semiconductor_diagnostics(
    values: dict[str, dict[str, float]],
) -> dict[str, object]:
    all_periods = sorted({period for series in values.values() for period in series})
    monthly: list[dict[str, object]] = []

    def value(metric: str, period: str) -> float | None:
        return values.get(metric, {}).get(period)

    for period in all_periods:
        lag1 = _month_shift(period, -1)
        lag12 = _month_shift(period, -12)
        production_yoy = _pct_change(value("production_raw", period), value("production_raw", lag12))
        shipment_yoy = _pct_change(value("shipment_raw", period), value("shipment_raw", lag12))
        inventory_yoy = _pct_change(value("inventory_raw", period), value("inventory_raw", lag12))
        capacity_yoy = _pct_change(value("capacity_raw", period), value("capacity_raw", lag12))
        utilization_yoy = _pct_change(
            value("utilization_raw", period), value("utilization_raw", lag12)
        )
        production_mom_sa = _pct_change(value("production_sa", period), value("production_sa", lag1))
        shipment_mom_sa = _pct_change(value("shipment_sa", period), value("shipment_sa", lag1))
        inventory_mom_sa = _pct_change(value("inventory_sa", period), value("inventory_sa", lag1))
        utilization_mom_sa = _pct_change(
            value("utilization_sa", period), value("utilization_sa", lag1)
        )
        shipment_minus_inventory = (
            shipment_yoy - inventory_yoy
            if shipment_yoy is not None and inventory_yoy is not None
            else None
        )
        production_minus_shipment = (
            production_yoy - shipment_yoy
            if production_yoy is not None and shipment_yoy is not None
            else None
        )
        shipment_level = value("shipment_raw", period)
        inventory_level = value("inventory_raw", period)
        inventory_vs_shipment = (
            inventory_level / shipment_level * 100.0
            if inventory_level is not None and shipment_level not in {None, 0}
            else None
        )
        phase = _heuristic_phase(shipment_yoy, inventory_yoy)
        confirmations: list[str] = []
        for label, metric_value in (
            ("production_sa_mom_positive", production_mom_sa),
            ("shipment_sa_mom_positive", shipment_mom_sa),
            ("utilization_sa_mom_positive", utilization_mom_sa),
            ("inventory_sa_mom_negative", -inventory_mom_sa if inventory_mom_sa is not None else None),
        ):
            if metric_value is not None and metric_value > 0:
                confirmations.append(label)

        if any(
            metric is not None
            for metric in (
                production_yoy,
                shipment_yoy,
                inventory_yoy,
                capacity_yoy,
                utilization_yoy,
                production_mom_sa,
                shipment_mom_sa,
                inventory_mom_sa,
                utilization_mom_sa,
            )
        ):
            monthly.append(
                {
                    "period": period,
                    "production_yoy_pct": _rounded(production_yoy),
                    "shipment_yoy_pct": _rounded(shipment_yoy),
                    "inventory_yoy_pct": _rounded(inventory_yoy),
                    "capacity_yoy_pct": _rounded(capacity_yoy),
                    "utilization_yoy_pct": _rounded(utilization_yoy),
                    "production_mom_sa_pct": _rounded(production_mom_sa),
                    "shipment_mom_sa_pct": _rounded(shipment_mom_sa),
                    "inventory_mom_sa_pct": _rounded(inventory_mom_sa),
                    "utilization_mom_sa_pct": _rounded(utilization_mom_sa),
                    "shipment_minus_inventory_yoy_pp": _rounded(shipment_minus_inventory),
                    "production_minus_shipment_yoy_pp": _rounded(production_minus_shipment),
                    "inventory_vs_shipment_index_ratio": _rounded(inventory_vs_shipment),
                    "heuristic_phase": phase,
                    "momentum_confirmations": confirmations,
                }
            )

    latest = monthly[-1] if monthly else None
    return {
        "schema_version": 2,
        "status": "heuristic_diagnostics_available" if latest is not None else "insufficient_history",
        "methodology": {
            "raw_yoy": "12-month percent change on original indexes",
            "seasonally_adjusted_mom": "1-month percent change on seasonally adjusted indexes",
            "shipment_minus_inventory_yoy_pp": (
                "shipment YoY minus inventory YoY; positive values mean shipments are growing "
                "faster than inventory"
            ),
            "inventory_vs_shipment_index_ratio": (
                "relative ratio of two 2020=100 indexes; not a physical stock-to-sales ratio"
            ),
            "heuristic_phase": (
                "transparent sign-and-spread diagnostic based only on shipment and inventory YoY; "
                "a fixed spread deadband prevents near-equal growth from flipping inventory labels; "
                "not a certified industry-cycle regime"
            ),
            "heuristic_phase_spread_deadband_pp": HEURISTIC_SPREAD_DEADBAND_PP,
            "heuristic_phase_spread_deadband_basis": (
                "fixed descriptive stability guard; not estimated from returns or fitted to outcomes"
            ),
        },
        "diagnostic_month_count": len(monthly),
        "latest": latest,
        "monthly": monthly,
        "heuristic_phase_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }


def capture_semiconductor_history(
    *,
    client: KosisReadOnlyClient,
    output_root: Path,
    now: datetime,
    months: int = DEFAULT_MONTHS,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("KOSIS semiconductor history clock must be timezone-aware")
    if months < 13 or months > MAX_MONTHS:
        raise ValueError(f"KOSIS semiconductor history months must be between 13 and {MAX_MONTHS}")

    binding_verification, raw_binding = _verify_table_bindings(client)
    rows_by_metric: dict[str, tuple[KosisParameterRow, ...]] = {}
    raw_by_metric: dict[str, object] = {}
    series_manifest: list[dict[str, object]] = []
    for spec in SERIES_SPECS:
        rows, raw_payload = _fetch_series(client, spec, months=months)
        rows_by_metric[spec.metric] = rows
        raw_by_metric[spec.metric] = raw_payload
        periods = [row.period for row in rows]
        series_manifest.append(
            {
                "metric": spec.metric,
                "table_id": spec.table_id,
                "table_name": spec.table_name,
                "object_codes": spec.object_codes,
                "classification_names": spec.classification_names,
                "item_id": spec.item_id,
                "item_name": spec.item_name,
                "row_count": len(rows),
                "first_period": min(periods),
                "last_period": max(periods),
                "source_change_dates": sorted({row.last_changed for row in rows if row.last_changed}),
                "missing_last_changed_rows": sum(not row.last_changed for row in rows),
                "raw_sha256": hashlib.sha256(_canonical_bytes(raw_payload)).hexdigest(),
            }
        )

    normalized_rows, values = _normalize_series_rows(rows_by_metric)
    diagnostics = build_semiconductor_diagnostics(values)
    captured_at = now.astimezone(UTC)
    normalized_sha256 = hashlib.sha256(_canonical_bytes(normalized_rows)).hexdigest()
    diagnostics_sha256 = hashlib.sha256(_canonical_bytes(diagnostics)).hexdigest()
    identity_material: dict[str, object] = {
        "schema_version": 1,
        "source": "kosis_openapi",
        "source_scope": "korean_semiconductor_cycle_history",
        "captured_at": captured_at.isoformat(),
        "requested_months": months,
        "org_id": KOSIS_ORG_ID,
        "binding_verification": binding_verification,
        "series": series_manifest,
        "normalized_sha256": normalized_sha256,
        "diagnostics_sha256": diagnostics_sha256,
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "heuristic_phase_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
        "status": "semiconductor_history_captured",
    }
    artifact_id = hashlib.sha256(_canonical_bytes(identity_material)).hexdigest()
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    directory.mkdir(parents=True, exist_ok=False)

    for role, (search_payload, meta_payload) in raw_binding.items():
        _write_json(directory / f"raw_search__{role}.json", search_payload)
        _write_json(directory / f"raw_meta__{role}.json", meta_payload)
    for metric, raw_payload in raw_by_metric.items():
        _write_json(directory / f"raw_series__{metric}.json", raw_payload)
    _write_json(directory / "normalized_series.json", normalized_rows)
    _write_json(directory / "series_manifest.json", series_manifest)
    _write_json(directory / "diagnostics.json", diagnostics)
    manifest = {**identity_material, "artifact_id": artifact_id}
    _write_json(directory / "manifest.json", manifest)

    latest = diagnostics.get("latest")
    latest_period = (
        str(cast(dict[str, object], latest).get("period", ""))
        if isinstance(latest, dict)
        else ""
    )
    pointer: dict[str, object] = {
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "diagnostics_path": str((directory / "diagnostics.json").resolve()),
        "status": "semiconductor_history_captured",
        "diagnostics_status": diagnostics["status"],
        "latest_period": latest_period,
        "requested_months": months,
        "series_count": len(SERIES_SPECS),
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "heuristic_phase_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / LATEST_POINTER_NAME, pointer, ensure_ascii=True)
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kosis-semiconductor-history",
        description=(
            "Capture verified KOSIS semiconductor production, shipment, inventory, capacity, "
            "and utilization history and derive non-scoring diagnostics"
        ),
    )
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        if args.max_retries < 0:
            raise ValueError("--max-retries cannot be negative")
        client = KosisReadOnlyClient.from_env()
        client.timeout_seconds = args.timeout_seconds
        client.max_retries = args.max_retries
        pointer = capture_semiconductor_history(
            client=client,
            output_root=args.output,
            now=datetime.now(UTC),
            months=args.months,
        )
        print(json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())