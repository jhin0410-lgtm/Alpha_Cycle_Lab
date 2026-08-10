"""Normalize forward KIS estimate levels from historically crosschecked row bindings."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.kis_forward_estimates import (
    build_semantic_binding,
    latest_expectation_snapshot,
    normalize_forward_estimates,
)

DEFAULT_EXPECTATION_ROOT = Path("data/private/live-research/expectation-intelligence")
DEFAULT_GENERAL_CROSSCHECK_POINTER = Path(
    "data/private/live-research/kis-expectation-semantic-crosscheck/"
    "latest_kis_expectation_semantic_crosscheck.json"
)
DEFAULT_OWNER_CROSSCHECK_POINTER = Path(
    "data/private/live-research/kis-owner-net-income-crosscheck/"
    "latest_kis_owner_net_income_crosscheck.json"
)
DEFAULT_OUTPUT_ROOT = Path("data/private/live-research/kis-forward-estimates")
LATEST_POINTER_NAME = "latest_kis_forward_estimates.json"
SCHEMA_VERSION = 1


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in frame.to_dict(orient="records"):
        row: dict[str, object] = {}
        for key, value in raw.items():
            if pd.isna(value):
                row[str(key)] = None
            elif hasattr(value, "item"):
                row[str(key)] = value.item()
            else:
                row[str(key)] = value
        rows.append(row)
    return rows


def _write_json(path: Path, value: object, *, ensure_ascii: bool = False) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def run_normalization(
    *,
    expectation_root: Path,
    general_crosscheck_pointer: Path,
    owner_crosscheck_pointer: Path,
    output_root: Path,
    now: datetime,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Forward normalization clock must be timezone-aware")

    binding = build_semantic_binding(
        general_crosscheck_pointer=general_crosscheck_pointer,
        owner_crosscheck_pointer=owner_crosscheck_pointer,
    )
    expectation_directory, _ = latest_expectation_snapshot(expectation_root)
    source_snapshot_id, source_captured_at, forward, summary = normalize_forward_estimates(
        expectation_directory=expectation_directory,
        binding=binding,
    )
    captured_at = now.astimezone(UTC)
    binding_payload = binding.as_dict()
    forward_records = _records(forward)
    summary_records = _records(summary)
    payload_without_id: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": "forward_estimate_levels_normalized",
        "captured_at": captured_at.isoformat(),
        "source_expectation_snapshot_id": source_snapshot_id,
        "source_expectation_captured_at": source_captured_at.isoformat(),
        "binding_evidence_expectation_snapshot_id": (
            binding.evidence_expectation_snapshot_id
        ),
        "binding_evidence_valuation_snapshot_id": binding.evidence_valuation_snapshot_id,
        "general_crosscheck_artifact_id": binding.general_crosscheck_artifact_id,
        "owner_crosscheck_artifact_id": binding.owner_crosscheck_artifact_id,
        "binding": binding_payload,
        "symbols": sorted(forward["symbol"].astype(str).unique().tolist()),
        "metrics": sorted(forward["metric"].astype(str).unique().tolist()),
        "forecast_period_labels": sorted(
            forward["period_label"].astype(str).unique().tolist()
        ),
        "forward_estimates": forward_records,
        "forward_summary": summary_records,
        "historical_semantic_crosscheck_verified": True,
        "forward_values_normalized": True,
        "estimate_snapshot_change_available": False,
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "point_in_time_backtest_eligible": False,
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    artifact_id = hashlib.sha256(
        _canonical_json(payload_without_id).encode("utf-8")
    ).hexdigest()
    artifact = {**payload_without_id, "artifact_id": artifact_id}
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    if directory.exists():
        raise ValueError(f"Forward estimate artifact already exists: {directory}")
    temporary = output_root / f".{directory.name}.tmp"
    output_root.mkdir(parents=True, exist_ok=True)
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        forward.to_csv(temporary / "forward_estimates.csv", index=False)
        summary.to_csv(temporary / "forward_summary.csv", index=False)
        _write_json(temporary / "semantic_binding.json", binding_payload)
        manifest = {
            key: value
            for key, value in artifact.items()
            if key not in {"forward_estimates", "forward_summary", "binding"}
        }
        manifest["files"] = [
            "forward_estimates.csv",
            "forward_summary.csv",
            "semantic_binding.json",
        ]
        _write_json(temporary / "manifest.json", manifest)
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "status": "forward_estimate_levels_normalized",
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "forward_estimates_path": str((directory / "forward_estimates.csv").resolve()),
        "forward_summary_path": str((directory / "forward_summary.csv").resolve()),
        "semantic_binding_path": str((directory / "semantic_binding.json").resolve()),
        "source_expectation_snapshot_id": source_snapshot_id,
        "source_expectation_captured_at": source_captured_at.isoformat(),
        "symbols": artifact["symbols"],
        "forecast_period_labels": artifact["forecast_period_labels"],
        "historical_semantic_crosscheck_verified": True,
        "forward_values_normalized": True,
        "estimate_snapshot_change_available": False,
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "decision_score_enabled": False,
    }
    _write_json(output_root / LATEST_POINTER_NAME, pointer, ensure_ascii=True)
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kis-forward-estimates",
        description=(
            "Normalize KIS 2026E/2027E-style forward levels only from historically "
            "crosschecked row/scale bindings; do not claim consensus provenance or score them."
        ),
    )
    parser.add_argument("--expectation-root", type=Path, default=DEFAULT_EXPECTATION_ROOT)
    parser.add_argument(
        "--general-crosscheck-pointer",
        type=Path,
        default=DEFAULT_GENERAL_CROSSCHECK_POINTER,
    )
    parser.add_argument(
        "--owner-crosscheck-pointer",
        type=Path,
        default=DEFAULT_OWNER_CROSSCHECK_POINTER,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        payload = run_normalization(
            expectation_root=args.expectation_root,
            general_crosscheck_pointer=args.general_crosscheck_pointer,
            owner_crosscheck_pointer=args.owner_crosscheck_pointer,
            output_root=args.output,
            now=datetime.now(UTC),
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError) as exc:
        print(
            json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
