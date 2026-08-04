"""Tests for explaining fail-closed market-source conflicts."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from alpha_cycle.market_consistency_diagnostics_cli import (
    diagnose_latest_consistency,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _result_id(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _row(
    ticker: str,
    candle_date: str,
    toss: tuple[int, int, int, int, int],
    kiwoom: tuple[int, int, int, int, int],
) -> dict[str, object]:
    price_match = toss[:4] == kiwoom[:4]
    return {
        "ticker": ticker,
        "date": candle_date,
        "toss_open": toss[0],
        "kiwoom_open": kiwoom[0],
        "toss_high": toss[1],
        "kiwoom_high": kiwoom[1],
        "toss_low": toss[2],
        "kiwoom_low": kiwoom[2],
        "toss_close": toss[3],
        "kiwoom_close": kiwoom[3],
        "toss_volume": toss[4],
        "kiwoom_volume": kiwoom[4],
        "max_price_difference_won": max(
            abs(toss[index] - kiwoom[index]) for index in range(4)
        ),
        "price_match": price_match,
        "volume_match": toss[4] == kiwoom[4],
        "volume_difference_bps": "0",
    }


def _write_artifacts(tmp_path: Path) -> Path:
    result_directory = tmp_path / "market-source-consistency" / "run"
    result_directory.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    for index, candle_date in enumerate(("2026-08-01", "2026-07-31", "2026-07-30")):
        first = (100 + index, 110 + index, 90 + index, 105 + index, 1000 + index)
        second = (200 + index, 210 + index, 190 + index, 205 + index, 2000 + index)
        third = (300 + index, 310 + index, 290 + index, 305 + index, 3000 + index)
        rows.extend(
            (
                _row("000660", candle_date, first, second),
                _row("005930", candle_date, second, first),
                _row("005935", candle_date, third, third),
            )
        )
    _write_csv(result_directory / "daily_price_comparisons.csv", rows)

    result_payload: dict[str, object] = {
        "schema_version": "1.0",
        "status": "failed",
        "checked_at_utc": "2026-08-04T08:00:00+00:00",
        "checked_at_kst": "2026-08-04T17:00:00+09:00",
        "expected_symbols": ["000660", "005930", "005935"],
        "toss_snapshot_id": "toss",
        "toss_captured_at": "2026-08-04T07:00:00+00:00",
        "toss_snapshot_age_seconds": 3600.0,
        "toss_directory": "toss",
        "toss_resolution_source": "latest_immutable_snapshot",
        "kiwoom_snapshot_id": "kiwoom",
        "kiwoom_captured_at": "2026-08-04T07:00:00+00:00",
        "kiwoom_snapshot_age_seconds": 3600.0,
        "kiwoom_directory": "kiwoom",
        "historical_cutoff_date_exclusive": "2026-08-04",
        "historical_days_required_per_symbol": 3,
        "historical_rows_compared": 9,
        "historical_symbols_passed": ["005935"],
        "historical_price_conflict_count": 6,
        "historical_volume_mismatch_count": 6,
        "live_quote_status": "not_comparable",
        "live_quote_comparable_count": 0,
        "live_quote_conflict_count": 0,
        "live_capture_gap_seconds": 0.0,
        "decision_integration_eligible": False,
        "automatic_provider_substitution_enabled": False,
        "account_api_enabled": False,
        "order_api_enabled": False,
        "warnings": [],
        "failures": ["000660 conflict", "005930 conflict"],
        "daily_comparisons_file": "daily_price_comparisons.csv",
        "quote_comparisons_file": "live_quote_comparisons.csv",
    }
    result_id = _result_id(result_payload)
    result_payload["result_id"] = result_id
    result_path = result_directory / "consistency.json"
    result_path.write_text(json.dumps(result_payload), encoding="utf-8")

    pointer = {
        "status": "failed",
        "result_id": result_id,
        "result_path": str(result_path),
        "decision_integration_eligible": False,
        "historical_price_conflict_count": 6,
        "live_quote_status": "not_comparable",
        "automatic_provider_substitution_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = tmp_path / "latest_market_consistency.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_diagnostics_detects_full_series_and_symbol_mapping_conflicts(
    tmp_path: Path,
) -> None:
    report = diagnose_latest_consistency(_write_artifacts(tmp_path))

    assert report.status == "failed"
    assert report.rows_compared == 9
    assert report.price_conflicts == 6
    by_symbol = {symbol.ticker: symbol for symbol in report.symbols}

    first = by_symbol["000660"]
    assert first.price_conflicts == 3
    assert first.volume_mismatches == 3
    assert first.open_conflicts == 3
    assert first.close_conflicts == 3
    assert "full_series_price_mismatch" in first.suspected_patterns
    assert "full_series_volume_mismatch" in first.suspected_patterns
    assert "possible_symbol_mapping_conflict" in first.suspected_patterns
    assert first.possible_kiwoom_symbol == "005930"
    assert first.possible_symbol_match_rows == 3
    assert len(first.representative_rows) == 3

    passed = by_symbol["005935"]
    assert passed.price_conflicts == 0
    assert passed.volume_mismatches == 0
    assert passed.suspected_patterns == ()


def test_consistency_cmd_runs_diagnostics_without_masking_original_failure() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_market_source_consistency.cmd"
    ).read_text(encoding="utf-8")

    assert "alpha_cycle.market_consistency_cli" in script
    assert "alpha_cycle.market_consistency_diagnostics_cli" in script
    assert 'if not "%EXIT_CODE%"=="0"' in script
    assert "endlocal & exit /b %EXIT_CODE%" in script
