from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation import (
    build_historical_target_join,
    extract_historical_target_observation,
    load_frozen_historical_evaluation_execution,
    load_historical_target_join,
    persist_historical_target_join,
    run_frozen_historical_backtest,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    build_locked_pit_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureObservation,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    FrozenExactTwentyPeriodExAnteScope,
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


def _feature_values(index: int) -> dict[str, float]:
    revenue = 10_000.0 + index * 317.0 + (index % 3) * 29.0
    gross_profit = 1_100.0 + index * 83.0 + (index % 2) * 17.0
    return {
        "lagged_company_revenue": revenue,
        "lagged_company_gross_profit": gross_profit,
        "lagged_company_gross_margin": gross_profit / revenue,
        "lagged_nand_revenue_share": 0.42 + 0.01 * ((index * 3) % 7),
        "lagged_other_revenue_share": 0.07 + 0.006 * ((index * 5) % 6),
    }


def _bundle():
    observations: list[PointInTimeFeatureObservation] = []
    for index, period_id in enumerate(_PERIODS):
        values = _feature_values(index)
        for feature_id in _FEATURES:
            direct = feature_id in {
                "lagged_company_revenue",
                "lagged_company_gross_profit",
            }
            observations.append(
                PointInTimeFeatureObservation(
                    period_id=period_id,
                    feature_id=feature_id,
                    value=values[feature_id],
                    provenance_class="timestamped_immutable_filing",
                    source_available_at=datetime(int(period_id[:4]), 1, 1, tzinfo=UTC),
                    source_bytes_sha256="a" * 64,
                    source_evidence_id="b" * 64,
                    source_version_identity=f"test:{period_id}:{feature_id}",
                    direct_source_fact=direct,
                    deterministic_transform=not direct,
                )
            )
    return build_locked_pit_feature_bundle(
        created_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        observations=tuple(observations),
    )


def _scope(bundle_evidence_id: str, estimator_evidence_id: str):
    return FrozenExactTwentyPeriodExAnteScope(
        evidence_id="c" * 64,
        frozen_at=datetime(2026, 8, 21, 12, 30, tzinfo=UTC),
        status="skhynix_ex_ante_exact_twenty_period_scope_frozen_target_blind",
        ticker="000660",
        target_metric="company_gross_profit_krw_million",
        protocol_evidence_id="d" * 64,
        feature_frontier_evidence_id="e" * 64,
        estimator_freeze_evidence_id=estimator_evidence_id,
        expansion_contract_evidence_id="f" * 64,
        expansion_report_sha256="1" * 64,
        base_bundle_evidence_id="2" * 64,
        combined_bundle_evidence_id=bundle_evidence_id,
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
    year = period_id[:4]
    month_day = "0815" if period_id.endswith("Q2") else "1115"
    return f"{year}{month_day}000001"


def _raw_payload(period_id: str, target_million: float, *, split_receipt: bool = False):
    report_code = "11012" if period_id.endswith("Q2") else "11014"
    receipt = _receipt(period_id)
    alternate_receipt = receipt[:-1] + "2"
    gross = int(round(target_million * 1_000_000.0))
    revenue = 20_000_000_000_000 + int(period_id[:4]) * 1_000_000
    cost = revenue - gross
    common = {
        "sj_div": "IS",
        "bsns_year": period_id[:4],
        "reprt_code": report_code,
    }
    return {
        "company": {"stock_code": "000660"},
        "financials": {
            "status": "000",
            "list": [
                {
                    **common,
                    "account_id": "ifrs-full_Revenue",
                    "rcept_no": receipt,
                    "thstrm_amount": str(revenue),
                },
                {
                    **common,
                    "account_id": "ifrs-full_CostOfSales",
                    "rcept_no": alternate_receipt if split_receipt else receipt,
                    "thstrm_amount": str(cost),
                },
                {
                    **common,
                    "account_id": "ifrs-full_GrossProfit",
                    "rcept_no": receipt,
                    "thstrm_amount": str(gross),
                },
            ],
        },
    }


def _payloads(*, benchmark_exact: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    for index, period_id in enumerate(_PERIODS):
        values = _feature_values(index)
        if benchmark_exact:
            target = values["lagged_company_gross_profit"]
        else:
            target = (
                1.35 * values["lagged_company_gross_profit"]
                + 850.0 * values["lagged_nand_revenue_share"]
                + 75.0
            )
        result[period_id] = _raw_payload(period_id, target)
    return result


def test_execution_manifest_is_frozen_before_first_target_read() -> None:
    execution = load_frozen_historical_evaluation_execution()

    assert execution.exact_target_periods == _PERIODS
    assert execution.shared_initial_training_rows == 12
    assert execution.scored_fold_count == 8
    assert execution.q2_report_code == "11012"
    assert execution.q3_report_code == "11014"
    assert not execution.post_join_target_refresh_allowed
    assert not execution.source_fallback_allowed
    assert not execution.partial_target_join_allowed
    assert not execution.historical_target_values_read_before_run
    assert not execution.historical_backtest_run_before_run
    assert not execution.q3_target_read_before_run


def test_first_target_join_and_backtest_cross_only_historical_boundary() -> None:
    execution = load_frozen_historical_evaluation_execution()
    estimator = load_frozen_ex_ante_estimator_selection()
    bundle = _bundle()
    scope = _scope(bundle.evidence_id, estimator.evidence_id)
    join = build_historical_target_join(
        execution,
        scope,
        bundle,
        estimator,
        evaluation_date=date(2026, 8, 21),
        raw_payloads=_payloads(benchmark_exact=False),
    )
    backtest = run_frozen_historical_backtest(execution, scope, estimator, join)

    assert join.target_periods == _PERIODS
    assert len(join.target_observations) == 20
    assert len(join.rows) == 20
    assert join.historical_target_values_read
    assert join.target_join_run
    assert not join.estimator_fit_run
    assert not join.historical_backtest_run
    assert not join.q3_target_read
    assert not join.q3_source_outcome_loaded

    assert len(backtest.benchmark_folds) == 8
    assert tuple(item.training_row_count for item in backtest.benchmark_folds) == tuple(
        range(12, 20)
    )
    assert tuple(item.score_period for item in backtest.benchmark_folds) == _PERIODS[12:]
    assert backtest.historical_target_values_read
    assert backtest.target_join_run
    assert backtest.estimator_fit_run
    assert backtest.historical_backtest_run
    assert not backtest.q1_used_for_selection
    assert not backtest.q3_target_read
    assert not backtest.q3_source_outcome_loaded
    assert not backtest.q3_evaluated
    assert not backtest.numeric_forward_forecast_enabled
    assert any(item.strictly_beats_benchmark for item in backtest.candidates)
    assert backtest.selected_candidate_id is not None


def test_strict_benchmark_gate_selects_no_estimator_when_persistence_is_exact() -> None:
    execution = load_frozen_historical_evaluation_execution()
    estimator = load_frozen_ex_ante_estimator_selection()
    bundle = _bundle()
    scope = _scope(bundle.evidence_id, estimator.evidence_id)
    join = build_historical_target_join(
        execution,
        scope,
        bundle,
        estimator,
        evaluation_date=date(2026, 8, 21),
        raw_payloads=_payloads(benchmark_exact=True),
    )
    backtest = run_frozen_historical_backtest(execution, scope, estimator, join)

    assert backtest.benchmark_mae_krw_million == 0.0
    assert not any(item.strictly_beats_benchmark for item in backtest.candidates)
    assert backtest.selected_candidate_id is None
    assert not backtest.final_estimator_selected
    assert backtest.selection_status == "no_candidate_strictly_beat_frozen_benchmark"
    assert not backtest.numeric_forward_forecast_enabled


def test_target_extraction_rejects_cross_receipt_account_values() -> None:
    execution = load_frozen_historical_evaluation_execution()
    payload = _raw_payload("2016Q2", 1_500.0, split_receipt=True)

    with pytest.raises(ValueError, match="cross filing receipts"):
        extract_historical_target_observation(
            execution,
            "2016Q2",
            payload,
            evaluation_date=date(2026, 8, 21),
        )


def test_persisted_target_join_cannot_be_refreshed_after_first_lock(tmp_path: Path) -> None:
    execution = load_frozen_historical_evaluation_execution()
    estimator = load_frozen_ex_ante_estimator_selection()
    bundle = _bundle()
    scope = _scope(bundle.evidence_id, estimator.evidence_id)
    first_payloads = _payloads(benchmark_exact=False)
    first = build_historical_target_join(
        execution,
        scope,
        bundle,
        estimator,
        evaluation_date=date(2026, 8, 21),
        raw_payloads=first_payloads,
    )
    pointer = persist_historical_target_join(first, first_payloads, output=tmp_path)
    replayed = load_historical_target_join(pointer)

    assert replayed.evidence_id == first.evidence_id

    refreshed_payloads = _payloads(benchmark_exact=False)
    refreshed_payloads["2025Q3"] = _raw_payload("2025Q3", 99_999.0)
    refreshed = build_historical_target_join(
        execution,
        scope,
        bundle,
        estimator,
        evaluation_date=date(2026, 8, 21),
        raw_payloads=refreshed_payloads,
    )
    with pytest.raises(ValueError, match="post-join target refresh is prohibited"):
        persist_historical_target_join(refreshed, refreshed_payloads, output=tmp_path)
