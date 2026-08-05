"""Exact-snapshot market consistency gate for live and resumed decisions."""

from __future__ import annotations

import csv
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

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
        raw_integrity._write_failed_pointer(root, failure, checked_at)
        raise failure from exc
    except (core.ConsistencyError, OSError, TypeError, ValueError) as exc:
        raw_integrity._write_failed_pointer(root, exc, checked_at)
        raise

    assessment, assessment_path = assess_consistency_result(
        raw_result,
        raw_result_path,
        output_root=root,
    )
    try:
        provenance = load_market_consistency_provenance(
            root,
            market_snapshot_id=raw_result.toss_snapshot_id,
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
