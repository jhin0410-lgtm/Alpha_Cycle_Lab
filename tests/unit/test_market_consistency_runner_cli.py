"""Tests for venue-scope-aware cross-provider consistency assessment."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

from alpha_cycle.market_consistency_cli import ConsistencyResult
from alpha_cycle.market_consistency_runner_cli import assess_consistency_result

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


def _comparison_row(
    ticker: str,
    index: int,
    *,
    price_match: bool,
    volume_match: bool,
) -> dict[str, object]:
    toss_base = 100_000 + index
    kiwoom_base = toss_base if price_match else toss_base + 100
    return {
        "ticker": ticker,
        "date": f"2026-07-{index + 1:02d}",
        "toss_open": toss_base,
        "kiwoom_open": kiwoom_base,
        "toss_high": toss_base + 10,
        "kiwoom_high": kiwoom_base + 10,
        "toss_low": toss_base - 10,
        "kiwoom_low": kiwoom_base - 10,
        "toss_close": toss_base + 5,
        "kiwoom_close": kiwoom_base + 5,
        "toss_volume": 1_000_000 + index,
        "kiwoom_volume": (
            1_000_000 + index if volume_match else 900_000 + index
        ),
        "max_price_difference_won": 0 if price_match else 100,
        "price_match": price_match,
        "volume_match": volume_match,
        "volume_difference_bps": "0" if volume_match else "1000",
    }


def _build_case(
    tmp_path: Path,
    *,
    venue_mismatch: bool,
    control_conflict: bool = False,
    explicit_equal_scope: bool = False,
) -> tuple[ConsistencyResult, Path]:
    toss_directory = tmp_path / "toss"
    kiwoom_directory = tmp_path / "kiwoom"
    result_directory = tmp_path / "market-source-consistency" / "run"
    scope_fields: dict[str, object] = {}
    if explicit_equal_scope:
        scope_fields["historical_market_scope"] = "same_scope"

    _write_json(
        toss_directory / "manifest.json",
        {
            "provider": "tossinvest-readonly",
            "adjusted": False,
            **scope_fields,
        },
    )
    _write_json(
        kiwoom_directory / "manifest.json",
        {
            "provider": "kiwoom_openapi_plus",
            "adjusted_prices": False,
            "daily_tr_code": "opt10081",
            **scope_fields,
        },
    )

    rows: list[dict[str, object]] = []
    for ticker in SYMBOLS:
        for index in range(20):
            if ticker in {"000660", "005930"}:
                matches = not venue_mismatch
                rows.append(
                    _comparison_row(
                        ticker,
                        index,
                        price_match=matches,
                        volume_match=matches,
                    )
                )
            else:
                matches = not control_conflict or index != 0
                rows.append(
                    _comparison_row(
                        ticker,
                        index,
                        price_match=matches,
                        volume_match=matches,
                    )
                )
    _write_csv(result_directory / "daily_price_comparisons.csv", rows)

    price_conflicts = sum(not bool(row["price_match"]) for row in rows)
    volume_conflicts = sum(not bool(row["volume_match"]) for row in rows)
    status = "failed" if price_conflicts else "passed_historical_only"
    passed_symbols = tuple(
        ticker
        for ticker in SYMBOLS
        if all(
            bool(row["price_match"])
            for row in rows
            if row["ticker"] == ticker
        )
    )
    result = ConsistencyResult(
        schema_version="1.0",
        status=status,
        checked_at_utc="2026-08-04T08:00:00+00:00",
        checked_at_kst="2026-08-04T17:00:00+09:00",
        expected_symbols=SYMBOLS,
        toss_snapshot_id="toss-id",
        toss_captured_at="2026-08-04T06:00:00+00:00",
        toss_snapshot_age_seconds=7200.0,
        toss_directory=str(toss_directory),
        toss_resolution_source="latest_immutable_snapshot",
        kiwoom_snapshot_id="kiwoom-id",
        kiwoom_captured_at="2026-08-04T07:00:00+00:00",
        kiwoom_snapshot_age_seconds=3600.0,
        kiwoom_directory=str(kiwoom_directory),
        historical_cutoff_date_exclusive="2026-08-04",
        historical_days_required_per_symbol=20,
        historical_rows_compared=60,
        historical_symbols_passed=passed_symbols,
        historical_price_conflict_count=price_conflicts,
        historical_volume_mismatch_count=volume_conflicts,
        live_quote_status="not_comparable",
        live_quote_comparable_count=0,
        live_quote_conflict_count=0,
        live_capture_gap_seconds=3600.0,
        decision_integration_eligible=False,
        automatic_provider_substitution_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        warnings=(),
        failures=("raw price differences",) if price_conflicts else (),
        daily_comparisons_file="daily_price_comparisons.csv",
        quote_comparisons_file="live_quote_comparisons.csv",
        result_id="raw-result-id",
    )
    result_path = result_directory / "consistency.json"
    _write_json(result_path, {"result_id": result.result_id})
    return result, result_path


def test_full_series_variable_symbols_with_exact_control_are_scope_blocked(
    tmp_path: Path,
) -> None:
    result, result_path = _build_case(tmp_path, venue_mismatch=True)

    assessment, assessment_path = assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "blocked_market_scope_mismatch"
    assert assessment.classification == "inferred_venue_scope_mismatch"
    assert assessment.raw_price_difference_count == 40
    assert assessment.comparable_scope_price_conflict_count == 0
    assert assessment.scope_incompatible_row_count == 40
    assert assessment.scope_incompatible_symbols == ("000660", "005930")
    assert assessment.control_symbols_verified == ("005935",)
    assert assessment.historical_scope_status == "not_comparable"
    assert assessment.decision_integration_eligible is False
    assert assessment.automatic_provider_substitution_enabled is False
    assert assessment.account_api_enabled is False
    assert assessment.order_api_enabled is False
    assert assessment_path.is_file()
    assert (tmp_path / "latest_market_scope_assessment.json").is_file()


def test_control_security_conflict_remains_true_fail_closed_conflict(
    tmp_path: Path,
) -> None:
    result, result_path = _build_case(
        tmp_path,
        venue_mismatch=False,
        control_conflict=True,
    )

    assessment, _ = assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "failed"
    assert assessment.classification == "true_or_unresolved_price_conflict"
    assert assessment.raw_price_difference_count == 1
    assert assessment.comparable_scope_price_conflict_count == 1
    assert assessment.scope_incompatible_row_count == 0
    assert assessment.decision_integration_eligible is False


def test_explicit_equal_market_scopes_prevent_venue_inference(tmp_path: Path) -> None:
    result, result_path = _build_case(
        tmp_path,
        venue_mismatch=True,
        explicit_equal_scope=True,
    )

    assessment, _ = assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "failed"
    assert assessment.classification == "true_or_unresolved_price_conflict"
    assert assessment.comparable_scope_price_conflict_count == 40
    assert assessment.scope_incompatible_symbols == ()


def test_matching_historical_series_preserve_historical_only_status(
    tmp_path: Path,
) -> None:
    result, result_path = _build_case(tmp_path, venue_mismatch=False)
    result = replace(result, status="passed_historical_only")

    assessment, _ = assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "passed_historical_only"
    assert assessment.classification == "equivalent_scope_observed"
    assert assessment.raw_price_difference_count == 0
    assert assessment.comparable_scope_price_conflict_count == 0
    assert assessment.decision_integration_eligible is False


def test_windows_wrapper_uses_scope_aware_runner_only() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_market_source_consistency.cmd"
    ).read_text(encoding="utf-8")

    assert "alpha_cycle.market_consistency_runner_cli" in script
    assert "alpha_cycle.market_consistency_cli" not in script
    assert "alpha_cycle.market_consistency_diagnostics_cli" not in script
    assert "endlocal & exit /b %EXIT_CODE%" in script
