"""Capture revision-sensitive KOSIS industry parameter data without scoring it."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.providers.kosis import (
    DEFAULT_INDUSTRY_SEARCH,
    DEFAULT_KOSIS_ORG_ID,
    DEFAULT_KOSIS_PERIOD,
    DEFAULT_KOSIS_TABLE_ID,
    KosisParameterQuery,
    KosisParameterRow,
    KosisReadOnlyClient,
)

DEFAULT_OUTPUT_ROOT = Path("data/private/live-research/kosis-industry-parameters")
LATEST_POINTER_NAME = "latest_kosis_industry_parameters.json"


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


def build_parameter_inventory(rows: tuple[KosisParameterRow, ...]) -> dict[str, object]:
    """Build table inventory without pretending one item has one universal unit."""

    classifications: dict[tuple[str, ...], dict[str, object]] = {}
    item_names: dict[str, str] = {}
    item_units: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        classifications.setdefault(
            row.classification_ids,
            {
                "classification_ids": row.classification_ids,
                "classification_object_names": row.classification_object_names,
                "classification_names": row.classification_names,
            },
        )
        existing_name = item_names.setdefault(row.item_id, row.item_name)
        if existing_name != row.item_name:
            raise ValueError("KOSIS item ID mapped to multiple item names")
        item_units.setdefault(row.item_id, set()).add((row.unit_id, row.unit_name))

    item_rows: list[dict[str, object]] = []
    for item_id in sorted(item_names):
        units = sorted(item_units.get(item_id, set()))
        item_rows.append(
            {
                "item_id": item_id,
                "item_name": item_names[item_id],
                "unit_variant_count": len(units),
                "units": [
                    {"unit_id": unit_id, "unit_name": unit_name}
                    for unit_id, unit_name in units
                ],
            }
        )

    periods = sorted({row.period for row in rows})
    source_change_dates = sorted({row.last_changed for row in rows if row.last_changed})
    return {
        "inventory_schema_version": 2,
        "classification_count": len(classifications),
        "classifications": sorted(
            classifications.values(),
            key=lambda value: cast(tuple[str, ...], value["classification_ids"]),
        ),
        "item_count": len(item_rows),
        "items": item_rows,
        "period_count": len(periods),
        "periods": periods,
        "source_change_dates": source_change_dates,
        "missing_last_changed_rows": sum(not row.last_changed for row in rows),
    }


def capture_parameter_data(
    *,
    client: KosisReadOnlyClient,
    query: KosisParameterQuery,
    output_root: Path,
    now: datetime,
    expected_table_name: str = DEFAULT_INDUSTRY_SEARCH,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("KOSIS capture clock must be timezone-aware")
    expected_title = expected_table_name.strip()
    if not expected_title:
        raise ValueError("KOSIS expected_table_name cannot be blank")

    rows, raw_payload = client.fetch_parameter_data(query)
    titles = {row.table_name for row in rows}
    if titles != {expected_title}:
        raise ValueError("KOSIS parameter data title does not match the verified table")

    normalized_rows = [asdict(row) for row in rows]
    inventory = build_parameter_inventory(rows)
    captured_at = now.astimezone(UTC)
    query_payload = query.params()
    probe_scope = (
        query.object_codes == ("ALL",)
        and query.item_id == "ALL"
        and query.latest_count == 1
        and query.start_period is None
    )
    query_scope = "parameter_inventory_probe" if probe_scope else "bounded_parameter_capture"

    raw_sha256 = hashlib.sha256(_canonical_bytes(raw_payload)).hexdigest()
    normalized_sha256 = hashlib.sha256(_canonical_bytes(normalized_rows)).hexdigest()
    identity_material: dict[str, object] = {
        "schema_version": 2,
        "source": "kosis_openapi",
        "source_scope": "parameter_data",
        "query_scope": query_scope,
        "captured_at": captured_at.isoformat(),
        "org_id": query.org_id,
        "table_id": query.table_id,
        "table_name": expected_title,
        "query": query_payload,
        "row_count": len(rows),
        "classification_count": inventory["classification_count"],
        "item_count": inventory["item_count"],
        "period_count": inventory["period_count"],
        "raw_sha256": raw_sha256,
        "normalized_sha256": normalized_sha256,
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
        "status": "parameter_data_captured",
    }
    artifact_id = hashlib.sha256(_canonical_bytes(identity_material)).hexdigest()
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    directory.mkdir(parents=True, exist_ok=False)

    _write_json(directory / "raw_parameter_data.json", raw_payload)
    _write_json(directory / "normalized_rows.json", normalized_rows)
    _write_json(directory / "parameter_inventory.json", inventory)
    manifest = {**identity_material, "artifact_id": artifact_id}
    _write_json(directory / "manifest.json", manifest)

    pointer: dict[str, object] = {
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "status": "parameter_data_captured",
        "query_scope": query_scope,
        "org_id": query.org_id,
        "table_id": query.table_id,
        "table_name": expected_title,
        "row_count": len(rows),
        "classification_count": inventory["classification_count"],
        "item_count": inventory["item_count"],
        "periods": inventory["periods"],
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / LATEST_POINTER_NAME, pointer, ensure_ascii=True)
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kosis-parameters",
        description=(
            "Capture an exact verified KOSIS table while keeping industry-cycle "
            "scoring disabled"
        ),
    )
    parser.add_argument("--org-id", default=DEFAULT_KOSIS_ORG_ID)
    parser.add_argument("--table-id", default=DEFAULT_KOSIS_TABLE_ID)
    parser.add_argument("--expected-table-name", default=DEFAULT_INDUSTRY_SEARCH)
    parser.add_argument(
        "--obj",
        action="append",
        dest="object_codes",
        help="classification code in dimension order; repeat for objL2..objL8",
    )
    parser.add_argument("--itm-id", default="ALL")
    parser.add_argument("--prd-se", default=DEFAULT_KOSIS_PERIOD)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--latest-count", type=int, default=1)
    parser.add_argument("--period-interval", type=int, default=1)
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

        start = str(args.start).strip() if args.start is not None else None
        end = str(args.end).strip() if args.end is not None else None
        latest_count = None if start is not None or end is not None else args.latest_count
        object_codes = tuple(args.object_codes or ("ALL",))
        query = KosisParameterQuery(
            org_id=str(args.org_id).strip(),
            table_id=str(args.table_id).strip(),
            object_codes=object_codes,
            item_id=str(args.itm_id).strip(),
            period=str(args.prd_se).strip().upper(),
            start_period=start,
            end_period=end,
            latest_count=latest_count,
            period_interval=args.period_interval,
        )
        client = KosisReadOnlyClient.from_env()
        client.timeout_seconds = args.timeout_seconds
        client.max_retries = args.max_retries
        pointer = capture_parameter_data(
            client=client,
            query=query,
            output_root=args.output,
            now=datetime.now(UTC),
            expected_table_name=str(args.expected_table_name),
        )
        print(json.dumps(pointer, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        error_payload = json.dumps(
            {"status": "failed", "error": str(exc)},
            ensure_ascii=False,
        )
        print(error_payload, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
