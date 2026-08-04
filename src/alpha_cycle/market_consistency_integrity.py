"""Fail-closed integrity wrapper for the raw market consistency engine."""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from alpha_cycle import market_consistency_cli as core

EXPECTED_SYMBOLS = core.EXPECTED_SYMBOLS
_TOSS_RESOLVER = "_resolve_toss_directory"
_KIWOOM_RESOLVER = "_resolve_kiwoom_directory"
_RESOLUTION_LOCK = threading.Lock()


@dataclass(frozen=True)
class PinnedEvidence:
    toss_directory: Path
    toss_resolution_source: str
    kiwoom_directory: Path


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_failed_pointer(
    output_root: Path,
    failure: BaseException,
    checked_at: datetime,
) -> None:
    payload: dict[str, object] = {
        "status": "failed_validation",
        "result_id": None,
        "checked_at_utc": checked_at.astimezone(UTC).isoformat(),
        "result_path": None,
        "decision_integration_eligible": False,
        "historical_price_conflict_count": None,
        "live_quote_status": "not_evaluated",
        "failure": str(failure),
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    try:
        _atomic_json(output_root / "latest_market_consistency.json", payload)
    except OSError:
        return


def _validate_unique_rows(
    path: Path,
    *,
    symbol_field: str,
    provider: str,
) -> None:
    rows = core._read_csv(path)
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        symbol = row.get(symbol_field, "").strip()
        if not symbol:
            raise core.ConsistencyError(
                f"{provider} live quote row has no {symbol_field}"
            )
        if symbol in seen:
            duplicates.add(symbol)
        seen.add(symbol)
    if duplicates:
        raise core.ConsistencyError(
            f"{provider} live quote evidence has duplicate symbols: "
            + ", ".join(sorted(duplicates))
        )
    if tuple(sorted(seen)) != EXPECTED_SYMBOLS:
        raise core.ConsistencyError(
            f"{provider} live quote symbol set mismatch: {tuple(sorted(seen))}"
        )


def _resolve_and_validate_evidence(output_root: Path) -> PinnedEvidence:
    toss_directory, toss_resolution = core._resolve_toss_directory(output_root)
    kiwoom_directory = core._resolve_kiwoom_directory(output_root)
    _validate_unique_rows(
        toss_directory / "prices.csv",
        symbol_field="symbol",
        provider="TossInvest",
    )
    _validate_unique_rows(
        kiwoom_directory / "quotes.csv",
        symbol_field="ticker",
        provider="Kiwoom",
    )
    return PinnedEvidence(
        toss_directory=toss_directory.resolve(),
        toss_resolution_source=toss_resolution,
        kiwoom_directory=kiwoom_directory.resolve(),
    )


def _run_core_with_pinned_evidence(
    *,
    staging_root: Path,
    evidence: PinnedEvidence,
    required_days: int,
    price_tolerance_won: Decimal,
    live_tolerance_bps: Decimal,
    max_snapshot_age_minutes: int,
    max_capture_gap_seconds: int,
    checked_at: datetime,
) -> tuple[core.ConsistencyResult, Path]:
    with _RESOLUTION_LOCK:
        original_toss: object = getattr(core, _TOSS_RESOLVER)
        original_kiwoom: object = getattr(core, _KIWOOM_RESOLVER)

        def pinned_toss(_output_root: Path) -> tuple[Path, str]:
            return evidence.toss_directory, evidence.toss_resolution_source

        def pinned_kiwoom(_output_root: Path) -> Path:
            return evidence.kiwoom_directory

        setattr(core, _TOSS_RESOLVER, pinned_toss)
        setattr(core, _KIWOOM_RESOLVER, pinned_kiwoom)
        try:
            return core.run_consistency_check(
                output_root=staging_root,
                required_days=required_days,
                price_tolerance_won=price_tolerance_won,
                live_tolerance_bps=live_tolerance_bps,
                max_snapshot_age_minutes=max_snapshot_age_minutes,
                max_capture_gap_seconds=max_capture_gap_seconds,
                now=checked_at,
            )
        finally:
            setattr(core, _TOSS_RESOLVER, original_toss)
            setattr(core, _KIWOOM_RESOLVER, original_kiwoom)


def _publish_result(
    *,
    output_root: Path,
    result: core.ConsistencyResult,
    staging_result_path: Path,
    checked_at: datetime,
) -> Path:
    destination_root = output_root / "market-source-consistency"
    destination_root.mkdir(parents=True, exist_ok=True)
    prefix = (
        checked_at.astimezone(core.KOREA_TZ).strftime("%Y%m%dT%H%M%S%f%z")
        + "__"
        + result.result_id[:12]
        + "__"
    )
    destination = Path(tempfile.mkdtemp(prefix=prefix, dir=destination_root))
    source_directory = staging_result_path.parent
    ordered_files = (
        result.daily_comparisons_file,
        result.quote_comparisons_file,
        staging_result_path.name,
    )
    for name in ordered_files:
        source = source_directory / name
        if not source.is_file():
            raise core.ConsistencyError(f"staged result artifact is missing: {source}")
        shutil.move(str(source), str(destination / name))

    result_path = destination / staging_result_path.name
    _atomic_json(
        output_root / "latest_market_consistency.json",
        {
            "status": result.status,
            "result_id": result.result_id,
            "checked_at_utc": result.checked_at_utc,
            "result_path": str(result_path),
            "decision_integration_eligible": result.decision_integration_eligible,
            "historical_price_conflict_count": (
                result.historical_price_conflict_count
            ),
            "live_quote_status": result.live_quote_status,
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        },
    )
    return result_path


def run_consistency_check(
    *,
    output_root: Path,
    required_days: int,
    price_tolerance_won: Decimal,
    live_tolerance_bps: Decimal,
    max_snapshot_age_minutes: int,
    max_capture_gap_seconds: int,
    now: datetime | None = None,
) -> tuple[core.ConsistencyResult, Path]:
    checked_at = now or datetime.now(UTC)
    try:
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise core.ConsistencyError("checker clock must be timezone-aware")
        checked_at = checked_at.astimezone(UTC)
        if not price_tolerance_won.is_finite() or not live_tolerance_bps.is_finite():
            raise core.ConsistencyError("tolerances must be finite decimals")
        if price_tolerance_won < 0 or live_tolerance_bps < 0:
            raise core.ConsistencyError("tolerances cannot be negative")

        evidence = _resolve_and_validate_evidence(output_root)
        staging_parent = output_root / ".market-consistency-staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="run-",
            dir=staging_parent,
        ) as staging_text:
            staging_root = Path(staging_text)
            result, staging_result_path = _run_core_with_pinned_evidence(
                staging_root=staging_root,
                evidence=evidence,
                required_days=required_days,
                price_tolerance_won=price_tolerance_won,
                live_tolerance_bps=live_tolerance_bps,
                max_snapshot_age_minutes=max_snapshot_age_minutes,
                max_capture_gap_seconds=max_capture_gap_seconds,
                checked_at=checked_at,
            )
            result_path = _publish_result(
                output_root=output_root,
                result=result,
                staging_result_path=staging_result_path,
                checked_at=checked_at,
            )
        return result, result_path
    except csv.Error as exc:
        failure = core.ConsistencyError(f"malformed CSV evidence: {exc}")
        _write_failed_pointer(output_root, failure, checked_at)
        raise failure from exc
    except (core.ConsistencyError, OSError, TypeError, ValueError) as exc:
        pointer_clock = (
            checked_at
            if checked_at.tzinfo is not None and checked_at.utcoffset() is not None
            else datetime.now(UTC)
        )
        _write_failed_pointer(output_root, exc, pointer_clock)
        raise


def result_json(result: core.ConsistencyResult) -> str:
    """Serialize a successful result through one production JSON path."""
    return json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True)
