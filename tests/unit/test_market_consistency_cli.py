"""Tests for TossInvest/Kiwoom immutable market-evidence consistency."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from alpha_cycle.market_consistency_cli import run_consistency_check

SYMBOLS = ("000660", "005930", "005935")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _daily_dates(end: date, count: int = 25) -> list[date]:
    return [end - timedelta(days=index) for index in range(count)]


def _build_toss(
    root: Path,
    *,
    captured_at: datetime,
    conflict: tuple[str, date] | None = None,
    volume_offset: int = 0,
) -> Path:
    directory = root / "market-intelligence" / "toss-snapshot"
    directory.mkdir(parents=True)
    snapshot_id = "toss-snapshot-id"
    _write_json(
        directory / "manifest.json",
        {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "captured_at": captured_at.isoformat(),
            "provider": "tossinvest-readonly",
            "interval": "1d",
            "adjusted": False,
            "symbols": list(SYMBOLS),
            "files": ["prices.csv", "candles.csv"],
            "order_api_enabled": False,
        },
    )
    _write_csv(
        directory / "prices.csv",
        [
            {
                "symbol": symbol,
                "timestamp": captured_at.isoformat(),
                "last_price": str(100000 + index * 10000),
                "currency": "KRW",
            }
            for index, symbol in enumerate(SYMBOLS)
        ],
    )
    rows: list[dict[str, object]] = []
    dates = _daily_dates(date(2026, 8, 2))
    for symbol_index, symbol in enumerate(SYMBOLS):
        base = Decimal(100000 + symbol_index * 10000)
        for index, candle_date in enumerate(dates):
            open_price = base - index
            if conflict == (symbol, candle_date):
                open_price += 10
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": datetime(
                        candle_date.year,
                        candle_date.month,
                        candle_date.day,
                        tzinfo=UTC,
                    ).isoformat(),
                    "open": str(open_price),
                    "high": str(base + 100 - index),
                    "low": str(base - 100 - index),
                    "close": str(base + 10 - index),
                    "volume": str(1_000_000 + index + volume_offset),
                    "currency": "KRW",
                    "interval": "1d",
                    "adjusted": False,
                }
            )
    _write_csv(directory / "candles.csv", rows)
    return directory


def _build_kiwoom(
    root: Path,
    *,
    captured_at: datetime,
    conflict: tuple[str, date] | None = None,
    volume_offset: int = 0,
) -> Path:
    market_root = root / "kiwoom-openapi-plus-market"
    directory = market_root / "kiwoom-snapshot"
    directory.mkdir(parents=True)
    snapshot_id = "kiwoom-snapshot-id"
    _write_json(
        directory / "manifest.json",
        {
            "schema_version": "1.0",
            "status": "completed",
            "provider": "kiwoom_openapi_plus",
            "snapshot_id": snapshot_id,
            "captured_at_utc": captured_at.isoformat(),
            "captured_at_kst": captured_at.astimezone(
                timezone(timedelta(hours=9))
            ).isoformat(),
            "symbols": list(SYMBOLS),
            "adjusted_prices": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        },
    )
    _write_json(
        market_root / "latest_market_export.json",
        {
            "status": "completed",
            "snapshot_id": snapshot_id,
            "export_directory": str(directory),
        },
    )
    _write_csv(
        directory / "quotes.csv",
        [
            {
                "ticker": symbol,
                "current_price": str(100000 + index * 10000),
            }
            for index, symbol in enumerate(SYMBOLS)
        ],
    )
    rows: list[dict[str, object]] = []
    dates = _daily_dates(date(2026, 8, 2))
    for symbol_index, symbol in enumerate(SYMBOLS):
        base = Decimal(100000 + symbol_index * 10000)
        for index, candle_date in enumerate(dates):
            open_price = base - index
            if conflict == (symbol, candle_date):
                open_price += 10
            rows.append(
                {
                    "ticker": symbol,
                    "date": candle_date.strftime("%Y%m%d"),
                    "open_price": str(open_price),
                    "high_price": str(base + 100 - index),
                    "low_price": str(base - 100 - index),
                    "close_price": str(base + 10 - index),
                    "volume": str(1_000_000 + index + volume_offset),
                    "adjusted": False,
                }
            )
    _write_csv(directory / "daily_bars.csv", rows)
    return directory


def _write_latest_run(root: Path, market_directory: Path, *, status: str = "completed") -> None:
    payload: dict[str, object] = {"status": status}
    if status == "completed":
        payload["market_directory"] = str(market_directory)
    _write_json(root / "latest_run.json", payload)


def test_historical_prices_pass_when_live_snapshots_are_not_comparable(
    tmp_path: Path,
) -> None:
    toss_captured = datetime(2026, 8, 3, 6, tzinfo=UTC)
    kiwoom_captured = datetime(2026, 8, 4, 3, 6, tzinfo=UTC)
    toss_directory = _build_toss(tmp_path, captured_at=toss_captured)
    _build_kiwoom(tmp_path, captured_at=kiwoom_captured, volume_offset=3)
    _write_latest_run(tmp_path, toss_directory)

    result, result_path = run_consistency_check(
        output_root=tmp_path,
        required_days=20,
        price_tolerance_won=Decimal(0),
        live_tolerance_bps=Decimal(50),
        max_snapshot_age_minutes=30,
        max_capture_gap_seconds=60,
        now=datetime(2026, 8, 4, 3, 7, tzinfo=UTC),
    )

    assert result.status == "passed_historical_only"
    assert result.historical_rows_compared == 60
    assert result.historical_price_conflict_count == 0
    assert result.historical_volume_mismatch_count == 60
    assert result.live_quote_status == "not_comparable"
    assert result.decision_integration_eligible is False
    assert result.automatic_provider_substitution_enabled is False
    assert result.order_api_enabled is False
    assert result_path.is_file()
    assert (tmp_path / "latest_market_consistency.json").is_file()


def test_fresh_aligned_quotes_enable_future_decision_integration_gate(
    tmp_path: Path,
) -> None:
    toss_captured = datetime(2026, 8, 4, 3, 6, 20, tzinfo=UTC)
    kiwoom_captured = datetime(2026, 8, 4, 3, 6, 50, tzinfo=UTC)
    toss_directory = _build_toss(tmp_path, captured_at=toss_captured)
    _build_kiwoom(tmp_path, captured_at=kiwoom_captured)
    _write_latest_run(tmp_path, toss_directory)

    result, _ = run_consistency_check(
        output_root=tmp_path,
        required_days=20,
        price_tolerance_won=Decimal(0),
        live_tolerance_bps=Decimal(50),
        max_snapshot_age_minutes=30,
        max_capture_gap_seconds=60,
        now=datetime(2026, 8, 4, 3, 7, tzinfo=UTC),
    )

    assert result.status == "passed"
    assert result.live_quote_status == "passed"
    assert result.live_quote_comparable_count == 3
    assert result.live_quote_conflict_count == 0
    assert result.decision_integration_eligible is True


def test_completed_daily_ohlc_conflict_fails_closed(tmp_path: Path) -> None:
    captured = datetime(2026, 8, 4, 3, 6, tzinfo=UTC)
    conflict = ("005930", date(2026, 8, 2))
    toss_directory = _build_toss(tmp_path, captured_at=captured)
    _build_kiwoom(tmp_path, captured_at=captured, conflict=conflict)
    _write_latest_run(tmp_path, toss_directory)

    result, _ = run_consistency_check(
        output_root=tmp_path,
        required_days=20,
        price_tolerance_won=Decimal(0),
        live_tolerance_bps=Decimal(50),
        max_snapshot_age_minutes=30,
        max_capture_gap_seconds=60,
        now=datetime(2026, 8, 4, 3, 7, tzinfo=UTC),
    )

    assert result.status == "failed"
    assert result.historical_price_conflict_count == 1
    assert result.decision_integration_eligible is False
    assert any("005930" in failure for failure in result.failures)


def test_blocked_latest_run_uses_newest_immutable_toss_snapshot(tmp_path: Path) -> None:
    captured = datetime(2026, 8, 4, 3, 6, tzinfo=UTC)
    _build_toss(tmp_path, captured_at=captured)
    _build_kiwoom(tmp_path, captured_at=captured)
    _write_latest_run(tmp_path, tmp_path / "unused", status="blocked")

    result, _ = run_consistency_check(
        output_root=tmp_path,
        required_days=20,
        price_tolerance_won=Decimal(0),
        live_tolerance_bps=Decimal(50),
        max_snapshot_age_minutes=30,
        max_capture_gap_seconds=60,
        now=datetime(2026, 8, 4, 3, 7, tzinfo=UTC),
    )

    assert result.status == "passed"
    assert result.toss_resolution_source == "latest_immutable_snapshot"
