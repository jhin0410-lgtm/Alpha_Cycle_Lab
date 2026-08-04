"""Fail-closed integrity wrapper for the raw market consistency engine."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alpha_cycle import market_consistency_cli as core

EXPECTED_SYMBOLS = core.EXPECTED_SYMBOLS


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


def _preflight_evidence(output_root: Path) -> None:
    toss_directory, _ = core._resolve_toss_directory(output_root)
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


def _collision_free_checked_at(output_root: Path, requested: datetime) -> datetime:
    if requested.tzinfo is None or requested.utcoffset() is None:
        raise core.ConsistencyError("checker clock must be timezone-aware")
    requested = requested.astimezone(UTC)
    root = output_root / "market-source-consistency"
    for offset in range(3601):
        candidate = requested - timedelta(seconds=offset)
        timestamp = candidate.astimezone(core.KOREA_TZ).strftime("%Y%m%dT%H%M%S%z")
        if not (root / timestamp).exists():
            return candidate
    raise core.ConsistencyError(
        "could not allocate an immutable consistency result directory"
    )


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
        if not price_tolerance_won.is_finite() or not live_tolerance_bps.is_finite():
            raise core.ConsistencyError("tolerances must be finite decimals")
        _preflight_evidence(output_root)
        collision_free = _collision_free_checked_at(output_root, checked_at)
        return core.run_consistency_check(
            output_root=output_root,
            required_days=required_days,
            price_tolerance_won=price_tolerance_won,
            live_tolerance_bps=live_tolerance_bps,
            max_snapshot_age_minutes=max_snapshot_age_minutes,
            max_capture_gap_seconds=max_capture_gap_seconds,
            now=collision_free,
        )
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
