"""Compare distinct normalized KIS forward estimate snapshots without consensus claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.kis_forward_estimates import read_json_object

DEFAULT_FORWARD_ROOT = Path("data/private/live-research/kis-forward-estimates")
DEFAULT_OUTPUT_ROOT = Path("data/private/live-research/kis-forward-estimate-changes")
LATEST_POINTER_NAME = "latest_kis_forward_estimate_changes.json"
SCHEMA_VERSION = 1
KEY_COLUMNS = ("symbol", "metric", "period_label")
REQUIRED_FORWARD_COLUMNS = {
    *KEY_COLUMNS,
    "fiscal_year",
    "value_krw",
    "unit",
    "historical_semantic_crosscheck_verified",
    "provider_semantics_certified",
    "consensus_certified",
    "revision_certified",
    "decision_score_enabled",
}


@dataclass(frozen=True)
class ForwardArtifact:
    directory: Path
    artifact_id: str
    source_expectation_snapshot_id: str
    source_expectation_captured_at: datetime
    binding_signature: str
    frame: pd.DataFrame


def _sha256(value: object, field: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _strict_false(mapping: Mapping[str, object], key: str, *, label: str) -> None:
    if mapping.get(key) is not False:
        raise ValueError(f"{label} must keep {key}=false")


def _strict_true(mapping: Mapping[str, object], key: str, *, label: str) -> None:
    if mapping.get(key) is not True:
        raise ValueError(f"{label} must keep {key}=true")


def _aware_datetime(value: object, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


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


def _binding_signature(path: Path) -> str:
    binding = read_json_object(path, label="KIS forward semantic binding")
    metrics_raw = binding.get("metrics")
    if not isinstance(metrics_raw, list) or not metrics_raw:
        raise ValueError("KIS forward semantic binding is missing metrics")
    metrics: list[dict[str, object]] = []
    for index, raw in enumerate(metrics_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"KIS forward semantic binding metric #{index} is invalid")
        metric = {
            "metric": str(raw.get("metric", "")).strip(),
            "output_name": str(raw.get("output_name", "")).strip(),
            "row_number_1_based": raw.get("row_number_1_based"),
            "scale_to_krw": raw.get("scale_to_krw"),
        }
        if not metric["metric"] or not metric["output_name"]:
            raise ValueError("KIS forward semantic binding metric is incomplete")
        metrics.append(metric)
    structural = {
        "binding_version": binding.get("binding_version"),
        "verified_symbols": binding.get("verified_symbols"),
        "period_field_policy": binding.get("period_field_policy"),
        "metrics": sorted(metrics, key=lambda item: str(item["metric"])),
        "owner_reference_account_id": binding.get("owner_reference_account_id"),
    }
    return hashlib.sha256(_canonical_json(structural).encode("utf-8")).hexdigest()


def _flag_series(frame: pd.DataFrame, column: str, expected: bool) -> None:
    if column not in frame.columns:
        raise ValueError(f"Forward estimate frame is missing {column}")
    values = frame[column]
    normalized = values.map(
        lambda value: value
        if isinstance(value, bool)
        else str(value).strip().casefold() in {"true", "1"}
    )
    if not normalized.eq(expected).all():
        raise ValueError(f"Forward estimate frame must keep {column}={str(expected).lower()}")


def _load_forward_artifact(directory: Path) -> ForwardArtifact:
    manifest = read_json_object(directory / "manifest.json", label="KIS forward manifest")
    if manifest.get("status") != "forward_estimate_levels_normalized":
        raise ValueError("KIS forward manifest status is not normalized")
    _strict_true(
        manifest,
        "historical_semantic_crosscheck_verified",
        label="KIS forward manifest",
    )
    _strict_true(manifest, "forward_values_normalized", label="KIS forward manifest")
    for key in (
        "provider_semantics_certified",
        "consensus_certified",
        "revision_certified",
        "point_in_time_backtest_eligible",
        "decision_score_enabled",
        "account_api_enabled",
        "holdings_api_enabled",
        "balance_api_enabled",
        "order_api_enabled",
    ):
        _strict_false(manifest, key, label="KIS forward manifest")
    artifact_id = _sha256(manifest.get("artifact_id"), "forward artifact_id")
    source_id = _sha256(
        manifest.get("source_expectation_snapshot_id"),
        "source_expectation_snapshot_id",
    )
    source_captured = _aware_datetime(
        manifest.get("source_expectation_captured_at"),
        field="source_expectation_captured_at",
    )
    binding_path = directory / "semantic_binding.json"
    forward_path = directory / "forward_estimates.csv"
    if not binding_path.is_file() or not forward_path.is_file():
        raise ValueError("KIS forward artifact is incomplete")
    frame = pd.read_csv(forward_path, dtype={"symbol": "string"})
    missing = REQUIRED_FORWARD_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Forward estimate frame is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Forward estimate frame is empty")
    frame["symbol"] = frame["symbol"].astype("string").str.zfill(6)
    frame["metric"] = frame["metric"].astype("string")
    frame["period_label"] = frame["period_label"].astype("string")
    frame["value_krw"] = pd.to_numeric(frame["value_krw"], errors="raise")
    if not frame["value_krw"].map(lambda value: math.isfinite(float(value))).all():
        raise ValueError("Forward estimate values must be finite")
    if frame.duplicated(list(KEY_COLUMNS)).any():
        raise ValueError("Forward estimate frame has duplicate comparison keys")
    if not frame["unit"].astype(str).eq("KRW").all():
        raise ValueError("Forward estimate values must use KRW")
    _flag_series(frame, "historical_semantic_crosscheck_verified", True)
    for column in (
        "provider_semantics_certified",
        "consensus_certified",
        "revision_certified",
        "decision_score_enabled",
    ):
        _flag_series(frame, column, False)
    return ForwardArtifact(
        directory=directory,
        artifact_id=artifact_id,
        source_expectation_snapshot_id=source_id,
        source_expectation_captured_at=source_captured,
        binding_signature=_binding_signature(binding_path),
        frame=frame.sort_values(list(KEY_COLUMNS), kind="stable").reset_index(drop=True),
    )


def _forward_artifacts(root: Path) -> list[ForwardArtifact]:
    if not root.is_dir():
        raise ValueError(f"Forward estimate root does not exist: {root}")
    loaded: list[ForwardArtifact] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        if not (directory / "manifest.json").is_file():
            continue
        loaded.append(_load_forward_artifact(directory))
    if not loaded:
        raise ValueError("No complete normalized KIS forward artifacts were found")

    latest_by_source: dict[str, ForwardArtifact] = {}
    for item in loaded:
        existing = latest_by_source.get(item.source_expectation_snapshot_id)
        if existing is None or item.directory.name > existing.directory.name:
            latest_by_source[item.source_expectation_snapshot_id] = item
    result = sorted(
        latest_by_source.values(),
        key=lambda item: (
            item.source_expectation_captured_at,
            item.source_expectation_snapshot_id,
        ),
    )
    for previous, current in zip(result, result[1:], strict=False):
        if current.source_expectation_captured_at <= previous.source_expectation_captured_at:
            raise ValueError("Distinct KIS source snapshots must have increasing capture times")
    return result


def _direction(previous: float, current: float) -> str:
    tolerance = max(abs(previous), abs(current), 1.0) * 1e-12
    difference = current - previous
    if abs(difference) <= tolerance:
        return "unchanged"
    return "up" if difference > 0 else "down"


def _comparison_rows(
    previous: ForwardArtifact,
    current: ForwardArtifact,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    if previous.binding_signature != current.binding_signature:
        raise ValueError("KIS forward semantic binding changed between compared snapshots")
    previous_frame = previous.frame.loc[:, [*KEY_COLUMNS, "value_krw"]].rename(
        columns={"value_krw": "previous_value_krw"}
    )
    current_frame = current.frame.loc[:, [*KEY_COLUMNS, "value_krw"]].rename(
        columns={"value_krw": "current_value_krw"}
    )
    previous_keys = {
        "|".join(str(raw[column]) for column in KEY_COLUMNS)
        for raw in previous_frame.to_dict(orient="records")
    }
    current_keys = {
        "|".join(str(raw[column]) for column in KEY_COLUMNS)
        for raw in current_frame.to_dict(orient="records")
    }
    common = previous_frame.merge(
        current_frame,
        on=list(KEY_COLUMNS),
        how="inner",
        validate="one_to_one",
    )
    if common.empty:
        raise ValueError("KIS forward snapshots have no common issuer/metric/period rows")
    rows: list[dict[str, object]] = []
    for raw in common.to_dict(orient="records"):
        previous_value = float(raw["previous_value_krw"])
        current_value = float(raw["current_value_krw"])
        absolute = current_value - previous_value
        pct = (
            absolute / abs(previous_value) * 100.0
            if previous_value != 0
            else None
        )
        rows.append(
            {
                "symbol": str(raw["symbol"]).zfill(6),
                "metric": str(raw["metric"]),
                "period_label": str(raw["period_label"]),
                "previous_value_krw": previous_value,
                "current_value_krw": current_value,
                "absolute_change_krw": absolute,
                "percent_change": None if pct is None else round(pct, 8),
                "direction": _direction(previous_value, current_value),
                "unit": "KRW",
                "estimate_snapshot_change_verified": True,
                "provider_semantics_certified": False,
                "consensus_certified": False,
                "consensus_revision_certified": False,
                "revision_certified": False,
                "decision_score_enabled": False,
            }
        )
    changes = pd.DataFrame(rows).sort_values(list(KEY_COLUMNS), kind="stable").reset_index(drop=True)
    return changes, sorted(previous_keys - current_keys), sorted(current_keys - previous_keys)


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


def run_revision_tracker(
    *,
    forward_root: Path,
    output_root: Path,
    now: datetime,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Revision tracker clock must be timezone-aware")
    artifacts = _forward_artifacts(forward_root)
    current = artifacts[-1]
    captured_at = now.astimezone(UTC)

    if len(artifacts) == 1:
        status = "estimate_change_baseline_only"
        previous: ForwardArtifact | None = None
        changes = pd.DataFrame(
            columns=[
                *KEY_COLUMNS,
                "previous_value_krw",
                "current_value_krw",
                "absolute_change_krw",
                "percent_change",
                "direction",
                "unit",
                "estimate_snapshot_change_verified",
                "provider_semantics_certified",
                "consensus_certified",
                "consensus_revision_certified",
                "revision_certified",
                "decision_score_enabled",
            ]
        )
        dropped: list[str] = []
        added: list[str] = []
        estimate_change_verified = False
    else:
        previous = artifacts[-2]
        changes, dropped, added = _comparison_rows(previous, current)
        status = "estimate_snapshot_change_available"
        estimate_change_verified = True

    payload_without_id: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "captured_at": captured_at.isoformat(),
        "current_forward_artifact_id": current.artifact_id,
        "current_source_expectation_snapshot_id": current.source_expectation_snapshot_id,
        "current_source_expectation_captured_at": current.source_expectation_captured_at.isoformat(),
        "previous_forward_artifact_id": previous.artifact_id if previous is not None else None,
        "previous_source_expectation_snapshot_id": (
            previous.source_expectation_snapshot_id if previous is not None else None
        ),
        "previous_source_expectation_captured_at": (
            previous.source_expectation_captured_at.isoformat() if previous is not None else None
        ),
        "elapsed_hours": (
            round(
                (
                    current.source_expectation_captured_at
                    - previous.source_expectation_captured_at
                ).total_seconds()
                / 3600.0,
                6,
            )
            if previous is not None
            else None
        ),
        "binding_signature": current.binding_signature,
        "distinct_source_snapshot_count": len(artifacts),
        "common_change_row_count": len(changes),
        "dropped_keys": dropped,
        "added_keys": added,
        "changes": _records(changes),
        "historical_semantic_crosscheck_verified": True,
        "forward_values_normalized": True,
        "estimate_snapshot_change_verified": estimate_change_verified,
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "consensus_revision_certified": False,
        "revision_certified": False,
        "point_in_time_backtest_eligible": False,
        "decision_score_enabled": False,
    }
    artifact_id = hashlib.sha256(_canonical_json(payload_without_id).encode("utf-8")).hexdigest()
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        changes.to_csv(temporary / "estimate_changes.csv", index=False)
        manifest = {key: value for key, value in payload_without_id.items() if key != "changes"}
        manifest["artifact_id"] = artifact_id
        manifest["files"] = ["estimate_changes.csv"]
        _write_json(temporary / "manifest.json", manifest)
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "status": status,
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "estimate_changes_path": str((directory / "estimate_changes.csv").resolve()),
        "current_source_expectation_snapshot_id": current.source_expectation_snapshot_id,
        "previous_source_expectation_snapshot_id": (
            previous.source_expectation_snapshot_id if previous is not None else None
        ),
        "distinct_source_snapshot_count": len(artifacts),
        "estimate_snapshot_change_verified": estimate_change_verified,
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "consensus_revision_certified": False,
        "revision_certified": False,
        "decision_score_enabled": False,
    }
    _write_json(output_root / LATEST_POINTER_NAME, pointer, ensure_ascii=True)
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kis-forward-estimate-revisions",
        description=(
            "Compare the two latest distinct normalized KIS forward snapshots. "
            "Changes describe the observed KIS estimate series, not market consensus revisions."
        ),
    )
    parser.add_argument("--forward-root", type=Path, default=DEFAULT_FORWARD_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        payload = run_revision_tracker(
            forward_root=args.forward_root,
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
