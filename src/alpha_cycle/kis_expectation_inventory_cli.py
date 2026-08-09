"""Inspect local KIS estimate-perform payload structure without assigning semantics."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from alpha_cycle.providers.kis_research import KIS_RESEARCH_SOURCE_SCOPE

DEFAULT_OUTPUT_ROOT = Path("data/private/live-research/expectation-intelligence")
_REQUIRED_FILES = ("manifest.json", "raw_estimate_perform.json")
_FORBIDDEN_KEY_PARTS = (
    "access_token",
    "authorization",
    "appkey",
    "appsecret",
    "password",
    "account",
    "cano",
    "acnt",
)


def _read_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): item for key, item in value.items()}


def _latest_snapshot(root: Path) -> tuple[Path, dict[str, object]]:
    if not root.is_dir():
        raise ValueError(f"Expectation output root does not exist: {root}")
    for directory in sorted(root.iterdir(), reverse=True):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        if not all((directory / name).is_file() for name in _REQUIRED_FILES):
            continue
        try:
            manifest = _read_object(directory / "manifest.json", label="expectation manifest")
        except ValueError:
            continue
        if (
            manifest.get("provider") == "korea_investment_openapi"
            and manifest.get("source_scope") == KIS_RESEARCH_SOURCE_SCOPE
            and manifest.get("semantic_status") == "raw_structure_only"
        ):
            return directory, manifest
    raise ValueError("No complete semantically-unclassified KIS expectation snapshot was found")


def _strict_false(mapping: Mapping[str, object], key: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"Expectation manifest must keep {key}=false")


def _walk_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            text = str(key)
            keys.append(text)
            keys.extend(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys


def _reject_sensitive_response_keys(raw: Mapping[str, object]) -> None:
    for key in _walk_keys(raw):
        normalized = key.casefold().replace("-", "_")
        if any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
            raise ValueError(
                "KIS estimate response unexpectedly contains a sensitive-looking key: "
                f"{key}"
            )


def _rows(value: object, *, output_name: str) -> tuple[str, list[Mapping[str, object]]]:
    if isinstance(value, dict):
        return "object", [cast(Mapping[str, object], value)]
    if isinstance(value, list):
        rows: list[Mapping[str, object]] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise ValueError(f"{output_name}[{index}] must be an object")
            rows.append(cast(Mapping[str, object], item))
        return "array", rows
    raise ValueError(f"{output_name} must be an object or array")


def _public_descriptors(rows: list[Mapping[str, object]], key: str) -> list[str]:
    values: list[str] = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in values:
            values.append(text)
    return values


def _output_inventory(value: object, *, output_name: str) -> dict[str, object]:
    shape, rows = _rows(value, output_name=output_name)
    keys = sorted({str(key) for row in rows for key in row})
    return {
        "shape": shape,
        "row_count": len(rows),
        "keys": keys,
        "data1_labels": _public_descriptors(rows, "data1"),
        "period_labels": _public_descriptors(rows, "dt"),
    }


def inspect_expectation_snapshot(root: Path) -> dict[str, object]:
    directory, manifest = _latest_snapshot(root)
    for key in (
        "consensus_certified",
        "revision_certified",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _strict_false(manifest, key)

    snapshot_id = str(manifest.get("snapshot_id", "")).strip()
    if len(snapshot_id) != 64 or any(ch not in "0123456789abcdef" for ch in snapshot_id):
        raise ValueError("Expectation snapshot_id must be a SHA-256 digest")
    symbols_raw = manifest.get("symbols")
    if not isinstance(symbols_raw, list) or not symbols_raw:
        raise ValueError("Expectation manifest symbols must be a non-empty array")
    symbols = tuple(sorted(str(item).zfill(6) for item in symbols_raw))
    if len(symbols) != len(set(symbols)):
        raise ValueError("Expectation manifest symbols contain duplicates")

    raw = _read_object(
        directory / "raw_estimate_perform.json",
        label="raw estimate-perform payload",
    )
    _reject_sensitive_response_keys(raw)
    if tuple(sorted(str(key).zfill(6) for key in raw)) != symbols:
        raise ValueError("Raw KIS expectation symbols do not match manifest")

    symbol_inventory: dict[str, object] = {}
    for symbol in symbols:
        payload_raw = raw.get(symbol)
        if not isinstance(payload_raw, dict):
            raise ValueError(f"Raw KIS payload for {symbol} must be an object")
        payload = cast(Mapping[str, object], payload_raw)
        outputs: dict[str, object] = {}
        for output_name in ("output1", "output2", "output3", "output4"):
            if output_name not in payload:
                raise ValueError(f"Raw KIS payload for {symbol} is missing {output_name}")
            outputs[output_name] = _output_inventory(
                payload[output_name],
                output_name=f"{symbol}.{output_name}",
            )
        symbol_inventory[symbol] = outputs

    return {
        "status": "expectation_inventory_inspected",
        "snapshot_id": snapshot_id,
        "snapshot_directory": str(directory.resolve()),
        "captured_at": str(manifest.get("captured_at", "")),
        "provider": manifest.get("provider"),
        "source_scope": manifest.get("source_scope"),
        "semantic_status": manifest.get("semantic_status"),
        "consensus_certified": False,
        "revision_certified": False,
        "decision_score_enabled": False,
        "symbols": list(symbols),
        "outputs": symbol_inventory,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kis-expectation-inventory",
        description=(
            "Inspect field names, row counts, public data1 labels, and period labels in the "
            "latest local KIS estimate-perform snapshot without assigning financial semantics"
        ),
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        payload = inspect_expectation_snapshot(args.root)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
