"""Normalize KIS forward estimate levels only after local historical semantic crosschecks.

This module deliberately distinguishes three claims:

1. historical row/scale mapping verified against OpenDART for a narrow issuer/year scope;
2. forward values normalized from a structurally compatible KIS snapshot;
3. provider/consensus semantics, which remain uncertified.

No decision score is changed here.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.providers.kis_research import KIS_RESEARCH_SOURCE_SCOPE

EXPECTED_PROVIDER = "korea_investment_openapi"
OWNER_ACCOUNT_ID = "ifrs-full_ProfitLossAttributableToOwnersOfParent"
VERIFIED_SYMBOLS = ("000660", "005930")
_PERIOD = re.compile(r"^(\d{4})\.(\d{2})(E)?$")
_DATA_FIELD = re.compile(r"^data([1-9][0-9]*)$", re.IGNORECASE)


@dataclass(frozen=True)
class MetricBinding:
    """One historically crosschecked KIS row/scale mapping."""

    metric: str
    output_name: str
    row_number_1_based: int
    scale_to_krw: float

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("Metric binding name cannot be blank")
        if not self.output_name.startswith("output"):
            raise ValueError("Metric binding output_name is invalid")
        if self.row_number_1_based <= 0:
            raise ValueError("Metric binding row number must be positive")
        if not math.isfinite(self.scale_to_krw) or self.scale_to_krw <= 0:
            raise ValueError("Metric binding scale_to_krw must be positive and finite")

    def as_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "output_name": self.output_name,
            "row_number_1_based": self.row_number_1_based,
            "scale_to_krw": self.scale_to_krw,
        }


@dataclass(frozen=True)
class KisForwardSemanticBinding:
    """Local historical evidence supporting forward row normalization."""

    evidence_expectation_snapshot_id: str
    evidence_valuation_snapshot_id: str
    general_crosscheck_artifact_id: str
    owner_crosscheck_artifact_id: str
    verified_symbols: tuple[str, ...]
    actual_years: tuple[int, ...]
    period_field_policy: str
    metrics: tuple[MetricBinding, ...]
    owner_reference_account_id: str

    def __post_init__(self) -> None:
        for field, value in (
            ("evidence_expectation_snapshot_id", self.evidence_expectation_snapshot_id),
            ("evidence_valuation_snapshot_id", self.evidence_valuation_snapshot_id),
            ("general_crosscheck_artifact_id", self.general_crosscheck_artifact_id),
            ("owner_crosscheck_artifact_id", self.owner_crosscheck_artifact_id),
        ):
            _sha256(value, field)
        if self.verified_symbols != tuple(sorted(set(self.verified_symbols))):
            raise ValueError("verified_symbols must be unique and sorted")
        if len(self.actual_years) < 3 or self.actual_years != tuple(sorted(set(self.actual_years))):
            raise ValueError("actual_years must contain at least three unique sorted years")
        if self.period_field_policy != "output4_positional_data_columns":
            raise ValueError("Unexpected period-field policy")
        metric_names = tuple(item.metric for item in self.metrics)
        if metric_names != (
            "net_income_attributable_to_owners",
            "operating_income",
            "revenue",
        ):
            raise ValueError("Forward binding must contain the three verified financial metrics")
        row_keys = tuple((item.output_name, item.row_number_1_based) for item in self.metrics)
        if len(set(row_keys)) != len(row_keys):
            raise ValueError("Forward metric bindings cannot share the same source row")
        if self.owner_reference_account_id != OWNER_ACCOUNT_ID:
            raise ValueError("Unexpected owner-attributable net-income reference account")

    def as_dict(self) -> dict[str, object]:
        return {
            "binding_version": 1,
            "binding_scope": "005930_000660_2023_2025_historical_crosscheck",
            "evidence_expectation_snapshot_id": self.evidence_expectation_snapshot_id,
            "evidence_valuation_snapshot_id": self.evidence_valuation_snapshot_id,
            "general_crosscheck_artifact_id": self.general_crosscheck_artifact_id,
            "owner_crosscheck_artifact_id": self.owner_crosscheck_artifact_id,
            "verified_symbols": list(self.verified_symbols),
            "actual_years": list(self.actual_years),
            "period_field_policy": self.period_field_policy,
            "metrics": [item.as_dict() for item in self.metrics],
            "owner_reference_account_id": self.owner_reference_account_id,
            "historical_semantic_crosscheck_verified": True,
            "provider_semantics_certified": False,
            "consensus_certified": False,
            "revision_certified": False,
            "decision_score_enabled": False,
        }


@dataclass(frozen=True)
class NormalizedForwardEstimate:
    symbol: str
    metric: str
    period_label: str
    fiscal_year: int
    value_krw: float
    source_output: str
    source_row_number_1_based: int
    source_field: str
    scale_to_krw: float
    previous_period_label: str
    previous_value_krw: float
    growth_from_previous_pct: float | None
    growth_comparable: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "metric": self.metric,
            "period_label": self.period_label,
            "fiscal_year": self.fiscal_year,
            "value_krw": self.value_krw,
            "unit": "KRW",
            "source_output": self.source_output,
            "source_row_number_1_based": self.source_row_number_1_based,
            "source_field": self.source_field,
            "scale_to_krw": self.scale_to_krw,
            "previous_period_label": self.previous_period_label,
            "previous_value_krw": self.previous_value_krw,
            "growth_from_previous_pct": self.growth_from_previous_pct,
            "growth_comparable": self.growth_comparable,
            "historical_semantic_crosscheck_verified": True,
            "provider_semantics_certified": False,
            "consensus_certified": False,
            "revision_certified": False,
            "decision_score_enabled": False,
        }


def _sha256(value: str, field: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return text


def read_json_object(path: str | Path, *, label: str) -> dict[str, object]:
    location = Path(path)
    try:
        payload: object = json.loads(location.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {location}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {location}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in payload.items()}


def _strict_false(mapping: Mapping[str, object], key: str, *, label: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"{label} must keep {key}=false")


def _crosscheck_from_pointer(pointer_path: Path, *, label: str) -> dict[str, object]:
    pointer = read_json_object(pointer_path, label=f"{label} pointer")
    crosscheck_path = str(pointer.get("crosscheck_path", "")).strip()
    if not crosscheck_path:
        raise ValueError(f"{label} pointer is missing crosscheck_path")
    crosscheck = read_json_object(Path(crosscheck_path), label=label)
    pointer_artifact = _sha256(str(pointer.get("artifact_id", "")), f"{label} pointer artifact_id")
    artifact = _sha256(str(crosscheck.get("artifact_id", "")), f"{label} artifact_id")
    if pointer_artifact != artifact:
        raise ValueError(f"{label} pointer does not match its artifact")
    for key in (
        "provider_semantics_certified",
        "consensus_certified",
        "revision_certified",
        "decision_score_enabled",
    ):
        _strict_false(crosscheck, key, label=label)
    return crosscheck


def _unique_result(mapping: Mapping[str, object], *, label: str) -> Mapping[str, object]:
    if mapping.get("status") != "unique_historical_actual_match":
        raise ValueError(f"{label} is not a unique historical actual match")
    output_name = str(mapping.get("output_name", "")).strip()
    row_number = mapping.get("row_number_1_based")
    scale = mapping.get("scale_to_krw")
    if not output_name.startswith("output"):
        raise ValueError(f"{label} output_name is invalid")
    if isinstance(row_number, bool) or not isinstance(row_number, int) or row_number <= 0:
        raise ValueError(f"{label} row_number_1_based is invalid")
    if isinstance(scale, bool) or not isinstance(scale, (int, float)):
        raise ValueError(f"{label} scale_to_krw is invalid")
    scale_number = float(scale)
    if not math.isfinite(scale_number) or scale_number <= 0:
        raise ValueError(f"{label} scale_to_krw is invalid")
    year_to_field = mapping.get("year_to_field")
    if not isinstance(year_to_field, dict) or len(year_to_field) < 3:
        raise ValueError(f"{label} year_to_field is incomplete")
    for raw_year, raw_field in year_to_field.items():
        if not str(raw_year).isdigit() or _DATA_FIELD.fullmatch(str(raw_field).strip()) is None:
            raise ValueError(f"{label} year_to_field is invalid")
    return mapping


def build_semantic_binding(
    *,
    general_crosscheck_pointer: str | Path,
    owner_crosscheck_pointer: str | Path,
) -> KisForwardSemanticBinding:
    """Build a durable structural binding from the two successful historical crosschecks."""

    general = _crosscheck_from_pointer(
        Path(general_crosscheck_pointer),
        label="KIS general semantic crosscheck",
    )
    owner = _crosscheck_from_pointer(
        Path(owner_crosscheck_pointer),
        label="KIS owner-net-income crosscheck",
    )
    if general.get("status") not in {
        "historical_actual_crosscheck_partial",
        "historical_actual_crosscheck_complete",
    }:
        raise ValueError("KIS general semantic crosscheck status is not usable")
    if owner.get("status") != "owner_net_income_historical_match_verified":
        raise ValueError("KIS owner-net-income crosscheck is not verified")

    general_expectation = _sha256(
        str(general.get("expectation_snapshot_id", "")),
        "general expectation_snapshot_id",
    )
    owner_expectation = _sha256(
        str(owner.get("expectation_snapshot_id", "")),
        "owner expectation_snapshot_id",
    )
    general_valuation = _sha256(
        str(general.get("valuation_snapshot_id", "")),
        "general valuation_snapshot_id",
    )
    owner_valuation = _sha256(
        str(owner.get("valuation_snapshot_id", "")),
        "owner valuation_snapshot_id",
    )
    if general_expectation != owner_expectation:
        raise ValueError("Semantic crosschecks are bound to different KIS expectation snapshots")
    if general_valuation != owner_valuation:
        raise ValueError("Semantic crosschecks are bound to different valuation snapshots")

    metric_results = general.get("metric_results")
    if not isinstance(metric_results, dict):
        raise ValueError("General semantic crosscheck is missing metric_results")
    revenue_raw = metric_results.get("revenue")
    operating_raw = metric_results.get("operating_income")
    if not isinstance(revenue_raw, dict) or not isinstance(operating_raw, dict):
        raise ValueError("Revenue and operating-income semantic results are required")
    revenue = _unique_result(cast(Mapping[str, object], revenue_raw), label="revenue")
    operating = _unique_result(
        cast(Mapping[str, object], operating_raw),
        label="operating_income",
    )

    owner_result_raw = owner.get("metric_result")
    if not isinstance(owner_result_raw, dict):
        raise ValueError("Owner-net-income crosscheck is missing metric_result")
    owner_result = _unique_result(
        cast(Mapping[str, object], owner_result_raw),
        label="net_income_attributable_to_owners",
    )
    if str(owner.get("authoritative_reference_account_id", "")).strip() != OWNER_ACCOUNT_ID:
        raise ValueError("Owner-net-income crosscheck used an unexpected OpenDART account")

    def binding(metric: str, result: Mapping[str, object]) -> MetricBinding:
        return MetricBinding(
            metric=metric,
            output_name=str(result["output_name"]),
            row_number_1_based=int(cast(int, result["row_number_1_based"])),
            scale_to_krw=float(cast(float | int, result["scale_to_krw"])),
        )

    year_maps = [
        cast(Mapping[str, object], result["year_to_field"])
        for result in (revenue, operating, owner_result)
    ]
    actual_years = tuple(sorted(int(year) for year in year_maps[0]))
    if any(tuple(sorted(int(year) for year in mapping)) != actual_years for mapping in year_maps[1:]):
        raise ValueError("Verified KIS metrics use inconsistent actual-year mappings")
    for mapping in year_maps:
        expected_fields = tuple(f"data{index}" for index in range(1, len(actual_years) + 1))
        fields = tuple(str(mapping[str(year)]) for year in actual_years)
        if fields != expected_fields:
            raise ValueError("Verified historical KIS mapping is not positional")

    metrics = tuple(
        sorted(
            (
                binding("revenue", revenue),
                binding("operating_income", operating),
                binding("net_income_attributable_to_owners", owner_result),
            ),
            key=lambda item: item.metric,
        )
    )
    return KisForwardSemanticBinding(
        evidence_expectation_snapshot_id=general_expectation,
        evidence_valuation_snapshot_id=general_valuation,
        general_crosscheck_artifact_id=_sha256(
            str(general.get("artifact_id", "")),
            "general_crosscheck_artifact_id",
        ),
        owner_crosscheck_artifact_id=_sha256(
            str(owner.get("artifact_id", "")),
            "owner_crosscheck_artifact_id",
        ),
        verified_symbols=tuple(sorted(VERIFIED_SYMBOLS)),
        actual_years=actual_years,
        period_field_policy="output4_positional_data_columns",
        metrics=metrics,
        owner_reference_account_id=OWNER_ACCOUNT_ID,
    )


def latest_expectation_snapshot(root: str | Path) -> tuple[Path, dict[str, object]]:
    """Return the latest complete local KIS expectation snapshot."""

    directory_root = Path(root)
    if not directory_root.is_dir():
        raise ValueError(f"Expectation root does not exist: {directory_root}")
    candidates = sorted(
        (item for item in directory_root.iterdir() if item.is_dir() and not item.name.startswith(".")),
        reverse=True,
    )
    for directory in candidates:
        manifest_path = directory / "manifest.json"
        raw_path = directory / "raw_estimate_perform.json"
        if not manifest_path.is_file() or not raw_path.is_file():
            continue
        manifest = read_json_object(manifest_path, label="KIS expectation manifest")
        return directory, manifest
    raise ValueError("No complete KIS expectation snapshot was found")


def _validate_expectation_manifest(manifest: Mapping[str, object]) -> tuple[str, datetime]:
    snapshot_id = _sha256(str(manifest.get("snapshot_id", "")), "expectation snapshot_id")
    if manifest.get("provider") != EXPECTED_PROVIDER:
        raise ValueError("Unexpected KIS expectation provider")
    if manifest.get("source_scope") != KIS_RESEARCH_SOURCE_SCOPE:
        raise ValueError("Unexpected KIS expectation source scope")
    if manifest.get("semantic_status") != "raw_structure_only":
        raise ValueError("KIS expectation snapshot must remain raw_structure_only")
    for key in (
        "consensus_certified",
        "revision_certified",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _strict_false(manifest, key, label="KIS expectation manifest")
    captured_text = str(manifest.get("captured_at", "")).strip()
    try:
        captured_at = datetime.fromisoformat(captured_text)
    except ValueError as exc:
        raise ValueError("KIS expectation captured_at is invalid") from exc
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("KIS expectation captured_at must be timezone-aware")
    return snapshot_id, captured_at


def _rows(value: object, *, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    rows: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        rows.append(cast(Mapping[str, object], item))
    return tuple(rows)


def _period_axis(payload: Mapping[str, object], *, symbol: str) -> tuple[str, ...]:
    rows = _rows(payload.get("output4"), label=f"{symbol}.output4")
    labels: list[str] = []
    seen_forecast = False
    prior_year = 0
    for index, row in enumerate(rows, start=1):
        if set(str(key) for key in row) != {"dt"}:
            raise ValueError(f"{symbol}.output4 must contain only dt")
        label = str(row.get("dt", "")).strip()
        match = _PERIOD.fullmatch(label)
        if match is None:
            raise ValueError(f"Unsupported KIS period label for {symbol}: {label!r}")
        year = int(match.group(1))
        if year <= prior_year:
            raise ValueError(f"KIS period years must increase for {symbol}")
        prior_year = year
        is_forecast = match.group(3) is not None
        if seen_forecast and not is_forecast:
            raise ValueError(f"KIS actual period cannot follow a forecast period for {symbol}")
        seen_forecast = seen_forecast or is_forecast
        expected_field = f"data{index}"
        if _DATA_FIELD.fullmatch(expected_field) is None:
            raise AssertionError("Internal KIS field construction failed")
        labels.append(label)
    if not labels or not any(label.endswith("E") for label in labels):
        raise ValueError(f"KIS period axis has no forecast periods for {symbol}")
    if not any(not label.endswith("E") for label in labels):
        raise ValueError(f"KIS period axis has no actual reference period for {symbol}")
    return tuple(labels)


def _number(value: object, *, label: str) -> float:
    text = str(value).strip().replace(",", "")
    if text.casefold() in {"", "-", "--", "none", "nan", "n/a", "null"}:
        raise ValueError(f"{label} is missing")
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        parsed = float(text)
    except ValueError as exc:
        raise ValueError(f"{label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return -parsed if negative else parsed


def normalize_forward_estimates(
    *,
    expectation_directory: str | Path,
    binding: KisForwardSemanticBinding,
) -> tuple[str, datetime, pd.DataFrame, pd.DataFrame]:
    """Apply a historically verified structural binding to one compatible KIS snapshot."""

    directory = Path(expectation_directory)
    manifest = read_json_object(directory / "manifest.json", label="KIS expectation manifest")
    snapshot_id, captured_at = _validate_expectation_manifest(manifest)
    raw = read_json_object(
        directory / "raw_estimate_perform.json",
        label="KIS raw estimate-perform",
    )
    raw_symbols = manifest.get("symbols")
    if not isinstance(raw_symbols, list):
        raise ValueError("KIS expectation symbols must be an array")
    symbols = tuple(sorted(str(item).strip().zfill(6) for item in raw_symbols))
    if not set(binding.verified_symbols).issubset(symbols):
        raise ValueError("KIS expectation snapshot is missing a historically verified issuer")

    records: list[NormalizedForwardEstimate] = []
    common_axis: tuple[str, ...] | None = None
    for symbol in binding.verified_symbols:
        payload_raw = raw.get(symbol)
        if not isinstance(payload_raw, dict):
            raise ValueError(f"KIS raw expectation payload is missing {symbol}")
        payload = cast(Mapping[str, object], payload_raw)
        axis = _period_axis(payload, symbol=symbol)
        if common_axis is None:
            common_axis = axis
        elif axis != common_axis:
            raise ValueError("KIS forward period axes differ across verified issuers")
        data_fields = tuple(f"data{index}" for index in range(1, len(axis) + 1))
        forecast_indices = [index for index, label in enumerate(axis) if label.endswith("E")]
        if not forecast_indices or forecast_indices[0] == 0:
            raise ValueError("KIS forecast axis lacks an immediately preceding actual period")

        for metric_binding in binding.metrics:
            output_rows = _rows(
                payload.get(metric_binding.output_name),
                label=f"{symbol}.{metric_binding.output_name}",
            )
            row_index = metric_binding.row_number_1_based - 1
            if row_index >= len(output_rows):
                raise ValueError(
                    f"KIS source row is missing for {symbol} {metric_binding.metric}"
                )
            row = output_rows[row_index]
            if set(str(key) for key in row) != set(data_fields):
                raise ValueError(
                    f"KIS DATA structure changed for {symbol} {metric_binding.metric}"
                )
            scaled_values = [
                _number(
                    row.get(field),
                    label=f"{symbol}.{metric_binding.output_name}[{row_index}].{field}",
                )
                * metric_binding.scale_to_krw
                for field in data_fields
            ]
            for period_index in forecast_indices:
                label = axis[period_index]
                match = _PERIOD.fullmatch(label)
                assert match is not None
                previous_index = period_index - 1
                previous_value = scaled_values[previous_index]
                value = scaled_values[period_index]
                comparable = previous_value > 0
                growth = (
                    (value / previous_value - 1.0) * 100.0
                    if comparable
                    else None
                )
                records.append(
                    NormalizedForwardEstimate(
                        symbol=symbol,
                        metric=metric_binding.metric,
                        period_label=label,
                        fiscal_year=int(match.group(1)),
                        value_krw=value,
                        source_output=metric_binding.output_name,
                        source_row_number_1_based=metric_binding.row_number_1_based,
                        source_field=data_fields[period_index],
                        scale_to_krw=metric_binding.scale_to_krw,
                        previous_period_label=axis[previous_index],
                        previous_value_krw=previous_value,
                        growth_from_previous_pct=(
                            None if growth is None else round(growth, 8)
                        ),
                        growth_comparable=comparable,
                    )
                )

    if common_axis is None:
        raise ValueError("No verified KIS issuer was normalized")
    forward = pd.DataFrame([item.as_dict() for item in records]).sort_values(
        ["symbol", "fiscal_year", "metric"],
        kind="stable",
    ).reset_index(drop=True)
    if forward.empty:
        raise ValueError("KIS forward normalization produced no rows")

    summaries: list[dict[str, object]] = []
    for (symbol, period_label, fiscal_year), group in forward.groupby(
        ["symbol", "period_label", "fiscal_year"],
        sort=True,
    ):
        lookup = {
            str(raw_metric): float(raw_value)
            for raw_metric, raw_value in zip(group["metric"], group["value_krw"], strict=True)
        }
        required = {
            "revenue",
            "operating_income",
            "net_income_attributable_to_owners",
        }
        if set(lookup) != required:
            raise ValueError(f"Forward summary metrics are incomplete for {symbol} {period_label}")
        revenue = lookup["revenue"]
        operating = lookup["operating_income"]
        owner_net = lookup["net_income_attributable_to_owners"]
        summaries.append(
            {
                "symbol": str(symbol),
                "period_label": str(period_label),
                "fiscal_year": int(fiscal_year),
                "revenue_krw": revenue,
                "operating_income_krw": operating,
                "net_income_attributable_to_owners_krw": owner_net,
                "operating_margin_pct": (
                    round(operating / revenue * 100.0, 8) if revenue > 0 else None
                ),
                "owner_net_margin_pct": (
                    round(owner_net / revenue * 100.0, 8) if revenue > 0 else None
                ),
                "unit": "KRW",
                "historical_semantic_crosscheck_verified": True,
                "provider_semantics_certified": False,
                "consensus_certified": False,
                "revision_certified": False,
                "decision_score_enabled": False,
            }
        )
    summary = pd.DataFrame(summaries).sort_values(
        ["symbol", "fiscal_year"],
        kind="stable",
    ).reset_index(drop=True)
    return snapshot_id, captured_at, forward, summary


__all__ = [
    "KisForwardSemanticBinding",
    "MetricBinding",
    "NormalizedForwardEstimate",
    "OWNER_ACCOUNT_ID",
    "VERIFIED_SYMBOLS",
    "build_semantic_binding",
    "latest_expectation_snapshot",
    "normalize_forward_estimates",
    "read_json_object",
]
