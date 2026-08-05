"""Tests for fail-closed market scope assessment integrity."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from alpha_cycle import market_consistency_assessment_integrity as integrity
from alpha_cycle import market_consistency_runner_cli as runner
from alpha_cycle.market_consistency_cli import ConsistencyResult

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


def _row(ticker: str, *, exact_difference: bool = False) -> dict[str, object]:
    base = {"000660": 100_000, "005930": 200_000, "005935": 300_000}[ticker]
    kiwoom_close = base + 1 if exact_difference else base
    return {
        "ticker": ticker,
        "date": "2026-08-01",
        "toss_open": base,
        "kiwoom_open": base,
        "toss_high": base + 10,
        "kiwoom_high": base + 10,
        "toss_low": base - 10,
        "kiwoom_low": base - 10,
        "toss_close": base,
        "kiwoom_close": kiwoom_close,
        "toss_volume": 1_000_000,
        "kiwoom_volume": 1_000_000,
        "max_price_difference_won": 1 if exact_difference else 0,
        "price_match": True,
        "volume_match": True,
        "volume_difference_bps": "0",
    }


def _quote_row(ticker: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "toss_price": 100,
        "kiwoom_price": 100,
        "absolute_difference_won": 0,
        "difference_bps": "0.0000",
        "capture_gap_seconds": "0.0",
        "comparable": True,
        "within_tolerance": True,
        "reason": "capture times and snapshot ages are comparable",
    }


def _case(
    tmp_path: Path,
    *,
    exact_difference: bool = True,
) -> tuple[ConsistencyResult, Path]:
    toss_directory = tmp_path / "toss"
    kiwoom_directory = tmp_path / "kiwoom"
    _write_json(
        toss_directory / "manifest.json",
        {"provider": "tossinvest-readonly", "adjusted": False},
    )
    _write_json(
        kiwoom_directory / "manifest.json",
        {
            "provider": "kiwoom_openapi_plus",
            "adjusted_prices": False,
            "daily_tr_code": "opt10081",
        },
    )

    result_directory = tmp_path / "result"
    _write_csv(
        result_directory / "daily_price_comparisons.csv",
        [
            _row("000660"),
            _row("005930", exact_difference=exact_difference),
            _row("005935"),
        ],
    )
    _write_csv(
        result_directory / "live_quote_comparisons.csv",
        [_quote_row(ticker) for ticker in SYMBOLS],
    )
    result = ConsistencyResult(
        schema_version="1.0",
        status="passed",
        checked_at_utc="2026-08-04T08:00:00+00:00",
        checked_at_kst="2026-08-04T17:00:00+09:00",
        expected_symbols=SYMBOLS,
        toss_snapshot_id="toss-id",
        toss_captured_at="2026-08-04T08:00:00+00:00",
        toss_snapshot_age_seconds=0.0,
        toss_directory=str(toss_directory),
        toss_resolution_source="pinned",
        kiwoom_snapshot_id="kiwoom-id",
        kiwoom_captured_at="2026-08-04T08:00:00+00:00",
        kiwoom_snapshot_age_seconds=0.0,
        kiwoom_directory=str(kiwoom_directory),
        historical_cutoff_date_exclusive="2026-08-04",
        historical_days_required_per_symbol=1,
        historical_rows_compared=3,
        historical_symbols_passed=SYMBOLS,
        historical_price_conflict_count=0,
        historical_volume_mismatch_count=0,
        live_quote_status="passed",
        live_quote_comparable_count=3,
        live_quote_conflict_count=0,
        live_capture_gap_seconds=0.0,
        decision_integration_eligible=True,
        automatic_provider_substitution_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        warnings=(),
        failures=(),
        daily_comparisons_file="daily_price_comparisons.csv",
        quote_comparisons_file="live_quote_comparisons.csv",
        result_id="raw-result-id",
    )
    result_path = result_directory / "consistency.json"
    _write_json(result_path, {"result_id": result.result_id})
    return result, result_path


def test_exact_difference_within_tolerance_cannot_be_integration_eligible(
    tmp_path: Path,
) -> None:
    result, result_path = _case(tmp_path)

    assessment, _ = integrity.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "passed"
    assert assessment.classification == "true_or_unresolved_price_conflict"
    assert assessment.raw_price_difference_count == 1
    assert assessment.tolerance_conflict_count == 0
    assert assessment.decision_integration_eligible is False
    assessment_pointer = json.loads(
        (tmp_path / "latest_market_scope_assessment.json").read_text(
            encoding="utf-8"
        )
    )
    assert assessment_pointer["decision_integration_eligible"] is False
    raw_pointer = json.loads(
        (tmp_path / "latest_market_consistency.json").read_text(encoding="utf-8")
    )
    assert raw_pointer["assessment_status"] == "completed"
    assert raw_pointer["classification"] == "true_or_unresolved_price_conflict"
    assert raw_pointer["decision_integration_eligible"] is False


def test_equivalent_scope_enables_raw_pointer_only_after_assessment(
    tmp_path: Path,
) -> None:
    result, result_path = _case(tmp_path, exact_difference=False)

    assessment, assessment_path = integrity.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.classification == "equivalent_scope_observed"
    assert assessment.decision_integration_eligible is True
    raw_pointer = json.loads(
        (tmp_path / "latest_market_consistency.json").read_text(encoding="utf-8")
    )
    assert raw_pointer["assessment_status"] == "completed"
    assert raw_pointer["assessment_id"] == assessment.assessment_id
    assert raw_pointer["assessment_path"] == str(assessment_path)
    assert raw_pointer["decision_integration_eligible"] is True


def test_live_quote_rows_require_exact_unique_symbol_membership(
    tmp_path: Path,
) -> None:
    result, result_path = _case(tmp_path)
    quote_path = result_path.parent / result.quote_comparisons_file
    rows = list(csv.DictReader(quote_path.open(encoding="utf-8", newline="")))
    rows[2]["ticker"] = "005930"
    _write_csv(quote_path, rows)

    with pytest.raises(
        runner.ScopeAssessmentError,
        match="duplicate tickers: 005930",
    ):
        integrity.assess_consistency_result(
            result,
            result_path,
            output_root=tmp_path,
        )


def test_live_quote_rows_require_all_evidence_fields(tmp_path: Path) -> None:
    result, result_path = _case(tmp_path)
    quote_path = result_path.parent / result.quote_comparisons_file
    _write_csv(quote_path, [{"ticker": ticker} for ticker in SYMBOLS])

    with pytest.raises(
        runner.ScopeAssessmentError,
        match="missing fields",
    ):
        integrity.assess_consistency_result(
            result,
            result_path,
            output_root=tmp_path,
        )

    raw_pointer = json.loads(
        (tmp_path / "latest_market_consistency.json").read_text(encoding="utf-8")
    )
    assert raw_pointer["assessment_status"] == "failed"
    assert raw_pointer["decision_integration_eligible"] is False


def test_live_quote_aggregates_must_match_linked_rows(tmp_path: Path) -> None:
    result, result_path = _case(tmp_path)
    quote_path = result_path.parent / result.quote_comparisons_file
    rows = list(csv.DictReader(quote_path.open(encoding="utf-8", newline="")))
    rows[0]["comparable"] = "False"
    rows[0]["within_tolerance"] = ""
    _write_csv(quote_path, rows)

    with pytest.raises(
        runner.ScopeAssessmentError,
        match="mixes comparable and non-comparable rows",
    ):
        integrity.assess_consistency_result(
            result,
            result_path,
            output_root=tmp_path,
        )


def test_live_quote_rows_cannot_be_empty_when_aggregates_are_zero(
    tmp_path: Path,
) -> None:
    result, result_path = _case(tmp_path)
    quote_path = result_path.parent / result.quote_comparisons_file
    quote_path.write_text("", encoding="utf-8")

    with pytest.raises(
        runner.ScopeAssessmentError,
        match="symbol set mismatch",
    ):
        integrity.assess_consistency_result(
            result,
            result_path,
            output_root=tmp_path,
        )
