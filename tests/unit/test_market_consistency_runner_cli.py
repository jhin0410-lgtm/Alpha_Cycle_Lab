"""Tests for venue-scope-aware cross-provider consistency assessment."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

from alpha_cycle import market_consistency_runner_cli as runner
from alpha_cycle.market_consistency_cli import ConsistencyResult

SYMBOLS = ("000660", "005930", "005935")
BASES = {"000660": 100_000, "005930": 200_000, "005935": 300_000}
VOLUMES = {"000660": 1_000_000, "005930": 2_000_000, "005935": 3_000_000}


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
    toss_base: int,
    kiwoom_base: int,
    toss_volume: int,
    kiwoom_volume: int,
    price_match: bool | None = None,
) -> dict[str, object]:
    exact_price_match = toss_base == kiwoom_base
    return {
        "ticker": ticker,
        "date": f"2026-07-{index + 1:02d}",
        "toss_open": toss_base + index,
        "kiwoom_open": kiwoom_base + index,
        "toss_high": toss_base + index + 10,
        "kiwoom_high": kiwoom_base + index + 10,
        "toss_low": toss_base + index - 10,
        "kiwoom_low": kiwoom_base + index - 10,
        "toss_close": toss_base + index + 5,
        "kiwoom_close": kiwoom_base + index + 5,
        "toss_volume": toss_volume + index,
        "kiwoom_volume": kiwoom_volume + index,
        "max_price_difference_won": abs(toss_base - kiwoom_base),
        "price_match": exact_price_match if price_match is None else price_match,
        "volume_match": toss_volume == kiwoom_volume,
        "volume_difference_bps": "0" if toss_volume == kiwoom_volume else "1000",
    }


def _build_case(
    tmp_path: Path,
    *,
    venue_mismatch: bool,
    control_conflict: bool = False,
    explicit_equal_scope: bool = False,
    cross_symbol_swap: bool = False,
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
    swap = {"000660": "005930", "005930": "000660"}
    for ticker in SYMBOLS:
        for index in range(20):
            toss_base = BASES[ticker]
            toss_volume = VOLUMES[ticker]
            if cross_symbol_swap and ticker in swap:
                kiwoom_symbol = swap[ticker]
                kiwoom_base = BASES[kiwoom_symbol]
                kiwoom_volume = VOLUMES[kiwoom_symbol]
            elif ticker in {"000660", "005930"} and venue_mismatch:
                kiwoom_base = toss_base + 100
                kiwoom_volume = toss_volume - 100_000
            elif ticker == "005935" and control_conflict and index == 0:
                kiwoom_base = toss_base + 100
                kiwoom_volume = toss_volume - 100_000
            else:
                kiwoom_base = toss_base
                kiwoom_volume = toss_volume
            rows.append(
                _comparison_row(
                    ticker,
                    index,
                    toss_base=toss_base,
                    kiwoom_base=kiwoom_base,
                    toss_volume=toss_volume,
                    kiwoom_volume=kiwoom_volume,
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


def _read_rows(result_path: Path) -> list[dict[str, str]]:
    with (result_path.parent / "daily_price_comparisons.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def test_full_series_variable_symbols_with_exact_control_are_scope_blocked(
    tmp_path: Path,
) -> None:
    result, result_path = _build_case(tmp_path, venue_mismatch=True)

    assessment, assessment_path = runner.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "blocked_market_scope_mismatch"
    assert assessment.classification == "inferred_venue_scope_mismatch"
    assert assessment.raw_price_difference_count == 40
    assert assessment.tolerance_conflict_count == 40
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

    assessment, _ = runner.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "failed"
    assert assessment.classification == "true_or_unresolved_price_conflict"
    assert assessment.raw_price_difference_count == 1
    assert assessment.comparable_scope_price_conflict_count == 1
    assert assessment.scope_incompatible_row_count == 0


def test_explicit_equal_market_scopes_prevent_venue_inference(tmp_path: Path) -> None:
    result, result_path = _build_case(
        tmp_path,
        venue_mismatch=True,
        explicit_equal_scope=True,
    )

    assessment, _ = runner.assess_consistency_result(
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

    assessment, _ = runner.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.status == "passed_historical_only"
    assert assessment.classification == "equivalent_scope_observed"
    assert assessment.raw_price_difference_count == 0
    assert assessment.comparable_scope_price_conflict_count == 0


def test_exact_differences_are_not_hidden_by_tolerance_flags(tmp_path: Path) -> None:
    result, result_path = _build_case(tmp_path, venue_mismatch=True)
    rows = _read_rows(result_path)
    control = next(row for row in rows if row["ticker"] == "005935")
    control["kiwoom_close"] = str(int(control["kiwoom_close"]) + 1)
    control["max_price_difference_won"] = "1"
    control["price_match"] = "True"
    _write_csv(result_path.parent / "daily_price_comparisons.csv", rows)

    assessment, _ = runner.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.raw_price_difference_count == 41
    assert assessment.tolerance_conflict_count == 40
    assert assessment.classification == "true_or_unresolved_price_conflict"


def test_cross_symbol_exact_mapping_blocks_venue_inference(tmp_path: Path) -> None:
    result, result_path = _build_case(
        tmp_path,
        venue_mismatch=False,
        cross_symbol_swap=True,
    )

    assessment, _ = runner.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.classification == "possible_symbol_mapping_conflict"
    by_symbol = {item.ticker: item for item in assessment.symbols}
    assert by_symbol["000660"].possible_kiwoom_symbol == "005930"
    assert by_symbol["005930"].possible_kiwoom_symbol == "000660"
    assert assessment.scope_incompatible_row_count == 0


def test_live_only_failure_is_not_mislabeled_as_historical_conflict(
    tmp_path: Path,
) -> None:
    result, result_path = _build_case(tmp_path, venue_mismatch=False)
    result = replace(
        result,
        status="failed",
        live_quote_status="conflict",
        live_quote_conflict_count=1,
        failures=("005930 live quote conflict",),
    )

    assessment, _ = runner.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.classification == "live_quote_conflict"
    assert assessment.raw_price_difference_count == 0
    assert assessment.live_quote_conflict_count == 1


def test_insufficient_overlap_produces_a_linked_fail_closed_assessment(
    tmp_path: Path,
) -> None:
    result, result_path = _build_case(tmp_path, venue_mismatch=True)
    rows = [row for row in _read_rows(result_path) if row["ticker"] != "005935"]
    _write_csv(result_path.parent / "daily_price_comparisons.csv", rows)
    result = replace(
        result,
        historical_rows_compared=40,
        historical_volume_mismatch_count=40,
        historical_symbols_passed=(),
        failures=("005935 has insufficient overlap",),
    )

    assessment, _ = runner.assess_consistency_result(
        result,
        result_path,
        output_root=tmp_path,
    )

    assert assessment.classification == "insufficient_historical_overlap"
    assert assessment.historical_scope_status == "insufficient_evidence"
    assert assessment.decision_integration_eligible is False


def test_assessment_failure_invalidates_latest_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, result_path = _build_case(tmp_path, venue_mismatch=True)
    rows = _read_rows(result_path)
    rows[0]["toss_open"] = "not-a-number"
    _write_csv(result_path.parent / "daily_price_comparisons.csv", rows)
    monkeypatch.setattr(
        runner,
        "run_consistency_check",
        lambda **_kwargs: (result, result_path),
    )

    with pytest.raises(runner.ScopeAssessmentError):
        runner.run_assessed_consistency(
            output_root=tmp_path,
            required_days=20,
            price_tolerance_won=runner.Decimal(0),
            live_tolerance_bps=runner.Decimal(50),
            max_snapshot_age_minutes=30,
            max_capture_gap_seconds=60,
        )

    pointer = json.loads(
        (tmp_path / "latest_market_scope_assessment.json").read_text(
            encoding="utf-8"
        )
    )
    assert pointer["status"] == "failed_assessment"
    assert pointer["raw_result_id"] == result.result_id
    assert pointer["decision_integration_eligible"] is False


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
