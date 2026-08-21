from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation import (
    HistoricalTargetJoin,
    HistoricalTargetObservation,
    JoinedHistoricalRow,
    load_frozen_historical_evaluation_execution,
    run_frozen_historical_backtest,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    FrozenExactTwentyPeriodExAnteScope,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_selected_estimator_freeze import (
    build_selected_estimator_full_fit,
    load_selected_estimator_full_fit_contract,
    persist_selected_estimator_full_fit,
)

_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
)
_FEATURES = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)


def _scope(estimator_evidence_id: str) -> FrozenExactTwentyPeriodExAnteScope:
    return FrozenExactTwentyPeriodExAnteScope(
        evidence_id="c" * 64,
        frozen_at=date(2026, 8, 21),
        status="skhynix_ex_ante_exact_twenty_period_scope_frozen_target_blind",
        ticker="000660",
        target_metric="company_gross_profit_krw_million",
        protocol_evidence_id="d" * 64,
        feature_frontier_evidence_id="e" * 64,
        estimator_freeze_evidence_id=estimator_evidence_id,
        expansion_contract_evidence_id="f" * 64,
        expansion_report_sha256="1" * 64,
        base_bundle_evidence_id="2" * 64,
        combined_bundle_evidence_id="3" * 64,
        target_periods=_PERIODS,
        feature_ids=_FEATURES,
        target_row_count=20,
        feature_observation_count=100,
        selected_legacy_year=2016,
        shared_initial_training_rows=12,
        scored_fold_count=8,
        all_observations_point_in_time_eligible=True,
        all_frozen_candidates_sample_eligible=True,
        next_action="perform_first_historical_target_join_against_exact_frozen_scope",
    )


def _receipt(period_id: str) -> str:
    month_day = "0814" if period_id.endswith("Q2") else "1114"
    return f"{period_id[:4]}{month_day}000001"


def _join(execution_evidence_id: str) -> HistoricalTargetJoin:
    observations: list[HistoricalTargetObservation] = []
    rows: list[JoinedHistoricalRow] = []
    for index, period_id in enumerate(_PERIODS):
        lagged_gp = 1_000.0 + index * 135.0 + (index % 3) * 27.0
        revenue_feature = 8_000.0 + index * 410.0 + (index % 4) * 33.0
        nand_share = 0.35 + ((index * 3) % 7) * 0.012
        other_share = 0.05 + ((index * 5) % 6) * 0.007
        margin = lagged_gp / revenue_feature
        noise = float((index % 4) * 31 - 37)
        target = 1.18 * lagged_gp + 220.0 + noise
        gross_krw = int(round(target * 1_000_000.0))
        revenue_krw = 20_000_000_000
        cost_krw = revenue_krw - gross_krw
        receipt = _receipt(period_id)
        observations.append(
            HistoricalTargetObservation(
                period_id=period_id,
                report_code="11012" if period_id.endswith("Q2") else "11014",
                receipt_no=receipt,
                receipt_date=date(
                    int(receipt[:4]),
                    int(receipt[4:6]),
                    int(receipt[6:8]),
                ),
                revenue_krw=revenue_krw,
                cost_of_sales_krw=cost_krw,
                gross_profit_krw=gross_krw,
                gross_profit_krw_million=gross_krw / 1_000_000.0,
                raw_payload_sha256="4" * 64,
                captured_payload_bytes_sha256="5" * 64,
            )
        )
        features = (
            ("lagged_company_revenue", revenue_feature),
            ("lagged_company_gross_profit", lagged_gp),
            ("lagged_company_gross_margin", margin),
            ("lagged_nand_revenue_share", nand_share),
            ("lagged_other_revenue_share", other_share),
        )
        rows.append(
            JoinedHistoricalRow(
                period_id=period_id,
                features=features,
                target_company_gross_profit_krw_million=gross_krw / 1_000_000.0,
                target_receipt_no=receipt,
                target_raw_payload_sha256="4" * 64,
                target_captured_payload_bytes_sha256="5" * 64,
            )
        )
    return HistoricalTargetJoin(
        evidence_id="6" * 64,
        execution_evidence_id=execution_evidence_id,
        scope_evidence_id="c" * 64,
        combined_bundle_evidence_id="3" * 64,
        target_source_evidence_id="7" * 64,
        evaluation_date=date(2026, 8, 21),
        target_periods=_PERIODS,
        target_observations=tuple(observations),
        rows=tuple(rows),
    )


def test_full_fit_contract_cannot_reopen_model_or_prospective_scope() -> None:
    contract = load_selected_estimator_full_fit_contract()

    assert contract.training_rows == 20
    assert contract.scaling_ddof == 0
    assert contract.status == (
        "frozen_post_historical_selection_before_prospective_forecast"
    )


def test_selected_candidate_is_refit_on_all_twenty_rows_without_q3_access() -> None:
    contract = load_selected_estimator_full_fit_contract()
    execution = load_frozen_historical_evaluation_execution()
    estimator = load_frozen_ex_ante_estimator_selection()
    scope = _scope(estimator.evidence_id)
    join = _join(execution.evidence_id)
    result = run_frozen_historical_backtest(execution, scope, estimator, join)

    assert result.selected_candidate_id is not None
    candidate = next(
        item for item in estimator.candidates if item.candidate_id == result.selected_candidate_id
    )
    item = build_selected_estimator_full_fit(
        contract,
        join,
        result,
        candidate,
        raw_target_capture_evidence_id="8" * 64,
    )

    assert item.selected_candidate_id == result.selected_candidate_id
    assert item.predictors == candidate.predictors
    assert item.training_periods == _PERIODS
    assert item.training_row_count == 20
    assert item.design_rank == candidate.parameter_count
    assert item.residual_degrees_of_freedom == 20 - candidate.parameter_count
    assert item.historical_selected_candidate_mae_krw_million < (
        item.historical_benchmark_mae_krw_million
    )
    assert item.historical_relative_mae_improvement > 0.0
    assert not item.prospective_feature_vector_frozen
    assert not item.prospective_forecast_run
    assert not item.q3_target_read
    assert not item.q3_source_outcome_loaded
    assert not item.q3_evaluated
    assert not item.numeric_forward_forecast_enabled


def test_selected_estimator_persistence_is_content_addressed_and_locked(
    tmp_path: Path,
) -> None:
    contract = load_selected_estimator_full_fit_contract()
    execution = load_frozen_historical_evaluation_execution()
    estimator = load_frozen_ex_ante_estimator_selection()
    scope = _scope(estimator.evidence_id)
    join = _join(execution.evidence_id)
    result = run_frozen_historical_backtest(execution, scope, estimator, join)
    assert result.selected_candidate_id is not None
    candidate = next(
        item for item in estimator.candidates if item.candidate_id == result.selected_candidate_id
    )
    item = build_selected_estimator_full_fit(
        contract,
        join,
        result,
        candidate,
        raw_target_capture_evidence_id="8" * 64,
    )

    pointer = persist_selected_estimator_full_fit(item, output=tmp_path)
    replay = persist_selected_estimator_full_fit(item, output=tmp_path)
    assert replay == pointer
    assert (tmp_path / f"selected-estimator-{item.evidence_id}.json").is_file()

    drifted = replace(
        item,
        evidence_id="9" * 64,
        training_mae_krw_million=item.training_mae_krw_million + 1.0,
    )
    with pytest.raises(ValueError, match="evidence hash drifted"):
        persist_selected_estimator_full_fit(drifted, output=tmp_path)
