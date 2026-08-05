"""Exact-snapshot market consistency gate for live and resumed decisions."""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from alpha_cycle import market_consistency_cli as core
from alpha_cycle import market_consistency_integrity as raw_integrity
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
    load_market_consistency_provenance,
)
from alpha_cycle.market_consistency_assessment_integrity import (
    assess_consistency_result,
)
from alpha_cycle.market_consistency_runner_cli import MarketScopeAssessment

DEFAULT_REQUIRED_DAYS = 20
DEFAULT_PRICE_TOLERANCE_WON = Decimal(0)
DEFAULT_LIVE_TOLERANCE_BPS = Decimal(50)
DEFAULT_MAX_SNAPSHOT_AGE_MINUTES = 30
DEFAULT_MAX_CAPTURE_GAP_SECONDS = 60


@dataclass(frozen=True)
class PipelineMarketConsistencyGate:
    """Validated gate artifacts and decision-consumable provenance."""

    raw_result: core.ConsistencyResult
    raw_result_path: Path
    assessment: MarketScopeAssessment
    assessment_path: Path
    provenance: MarketConsistencyProvenance


def _checked_at(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise core.ConsistencyError("pipeline consistency clock must be timezone-aware")
    return result.astimezone(UTC)


def _json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise core.ConsistencyError(f"JSON object required: {path}")
    return cast(dict[str, object], payload)


def _same_path(value: object, expected: Path, field: str) -> None:
    candidate = Path(str(value))
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if candidate.resolve() != expected.resolve():
        raise core.ConsistencyError(f"{field} changed before provenance binding")


def _write_failed_scope_pointer(
    *,
    output_root: Path,
    failure: BaseException,
    checked_at: datetime,
    raw_result: core.ConsistencyResult | None = None,
    raw_result_path: Path | None = None,
) -> None:
    """Replace any prior passing scope pointer with current failed state."""

    payload: dict[str, object] = {
        "status": "failed_assessment",
        "classification": "assessment_error",
        "assessment_id": None,
        "assessment_path": None,
        "raw_result_id": None if raw_result is None else raw_result.result_id,
        "raw_result_path": (
            None if raw_result_path is None else str(raw_result_path)
        ),
        "checked_at_utc": checked_at.astimezone(UTC).isoformat(),
        "failure": str(failure),
        "decision_integration_eligible": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    try:
        raw_integrity._atomic_json(
            output_root / "latest_market_scope_assessment.json",
            payload,
        )
    except OSError:
        return


def _write_raw_and_scope_failure(
    *,
    output_root: Path,
    failure: BaseException,
    checked_at: datetime,
) -> None:
    raw_integrity._write_failed_pointer(output_root, failure, checked_at)
    _write_failed_scope_pointer(
        output_root=output_root,
        failure=failure,
        checked_at=checked_at,
    )


def _explicit_evidence(
    *,
    output_root: Path,
    market_directory: Path,
) -> raw_integrity.PinnedEvidence:
    try:
        toss_directory = market_directory.resolve(strict=True)
    except OSError as exc:
        raise core.ConsistencyError(
            f"explicit market snapshot directory is unavailable: {market_directory}"
        ) from exc
    if not toss_directory.is_dir():
        raise core.ConsistencyError(
            f"explicit market snapshot is not a directory: {toss_directory}"
        )
    raw_integrity._validate_unique_rows(
        toss_directory / "prices.csv",
        symbol_field="symbol",
        provider="TossInvest",
    )
    kiwoom_directory = core._resolve_kiwoom_directory(output_root).resolve(strict=True)
    raw_integrity._validate_unique_rows(
        kiwoom_directory / "quotes.csv",
        symbol_field="ticker",
        provider="Kiwoom",
    )
    return raw_integrity.PinnedEvidence(
        toss_directory=toss_directory,
        toss_resolution_source="explicit_pipeline_market_directory",
        kiwoom_directory=kiwoom_directory,
    )


def _load_exact_provenance(
    *,
    root: Path,
    raw_result: core.ConsistencyResult,
    raw_result_path: Path,
    assessment: MarketScopeAssessment,
    assessment_path: Path,
    decision_symbols: tuple[str, ...],
) -> MarketConsistencyProvenance:
    """Verify latest IDs once, then load only isolated copies of those artifacts."""

    raw_pointer_path = root / "latest_market_consistency.json"
    scope_pointer_path = root / "latest_market_scope_assessment.json"
    raw_pointer = _json_object(raw_pointer_path)
    scope_pointer = _json_object(scope_pointer_path)
    if raw_pointer.get("result_id") != raw_result.result_id:
        raise core.ConsistencyError("latest raw result changed before provenance binding")
    if raw_pointer.get("assessment_id") != assessment.assessment_id:
        raise core.ConsistencyError("latest assessment changed before provenance binding")
    if scope_pointer.get("assessment_id") != assessment.assessment_id:
        raise core.ConsistencyError("scope assessment pointer changed before provenance binding")
    _same_path(raw_pointer.get("result_path"), raw_result_path, "result_path")
    _same_path(raw_pointer.get("assessment_path"), assessment_path, "assessment_path")
    _same_path(scope_pointer.get("raw_result_path"), raw_result_path, "raw_result_path")
    _same_path(scope_pointer.get("assessment_path"), assessment_path, "scope assessment_path")

    with tempfile.TemporaryDirectory(prefix="pipeline-provenance-") as isolated_text:
        isolated = Path(isolated_text)
        isolated_result = isolated / "consistency.json"
        isolated_assessment = isolated / "market_scope_assessment.json"
        shutil.copy2(raw_result_path, isolated_result)
        shutil.copy2(assessment_path, isolated_assessment)
        raw_pointer["result_path"] = str(isolated_result)
        raw_pointer["assessment_path"] = str(isolated_assessment)
        scope_pointer["raw_result_path"] = str(isolated_result)
        scope_pointer["assessment_path"] = str(isolated_assessment)
        (isolated / "latest_market_consistency.json").write_text(
            json.dumps(raw_pointer, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (isolated / "latest_market_scope_assessment.json").write_text(
            json.dumps(scope_pointer, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        provenance = load_market_consistency_provenance(
            isolated,
            market_snapshot_id=raw_result.toss_snapshot_id,
            decision_symbols=decision_symbols,
        )
    return replace(
        provenance,
        result_path=str(raw_result_path),
        assessment_path=str(assessment_path),
    )


def run_pipeline_market_consistency_gate(
    *,
    output_root: str | Path,
    market_directory: str | Path,
    decision_symbols: tuple[str, ...],
    required_days: int = DEFAULT_REQUIRED_DAYS,
    price_tolerance_won: Decimal = DEFAULT_PRICE_TOLERANCE_WON,
    live_tolerance_bps: Decimal = DEFAULT_LIVE_TOLERANCE_BPS,
    max_snapshot_age_minutes: int = DEFAULT_MAX_SNAPSHOT_AGE_MINUTES,
    max_capture_gap_seconds: int = DEFAULT_MAX_CAPTURE_GAP_SECONDS,
    now: datetime | None = None,
) -> PipelineMarketConsistencyGate:
    """Assess one exact Toss snapshot and block non-equivalent decision evidence."""

    root = Path(output_root)
    checked_at = _checked_at(now)
    if not decision_symbols:
        raise core.ConsistencyError("decision_symbols cannot be empty")
    if not price_tolerance_won.is_finite() or not live_tolerance_bps.is_finite():
        raise core.ConsistencyError("tolerances must be finite decimals")
    if price_tolerance_won < 0 or live_tolerance_bps < 0:
        raise core.ConsistencyError("tolerances cannot be negative")
    if required_days <= 0:
        raise core.ConsistencyError("required_days must be positive")
    if max_snapshot_age_minutes <= 0 or max_capture_gap_seconds <= 0:
        raise core.ConsistencyError("freshness limits must be positive")

    try:
        evidence = _explicit_evidence(
            output_root=root,
            market_directory=Path(market_directory),
        )
        staging_parent = root / ".market-consistency-staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="pipeline-",
            dir=staging_parent,
        ) as staging_text:
            raw_result, staged_path = raw_integrity._run_core_with_pinned_evidence(
                staging_root=Path(staging_text),
                evidence=evidence,
                required_days=required_days,
                price_tolerance_won=price_tolerance_won,
                live_tolerance_bps=live_tolerance_bps,
                max_snapshot_age_minutes=max_snapshot_age_minutes,
                max_capture_gap_seconds=max_capture_gap_seconds,
                checked_at=checked_at,
            )
            raw_result_path = raw_integrity._publish_result(
                output_root=root,
                result=raw_result,
                staging_result_path=staged_path,
                checked_at=checked_at,
            )
    except csv.Error as exc:
        failure = core.ConsistencyError(f"malformed pipeline market evidence: {exc}")
        _write_raw_and_scope_failure(
            output_root=root,
            failure=failure,
            checked_at=checked_at,
        )
        raise failure from exc
    except (core.ConsistencyError, OSError, TypeError, ValueError) as exc:
        _write_raw_and_scope_failure(
            output_root=root,
            failure=exc,
            checked_at=checked_at,
        )
        raise

    try:
        assessment, assessment_path = assess_consistency_result(
            raw_result,
            raw_result_path,
            output_root=root,
        )
    except (csv.Error, core.ConsistencyError, OSError, TypeError, ValueError) as exc:
        _write_failed_scope_pointer(
            output_root=root,
            failure=exc,
            checked_at=checked_at,
            raw_result=raw_result,
            raw_result_path=raw_result_path,
        )
        raise

    try:
        provenance = _load_exact_provenance(
            root=root,
            raw_result=raw_result,
            raw_result_path=raw_result_path,
            assessment=assessment,
            assessment_path=assessment_path,
            decision_symbols=decision_symbols,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise core.ConsistencyError(
            f"market consistency blocks investment decision: {exc}"
        ) from exc
    return PipelineMarketConsistencyGate(
        raw_result=raw_result,
        raw_result_path=raw_result_path,
        assessment=assessment,
        assessment_path=assessment_path,
        provenance=provenance,
    )


__all__ = [
    "PipelineMarketConsistencyGate",
    "run_pipeline_market_consistency_gate",
]
