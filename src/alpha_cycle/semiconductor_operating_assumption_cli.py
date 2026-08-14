"""Capture internal semiconductor Bull/Base/Bear operating assumptions."""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.semiconductor_forward_input_decision_evidence import (
    load_semiconductor_forward_input_decision_evidence,
)
from alpha_cycle.intelligence.semiconductor_operating_assumptions import (
    OperatingAssumption,
    build_operating_assumption_pack,
)

DEFAULT_OUTPUT = Path("data/private/live-research/semiconductor-operating-assumptions")


def _date_value(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _load_rows(path: Path, key: str, label: str) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    values = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} requires a non-empty {key} array")
    rows: list[dict[str, object]] = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError(f"{label} rows must be objects")
        rows.append({str(k): v for k, v in cast(dict[object, object], value).items()})
    return rows


def _verified_forward_claim_ids(
    forward_input_pointer: Path,
    *,
    evaluation_date: date,
) -> tuple[str, set[str]]:
    evidence = load_semiconductor_forward_input_decision_evidence(
        forward_input_pointer,
        evaluation_date=evaluation_date,
    )
    pointer = _json_object(forward_input_pointer, "Forward-input pointer")
    claims_path = Path(str(pointer.get("claims_path", "")).strip())
    claims = _load_rows(claims_path, "claims", "Forward-input claims")
    claim_ids = {str(row.get("claim_id", "")).strip() for row in claims}
    if not claim_ids or any(
        len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
        for item in claim_ids
    ):
        raise ValueError("Forward-input claim IDs are invalid")
    return evidence.evidence_id, claim_ids


def _assumption_payload(item: OperatingAssumption) -> dict[str, object]:
    return {
        "assumption_id": item.assumption_id,
        "ticker": item.ticker,
        "block_id": item.block_id,
        "driver_id": item.driver_id,
        "scenario": item.scenario,
        "quarter_index": item.quarter_index,
        "value": item.value,
        "unit": item.unit,
        "method_id": item.method_id,
        "method_version": item.method_version,
        "method_status": item.method_status,
        "method_version_frozen": item.method_version_frozen,
        "supporting_evidence_ids": list(item.supporting_evidence_ids),
        "supporting_evidence_verified": item.supporting_evidence_verified,
        "rationale": item.rationale,
        "invalidation_condition": item.invalidation_condition,
        "evaluation_date": item.evaluation_date.isoformat(),
        "model_use_ready": item.model_use_ready,
        "source_fact": False,
        "scenario_probability_enabled": False,
        "decision_score_enabled": False,
    }


def capture_operating_assumption_pack(
    raw_assumptions: list[dict[str, object]],
    *,
    evaluation_date: date,
    horizon_quarters: int,
    forward_input_pointer: str | Path,
    output: str | Path = DEFAULT_OUTPUT,
    input_path: str | Path | None = None,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    forward_pointer = Path(forward_input_pointer)
    forward_evidence_id, verified_claim_ids = _verified_forward_claim_ids(
        forward_pointer,
        evaluation_date=evaluation_date,
    )
    pack = build_operating_assumption_pack(
        raw_assumptions,
        evaluation_date=evaluation_date,
        horizon_quarters=horizon_quarters,
        verified_evidence_ids=verified_claim_ids,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "__" + pack.pack_id[:12]
    )
    if directory.exists():
        raise ValueError(f"Operating assumption artifact already exists: {directory}")
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        (temporary / "assumptions.json").write_text(
            json.dumps(
                [_assumption_payload(item) for item in pack.assumptions],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        pack.scenario_coverage.to_csv(temporary / "scenario_coverage.csv", index=False)
        manifest = {
            "schema_version": 1,
            "status": "semiconductor_operating_assumption_pack_captured",
            "pack_id": pack.pack_id,
            "captured_at": captured.isoformat(),
            "evaluation_date": evaluation_date.isoformat(),
            "horizon_quarters": horizon_quarters,
            "assumption_count": len(pack.assumptions),
            "forward_input_evidence_id": forward_evidence_id,
            "forward_input_pointer": str(forward_pointer.resolve()),
            "input_path": str(Path(input_path).resolve()) if input_path else None,
            "source_fact": False,
            "scenario_probabilities_enabled": False,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "fair_value_estimate_enabled": False,
            "target_price_enabled": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": ["assumptions.json", "scenario_coverage.csv"],
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "schema_version": 1,
        "status": "semiconductor_operating_assumption_pack_captured",
        "pack_id": pack.pack_id,
        "evaluation_date": evaluation_date.isoformat(),
        "horizon_quarters": horizon_quarters,
        "forward_input_evidence_id": forward_evidence_id,
        "forward_input_pointer": str(forward_pointer.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "assumptions_path": str((directory / "assumptions.json").resolve()),
        "scenario_coverage_path": str((directory / "scenario_coverage.csv").resolve()),
        "source_fact": False,
        "scenario_probabilities_enabled": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = root / "latest_semiconductor_operating_assumptions.json"
    temporary_pointer = root / ".latest_semiconductor_operating_assumptions.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return {**pointer, "artifact_directory": str(directory.resolve())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-semiconductor-operating-assumptions",
        description=(
            "Capture explicit Bull/Base/Bear semiconductor operating assumptions linked to "
            "verified forward-input evidence; no scenario probabilities or forecast are enabled"
        ),
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--evaluation-date", type=_date_value, required=True)
    parser.add_argument("--horizon-quarters", type=int, required=True)
    parser.add_argument("--forward-input-pointer", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        result = capture_operating_assumption_pack(
            _load_rows(args.input, "assumptions", "Operating assumption input"),
            evaluation_date=args.evaluation_date,
            horizon_quarters=args.horizon_quarters,
            forward_input_pointer=args.forward_input_pointer,
            output=args.output,
            input_path=args.input,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
