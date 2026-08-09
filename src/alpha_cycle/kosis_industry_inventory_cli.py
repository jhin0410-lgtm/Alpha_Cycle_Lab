"""Inspect the latest local KOSIS parameter inventory without another API call."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

DEFAULT_POINTER = Path(
    "data/private/live-research/kosis-industry-parameters/"
    "latest_kosis_industry_parameters.json"
)
DEFAULT_MATCH_TERMS = ("반도체", "메모리", "집적회로", "D램", "DRAM")


def _read_json(path: Path) -> object:
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError as exc:
        raise ValueError(f"KOSIS inventory file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"KOSIS inventory file is not valid JSON: {path}") from exc


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], value)


def _object_rows(value: object, *, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a JSON array")
    rows: list[Mapping[str, object]] = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError(f"{label} rows must be JSON objects")
        rows.append(cast(Mapping[str, object], raw))
    return rows


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def inspect_latest_inventory(
    *,
    pointer_path: Path = DEFAULT_POINTER,
    match_terms: tuple[str, ...] = DEFAULT_MATCH_TERMS,
) -> dict[str, object]:
    pointer = _mapping(_read_json(pointer_path), label="KOSIS latest pointer")
    if pointer.get("status") != "parameter_data_captured":
        raise ValueError("KOSIS latest pointer is not a captured parameter-data artifact")
    if pointer.get("industry_cycle_certified") is not False:
        raise ValueError("KOSIS latest pointer must remain industry-cycle uncertified")
    if pointer.get("decision_score_enabled") is not False:
        raise ValueError("KOSIS latest pointer must remain non-scoring")

    artifact_directory = str(pointer.get("artifact_directory", "")).strip()
    if not artifact_directory:
        raise ValueError("KOSIS latest pointer is missing artifact_directory")
    inventory_path = Path(artifact_directory) / "parameter_inventory.json"
    inventory = _mapping(_read_json(inventory_path), label="KOSIS parameter inventory")

    items = _object_rows(inventory.get("items"), label="KOSIS inventory items")
    classifications = _object_rows(
        inventory.get("classifications"),
        label="KOSIS inventory classifications",
    )
    normalized_terms = tuple(term.strip() for term in match_terms if term.strip())
    if not normalized_terms:
        raise ValueError("At least one non-blank classification match term is required")

    matched: list[dict[str, object]] = []
    for row in classifications:
        names = _string_list(row.get("classification_names"))
        searchable = " ".join(names).casefold()
        hits = [term for term in normalized_terms if term.casefold() in searchable]
        if hits:
            matched.append(
                {
                    "classification_ids": _string_list(row.get("classification_ids")),
                    "classification_object_names": _string_list(
                        row.get("classification_object_names")
                    ),
                    "classification_names": names,
                    "matched_terms": hits,
                }
            )

    normalized_items = [
        {
            "item_id": str(row.get("item_id", "")).strip(),
            "item_name": str(row.get("item_name", "")).strip(),
            "unit_id": str(row.get("unit_id", "")).strip(),
            "unit_name": str(row.get("unit_name", "")).strip(),
        }
        for row in items
    ]
    normalized_items.sort(key=lambda row: (str(row["item_id"]), str(row["unit_id"])))
    matched.sort(
        key=lambda row: tuple(str(value) for value in cast(list[str], row["classification_ids"]))
    )

    return {
        "status": "inventory_inspected",
        "artifact_id": str(pointer.get("artifact_id", "")).strip(),
        "org_id": str(pointer.get("org_id", "")).strip(),
        "table_id": str(pointer.get("table_id", "")).strip(),
        "periods": _string_list(pointer.get("periods")),
        "item_count": len(normalized_items),
        "classification_count": len(classifications),
        "match_terms": list(normalized_terms),
        "matched_classification_count": len(matched),
        "items": normalized_items,
        "matched_classifications": matched,
        "revision_sensitive": pointer.get("revision_sensitive") is True,
        "historical_vintage_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kosis-inventory",
        description=(
            "Inspect the latest captured KOSIS industry parameter inventory without "
            "making another network request"
        ),
    )
    parser.add_argument("--pointer", type=Path, default=DEFAULT_POINTER)
    parser.add_argument(
        "--match",
        action="append",
        dest="match_terms",
        help="classification name substring to match; repeat for additional terms",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        terms = tuple(args.match_terms) if args.match_terms else DEFAULT_MATCH_TERMS
        result = inspect_latest_inventory(pointer_path=args.pointer, match_terms=terms)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
