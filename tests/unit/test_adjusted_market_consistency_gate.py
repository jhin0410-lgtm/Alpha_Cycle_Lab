"""Integration tests for adjusted-price market consistency and degraded provenance."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle import pipeline_market_consistency_degraded as degraded
from alpha_cycle.market_consistency_cli import ConsistencyError

SYMBOLS = ("000660", "005930", "005935")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _build_toss(
    root: Path,
    *,
    captured_at: datetime,
    adjusted: bool,
    row_adjusted: bool | None = None,
) -> Path:
    directory = root / "market-intelligence" / "toss-adjusted"
    directory.mkdir(parents=True)
    snapshot_id = "a" * 64
    _write_json(
        directory / "manifest.json",
        {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "captured_at": captured_at.isoformat(),
            "provider": "tossinvest-readonly",
            "interval": "1d",
            "adjusted": adjusted,
            "symbols": list(SYMBOLS),
            "files": ["prices.csv", "candles.csv", "technical_features.csv"],
            "order_api_enabled": False,
        },
    )
    _write_csv(
        directory / "prices.csv",
        [
            {
                "symbol": symbol,
                "timestamp": captured_at.isoformat(),
                "last_price": 100_000 + index * 10_000,
                "currency": "KRW",
            }
            for index, symbol in enumerate(SYMBOLS)
        ],
    )
    effective_row_basis = adjusted if row_adjusted is None else row_adjusted
    candle_day = captured_at.date() - timedelta(days=1)
    _write_csv(
        directory / "candles.csv",
        [
            {
                "symbol": symbol,
                "timestamp": datetime(
                    candle_day.year,
                    candle_day.month,
                    candle_day.day,
                    tzinfo=UTC,
                ).isoformat(),
                "open": 100_000 + index * 10_000,
                "high": 100_100 + index * 10_000,
                "low": 99_900 + index * 10_000,
                "close": 100_050 + index * 10_000,
                "volume": 1_000_000 + index,
                "currency": "KRW",
                "interval": "1d",
                "adjusted": effective_row_basis,
            }
            for index, symbol in enumerate(SYMBOLS)
        ],
    )
    return directory


def _build_kiwoom(
    root: Path,
    *,
    captured_at: datetime,
    adjusted: bool,
) -> Path:
    market_root = root / "kiwoom-openapi-plus-market"
    directory = market_root / ("kiwoom-adjusted" if adjusted else "kiwoom-legacy")
    directory.mkdir(parents=True)
    snapshot_id = "b" * 64
    manifest: dict[str, object] = {
        "schema_version": "1.2" if adjusted else "1.0",
        "status": "completed",
        "provider": "kiwoom_openapi_plus",
        "snapshot_id": snapshot_id,
        "captured_at_utc": captured_at.isoformat(),
        "captured_at_kst": captured_at.astimezone(
            timezone_kst := datetime.now().astimezone().tzinfo or UTC
        ).isoformat(),
        "symbols": list(SYMBOLS),
        "adjusted_prices": adjusted,
        "daily_tr_code": "opt10081",
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    if adjusted:
        manifest.update(
            {
                "price_basis": "adjusted",
                "adjustment_request_value": "1",
                "adjustment_evidence_file": "adjustment_evidence.csv",
            }
        )
    _write_json(directory / "manifest.json", manifest)
    _write_json(
        market_root / "latest_market_export.json",
        {
            "status": "completed",
            "provider": "kiwoom_openapi_plus",
            "snapshot_id": snapshot_id,
            "export_directory": str(directory),
        },
    )
    _write_csv(
        directory / "quotes.csv",
        [
            {"ticker": symbol, "current_price": 100_000 + index * 10_000}
            for index, symbol in enumerate(SYMBOLS)
        ],
    )
    candle_day = captured_at.date() - timedelta(days=1)
    bar_rows = [
        {
            "ticker": symbol,
            "date": candle_day.strftime("%Y%m%d"),
            "open_price": 100_000 + index * 10_000,
            "high_price": 100_100 + index * 10_000,
            "low_price": 99_900 + index * 10_000,
            "close_price": 100_050 + index * 10_000,
            "volume": 1_000_000 + index,
            "adjusted": adjusted,
        }
        for index, symbol in enumerate(SYMBOLS)
    ]
    _write_csv(directory / "daily_bars.csv", bar_rows)
    if adjusted:
        _write_csv(
            directory / "adjustment_evidence.csv",
            [
                {
                    "ticker": row["ticker"],
                    "date": row["date"],
                    "requested_price_basis": "adjusted",
                    "adjustment_request_value": "1",
                    "response_adjustment_code_raw": "",
                    "response_adjustment_ratio_raw": "",
                    "response_adjustment_event_raw": "",
                    "previous_close_raw": "",
                }
                for row in bar_rows
            ],
        )
    return directory


def test_adjusted_toss_with_legacy_kiwoom_preserves_primary_research(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 7, 6, 0, tzinfo=UTC)
    toss = _build_toss(tmp_path, captured_at=now, adjusted=True)
    _build_kiwoom(
        tmp_path,
        captured_at=now - timedelta(hours=2),
        adjusted=False,
    )

    gate = degraded.run_pipeline_market_consistency_gate(
        output_root=tmp_path,
        market_directory=toss,
        decision_symbols=("000660", "005930"),
        required_days=1,
        now=now,
    )

    assert gate.raw_result.status == "failed"
    assert gate.raw_result.historical_rows_compared == 0
    assert gate.assessment.classification == "adjustment_basis_mismatch"
    assert gate.assessment.historical_scope_status == "not_comparable"
    assert gate.provenance.mode == "primary_source_only"
    assert gate.provenance.historical_verified is False
    assert gate.provenance.live_price_certified is False
    assert "cross_provider_historical_adjustment_basis_not_comparable" in (
        gate.provenance.warnings
    )


def test_adjusted_toss_and_adjusted_kiwoom_can_be_certified(tmp_path: Path) -> None:
    now = datetime(2026, 8, 7, 6, 0, tzinfo=UTC)
    toss = _build_toss(tmp_path, captured_at=now, adjusted=True)
    _build_kiwoom(tmp_path, captured_at=now, adjusted=True)

    gate = degraded.run_pipeline_market_consistency_gate(
        output_root=tmp_path,
        market_directory=toss,
        decision_symbols=("000660", "005930"),
        required_days=1,
        now=now,
    )

    assert gate.raw_result.status == "passed"
    assert gate.raw_result.historical_rows_compared == 3
    assert gate.assessment.classification == "equivalent_scope_observed"
    assert gate.provenance.historical_verified is True
    assert gate.provenance.live_price_certified is True


def test_manifest_and_row_adjustment_basis_mismatch_fails_closed(tmp_path: Path) -> None:
    now = datetime(2026, 8, 7, 6, 0, tzinfo=UTC)
    toss = _build_toss(
        tmp_path,
        captured_at=now,
        adjusted=True,
        row_adjusted=False,
    )
    _build_kiwoom(tmp_path, captured_at=now, adjusted=True)

    with pytest.raises(ConsistencyError, match="adjustment basis differs"):
        degraded.run_pipeline_market_consistency_gate(
            output_root=tmp_path,
            market_directory=toss,
            decision_symbols=("000660", "005930"),
            required_days=1,
            now=now,
        )
