"""Discover KOSIS tables appropriate for Korean semiconductor cycle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.kosis_industry_parameter_cli import build_parameter_inventory
from alpha_cycle.providers.kosis import (
    DEFAULT_KOSIS_ORG_ID,
    DEFAULT_KOSIS_PERIOD,
    KosisParameterQuery,
    KosisReadOnlyClient,
)

INDUSTRY_INDEX_TABLE_NAME = "시도/산업별 광공업생산지수(2020=100)"
CAPACITY_UTILIZATION_TABLE_NAME = "제조업 생산능력 및 가동률지수(2020=100)"
DEFAULT_OUTPUT_ROOT = Path(
    "data/private/live-research/kosis-semiconductor-source-discovery"
)
LATEST_POINTER_NAME = "latest_kosis_semiconductor_source_discovery.json"
SEMICONDUCTOR_TERMS = ("반도체 제조업", "반도체")


@dataclass(frozen=True)
class SourceTarget:
    role: str
    table_name: str


TARGETS = (
    SourceTarget("industry_production_shipment_inventory", INDUSTRY_INDEX_TABLE_NAME),
    SourceTarget("capacity_utilization", CAPACITY_UTILIZATION_TABLE_NAME),
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


def _classification_matches(
    inventory: dict[str, object],
    terms: tuple[str, ...],
) -> list[dict[str, object]]:
    raw = inventory.get("classifications")
    if not isinstance(raw, list):
        raise ValueError("KOSIS parameter inventory classifications must be an array")
    matched: list[dict[str, object]] = []
    for value in raw:
        if not isinstance(value, dict):
            raise ValueError("KOSIS parameter inventory classification must be an object")
        row = cast(dict[str, object], value)
        names_raw = row.get("classification_names")
        names = (
            [str(name).strip() for name in names_raw if str(name).strip()]
            if isinstance(names_raw, (list, tuple))
            else []
        )
        searchable = " ".join(names).casefold()
        hits = [term for term in terms if term.casefold() in searchable]
        if hits:
            matched.append(
                {
                    "classification_ids": row.get("classification_ids", ()),
                    "classification_object_names": row.get(
                        "classification_object_names", ()
                    ),
                    "classification_names": names,
                    "matched_terms": hits,
                }
            )
    return matched


def _discover_target(
    *,
    client: KosisReadOnlyClient,
    target: SourceTarget,
    org_id: str,
) -> tuple[dict[str, object], object, object | None, object | None]:
    candidates, raw_search = client.search_tables(target.table_name, org_id=org_id)
    exact = tuple(
        candidate for candidate in candidates if candidate.table_name == target.table_name
    )
    base: dict[str, object] = {
        "role": target.role,
        "table_name": target.table_name,
        "candidate_count": len(candidates),
        "exact_match_count": len(exact),
        "table_id": None,
        "metadata_title_verified": False,
        "parameter_probe_row_count": 0,
        "parameter_probe_periods": [],
        "item_count": 0,
        "items": [],
        "semiconductor_classification_count": 0,
        "semiconductor_classifications": [],
    }
    if len(exact) == 0:
        return {**base, "status": "no_exact_table_match"}, raw_search, None, None
    if len(exact) > 1:
        return {**base, "status": "ambiguous_exact_table_match"}, raw_search, None, None

    candidate = exact[0]
    metadata_title, raw_meta = client.table_title(candidate.org_id, candidate.table_id)
    if metadata_title != target.table_name:
        return (
            {
                **base,
                "table_id": candidate.table_id,
                "status": "table_metadata_mismatch",
            },
            raw_search,
            raw_meta,
            None,
        )

    query = KosisParameterQuery(
        org_id=candidate.org_id,
        table_id=candidate.table_id,
        object_codes=("ALL",),
        item_id="ALL",
        period=DEFAULT_KOSIS_PERIOD,
        latest_count=1,
    )
    try:
        rows, raw_parameter = client.fetch_parameter_data(query)
    except (ValueError, OSError, TypeError) as exc:
        return (
            {
                **base,
                "table_id": candidate.table_id,
                "metadata_title_verified": True,
                "status": "parameter_probe_failed",
                "parameter_probe_error": str(exc),
            },
            raw_search,
            raw_meta,
            None,
        )

    titles = {row.table_name for row in rows}
    if titles != {target.table_name}:
        return (
            {
                **base,
                "table_id": candidate.table_id,
                "metadata_title_verified": True,
                "status": "parameter_title_mismatch",
            },
            raw_search,
            raw_meta,
            raw_parameter,
        )

    inventory = build_parameter_inventory(rows)
    matches = _classification_matches(inventory, SEMICONDUCTOR_TERMS)
    periods = sorted({row.period for row in rows})
    status = "inventory_verified" if matches else "no_semiconductor_classification"
    result = {
        **base,
        "table_id": candidate.table_id,
        "metadata_title_verified": True,
        "parameter_probe_row_count": len(rows),
        "parameter_probe_periods": periods,
        "item_count": inventory["item_count"],
        "items": inventory["items"],
        "semiconductor_classification_count": len(matches),
        "semiconductor_classifications": matches,
        "status": status,
    }
    return result, raw_search, raw_meta, raw_parameter


def discover_semiconductor_sources(
    *,
    client: KosisReadOnlyClient,
    output_root: Path,
    now: datetime,
    org_id: str = DEFAULT_KOSIS_ORG_ID,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("KOSIS semiconductor discovery clock must be timezone-aware")
    clean_org = org_id.strip()
    if not clean_org:
        raise ValueError("KOSIS org_id cannot be blank")

    target_results: list[dict[str, object]] = []
    raw_by_role: dict[str, tuple[object, object | None, object | None]] = {}
    for target in TARGETS:
        result, raw_search, raw_meta, raw_parameter = _discover_target(
            client=client,
            target=target,
            org_id=clean_org,
        )
        target_results.append(result)
        raw_by_role[target.role] = (raw_search, raw_meta, raw_parameter)

    complete = all(result.get("status") == "inventory_verified" for result in target_results)
    overall_status = (
        "semiconductor_source_inventory_verified"
        if complete
        else "semiconductor_source_discovery_incomplete"
    )
    captured_at = now.astimezone(UTC)
    identity_material: dict[str, object] = {
        "schema_version": 1,
        "source": "kosis_openapi",
        "source_scope": "korean_semiconductor_industry_cycle_source_discovery",
        "captured_at": captured_at.isoformat(),
        "org_id": clean_org,
        "status": overall_status,
        "targets": target_results,
        "quantity_table_primary_for_semiconductors": False,
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }
    artifact_id = hashlib.sha256(_canonical_bytes(identity_material)).hexdigest()
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    directory.mkdir(parents=True, exist_ok=False)

    for role, (raw_search, raw_meta, raw_parameter) in raw_by_role.items():
        _write_json(directory / f"raw_search__{role}.json", raw_search)
        if raw_meta is not None:
            _write_json(directory / f"raw_meta__{role}.json", raw_meta)
        if raw_parameter is not None:
            _write_json(directory / f"raw_parameter__{role}.json", raw_parameter)
    _write_json(directory / "source_targets.json", target_results)
    manifest = {**identity_material, "artifact_id": artifact_id}
    _write_json(directory / "manifest.json", manifest)

    pointer: dict[str, object] = {
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "status": overall_status,
        "org_id": clean_org,
        "targets": target_results,
        "quantity_table_primary_for_semiconductors": False,
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
        prog="alpha-cycle-kosis-semiconductor-sources",
        description=(
            "Verify KOSIS industry-index and capacity-utilization sources for Korean "
            "semiconductor cycle research without enabling scoring"
        ),
    )
    parser.add_argument("--org-id", default=DEFAULT_KOSIS_ORG_ID)
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
        pointer = discover_semiconductor_sources(
            client=client,
            output_root=args.output,
            now=datetime.now(UTC),
            org_id=str(args.org_id),
        )
        print(json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if pointer["status"] == "semiconductor_source_inventory_verified" else 3
    except (ValueError, OSError, TypeError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
