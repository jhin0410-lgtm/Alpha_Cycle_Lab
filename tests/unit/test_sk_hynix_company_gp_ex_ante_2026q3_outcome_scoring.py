from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_numeric_forecast import (
    LockedNumericForecast,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_outcome_scoring import (
    build_outcome_score,
    build_outcome_source_capture,
    extract_outcome_observation,
    load_outcome_score,
    load_outcome_scoring_contract,
    load_outcome_source_capture,
    persist_outcome_score,
    persist_outcome_source_capture,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation_v2 import (
    load_frozen_historical_schema_repair_v2,
)

_KST = ZoneInfo("Asia/Seoul")


def _forecast() -> LockedNumericForecast:
    return LockedNumericForecast(
        evidence_id="a" * 64,
        contract_evidence_id="b" * 64,
        selected_estimator_evidence_id="c" * 64,
        feature_vector_evidence_id="d" * 64,
        protocol_evidence_id="e" * 64,
        source_capture_evidence_id="f" * 64,
        target_period="2026Q3",
        forecast_origin=datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
        forecast_locked_at=datetime(2026, 8, 22, 16, 52, 7, tzinfo=_KST),
        selected_candidate_id="lagged_gp_affine_ols",
        predictors=("lagged_company_gross_profit",),
        feature_values=(65_991_356.0,),
        raw_unit_intercept=337_637.5345664583,
        raw_unit_coefficients=(1.101554337993561,),
        standardized_input=(18.886897166195247,),
        selected_forecast_krw_million=73_030_702.00644387,
        benchmark_id="previous_reported_quarter_gross_profit_persistence",
        benchmark_forecast_krw_million=65_991_356.0,
        historical_selected_candidate_mae_krw_million=1_249_345.1117558964,
        historical_benchmark_mae_krw_million=1_677_703.75,
    )


def _raw_payload(
    *,
    revenue: int = 80_000_000_000_000,
    cost: int = 10_000_000_000_000,
    gross: int = 70_000_000_000_000,
    receipt: str = "20261114000001",
) -> object:
    repair = load_frozen_historical_schema_repair_v2()
    execution = repair.runtime_execution
    common = {
        "sj_div": "IS",
        "bsns_year": "2026",
        "reprt_code": "11014",
        "rcept_no": receipt,
    }
    return {
        "financials": {
            "list": [
                {
                    **common,
                    "account_id": execution.revenue_account_ids[-1],
                    "thstrm_amount": str(revenue),
                },
                {
                    **common,
                    "account_id": execution.cost_of_sales_account_ids[-1],
                    "thstrm_amount": str(cost),
                },
                {
                    **common,
                    "account_id": execution.gross_profit_account_ids[-1],
                    "thstrm_amount": str(gross),
                },
            ]
        }
    }


def test_scoring_contract_is_frozen_before_outcome() -> None:
    contract = load_outcome_scoring_contract()
    assert contract.target_period == "2026Q3"
    assert contract.report_code == "11014"
    assert contract.fs_div == "CFS"
    assert contract.amount_field == "thstrm_amount"
    assert contract.primary_metric == "absolute_error_krw_million"
    assert contract.winner_rule == "strict_lower_absolute_error"
    assert contract.minimum_evaluation_date == date(2026, 9, 30)


def test_source_capture_rejects_pre_quarter_and_empty_payload() -> None:
    contract = load_outcome_scoring_contract()
    execution = load_frozen_historical_schema_repair_v2().runtime_execution
    forecast = _forecast()
    with pytest.raises(ValueError, match="prohibited before quarter end"):
        build_outcome_source_capture(
            contract,
            forecast,
            execution,
            evaluation_date=date(2026, 9, 29),
            raw_payload=_raw_payload(),
        )
    with pytest.raises(ValueError, match="empty payload is not persisted"):
        build_outcome_source_capture(
            contract,
            forecast,
            execution,
            evaluation_date=date(2026, 11, 14),
            raw_payload={"financials": {"list": []}},
        )


def test_locked_source_extracts_exact_v2_accounts_and_scores_selected_win() -> None:
    contract = load_outcome_scoring_contract()
    execution = load_frozen_historical_schema_repair_v2().runtime_execution
    forecast = _forecast()
    raw_payload = _raw_payload()
    capture = build_outcome_source_capture(
        contract,
        forecast,
        execution,
        evaluation_date=date(2026, 11, 14),
        raw_payload=raw_payload,
    )
    observation = extract_outcome_observation(contract, execution, capture, raw_payload)
    assert observation.gross_profit_krw_million == 70_000_000.0
    score = build_outcome_score(contract, forecast, capture, observation)
    assert score.selected_signed_error_krw_million == pytest.approx(3_030_702.006443873)
    assert score.benchmark_signed_error_krw_million == pytest.approx(-4_008_644.0)
    assert score.selected_absolute_error_krw_million == pytest.approx(3_030_702.006443873)
    assert score.benchmark_absolute_error_krw_million == 4_008_644.0
    assert score.absolute_error_advantage_krw_million > 0.0
    assert score.winner == "selected"
    assert score.q3_target_read
    assert score.q3_source_outcome_loaded
    assert score.q3_evaluated
    assert not score.model_refit_run
    assert not score.forecast_changed_after_lock


def test_score_uses_exact_tie_without_tolerance() -> None:
    contract = load_outcome_scoring_contract()
    execution = load_frozen_historical_schema_repair_v2().runtime_execution
    forecast = replace(
        _forecast(),
        selected_forecast_krw_million=65_991_356.0,
    )
    raw_payload = _raw_payload()
    capture = build_outcome_source_capture(
        contract,
        forecast,
        execution,
        evaluation_date=date(2026, 11, 14),
        raw_payload=raw_payload,
    )
    observation = extract_outcome_observation(contract, execution, capture, raw_payload)
    score = build_outcome_score(contract, forecast, capture, observation)
    assert score.selected_absolute_error_krw_million == score.benchmark_absolute_error_krw_million
    assert score.winner == "tie"


def test_source_and_score_persistence_are_content_addressed(tmp_path: Path) -> None:
    contract = load_outcome_scoring_contract()
    execution = load_frozen_historical_schema_repair_v2().runtime_execution
    forecast = _forecast()
    raw_payload = _raw_payload()
    capture = build_outcome_source_capture(
        contract,
        forecast,
        execution,
        evaluation_date=date(2026, 11, 14),
        raw_payload=raw_payload,
    )
    capture_pointer = persist_outcome_source_capture(capture, raw_payload, output=tmp_path)
    reloaded_capture, reloaded_raw = load_outcome_source_capture(capture_pointer)
    assert reloaded_capture == capture
    assert reloaded_raw == raw_payload
    observation = extract_outcome_observation(contract, execution, capture, raw_payload)
    score = build_outcome_score(contract, forecast, capture, observation)
    score_pointer = persist_outcome_score(score, output=tmp_path)
    assert load_outcome_score(score_pointer) == score
