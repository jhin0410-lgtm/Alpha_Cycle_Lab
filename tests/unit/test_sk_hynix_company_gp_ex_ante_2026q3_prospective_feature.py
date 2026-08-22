from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_prospective_feature import (
    ProspectiveFeatureFreezeContract,
    build_prospective_feature_vector,
    build_prospective_source_capture,
    load_prospective_feature_freeze_contract,
    load_prospective_source_capture,
    persist_prospective_source_capture,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    load_frozen_company_gp_ex_ante_protocol,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_selected_estimator_freeze import (
    FrozenSelectedEstimatorFullFit,
)

_KST = ZoneInfo("Asia/Seoul")
_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
)


def _contract() -> ProspectiveFeatureFreezeContract:
    return ProspectiveFeatureFreezeContract(
        evidence_id="a" * 64,
        freeze_version="1.0-frozen-before-2026q3-origin",
        status="frozen_before_2026q3_forecast_origin",
        ticker="000660",
        target_metric="company_gross_profit_krw_million",
        target_period="2026Q3",
        source_period="2026Q2",
        protocol_path="config/skhynix_company_gp_ex_ante_forecast_protocol.v1.yaml",
        selected_estimator_path="unused.json",
        historical_execution_v2_path=(
            "config/skhynix_company_gp_ex_ante_historical_evaluation_execution.v2.yaml"
        ),
        required_selected_candidate_id="lagged_gp_affine_ols",
        required_predictors=("lagged_company_gross_profit",),
        business_year=2026,
        report_code="11012",
        fs_div="CFS",
        amount_field="thstrm_amount",
        raw_capture_before_extraction=True,
        source_refresh_allowed=False,
        first_capture_not_after_origin=True,
        early_lock_is_final=True,
    )


def _selected() -> FrozenSelectedEstimatorFullFit:
    return FrozenSelectedEstimatorFullFit(
        evidence_id="b" * 64,
        contract_evidence_id="c" * 64,
        execution_evidence_id="d" * 64,
        scope_evidence_id="e" * 64,
        combined_bundle_evidence_id="f" * 64,
        target_join_evidence_id="1" * 64,
        target_source_evidence_id="2" * 64,
        raw_target_capture_evidence_id="3" * 64,
        backtest_evidence_id="4" * 64,
        estimator_freeze_evidence_id="5" * 64,
        selected_candidate_id="lagged_gp_affine_ols",
        estimator="ordinary_least_squares",
        parameter_count=2,
        predictors=("lagged_company_gross_profit",),
        training_periods=_PERIODS,
        training_row_count=20,
        scaling_ddof=0,
        predictor_means=(4_112_973.15,),
        predictor_scales=(3_276_259.848587155,),
        standardized_coefficients=(4_868_300.95, 3_608_978.2486053077),
        raw_unit_intercept=337_637.5345664583,
        raw_unit_coefficients=(1.101554337993561,),
        design_rank=2,
        residual_degrees_of_freedom=18,
        condition_number=1.0,
        training_mae_krw_million=766_793.9968575586,
        training_rmse_krw_million=1_081_782.5124146359,
        historical_benchmark_mae_krw_million=1_677_703.75,
        historical_selected_candidate_mae_krw_million=1_249_345.1117558964,
        historical_relative_mae_improvement=0.25532436119553503,
    )


def _raw_payload(*, split_receipt: bool = False) -> dict[str, object]:
    receipt = "20260814000001"
    alternate = "20260814000002"
    revenue = 21_000_000_000_000
    gross = 11_000_000_000_000
    cost = revenue - gross
    common = {
        "sj_div": "IS",
        "bsns_year": "2026",
        "reprt_code": "11012",
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
                    "rcept_no": alternate if split_receipt else receipt,
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


def test_contract_inherits_one_selected_predictor_and_frozen_origin() -> None:
    contract = load_prospective_feature_freeze_contract()
    protocol = load_frozen_company_gp_ex_ante_protocol(contract.protocol_path)

    assert contract.target_period == "2026Q3"
    assert contract.source_period == "2026Q2"
    assert contract.required_selected_candidate_id == "lagged_gp_affine_ols"
    assert contract.required_predictors == ("lagged_company_gross_profit",)
    assert not contract.source_refresh_allowed
    assert contract.early_lock_is_final
    assert protocol.origin_for("2026Q3") == datetime(
        2026, 8, 31, 23, 59, 59, tzinfo=_KST
    )


def test_raw_capture_must_be_not_after_forecast_origin() -> None:
    contract = _contract()
    raw = _raw_payload()

    with pytest.raises(ValueError, match="after forecast origin"):
        build_prospective_source_capture(
            contract,
            historical_execution_evidence_id="d" * 64,
            forecast_origin=datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
            captured_at=datetime(2026, 9, 1, 0, 0, 0, tzinfo=_KST),
            raw_payload=raw,
        )


def test_locked_source_capture_replays_exact_bytes_and_cannot_refresh(tmp_path: Path) -> None:
    contract = _contract()
    raw = _raw_payload()
    capture = build_prospective_source_capture(
        contract,
        historical_execution_evidence_id="d" * 64,
        forecast_origin=datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
        captured_at=datetime(2026, 8, 22, 15, 30, 0, tzinfo=_KST),
        raw_payload=raw,
    )
    pointer = persist_prospective_source_capture(capture, raw, output=tmp_path)
    replayed, replayed_raw = load_prospective_source_capture(pointer)

    assert replayed.evidence_id == capture.evidence_id
    assert replayed_raw == raw

    changed = json.loads(json.dumps(raw))
    financials = changed["financials"]
    assert isinstance(financials, dict)
    rows = financials["list"]
    assert isinstance(rows, list)
    assert isinstance(rows[2], dict)
    rows[2]["thstrm_amount"] = "12000000000000"
    refreshed = build_prospective_source_capture(
        contract,
        historical_execution_evidence_id="d" * 64,
        forecast_origin=capture.forecast_origin,
        captured_at=capture.captured_at,
        raw_payload=changed,
    )
    with pytest.raises(ValueError, match="already locked"):
        persist_prospective_source_capture(refreshed, changed, output=tmp_path)


def test_feature_vector_freezes_only_lagged_gp_and_keeps_q3_sealed() -> None:
    contract = _contract()
    selected = _selected()
    raw = _raw_payload()
    capture = build_prospective_source_capture(
        contract,
        historical_execution_evidence_id=selected.execution_evidence_id,
        forecast_origin=datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
        captured_at=datetime(2026, 8, 22, 15, 30, 0, tzinfo=_KST),
        raw_payload=raw,
    )
    item = build_prospective_feature_vector(
        contract,
        selected,
        protocol_evidence_id="6" * 64,
        historical_execution_evidence_id=selected.execution_evidence_id,
        capture=capture,
        raw_payload=raw,
        revenue_account_ids=("ifrs_Revenue", "ifrs-full_Revenue"),
        cost_of_sales_account_ids=("ifrs_CostOfSales", "ifrs-full_CostOfSales"),
        gross_profit_account_ids=("ifrs_GrossProfit", "ifrs-full_GrossProfit"),
    )

    assert item.predictors == ("lagged_company_gross_profit",)
    assert item.feature_values == (11_000_000.0,)
    assert item.source_receipt_no == "20260814000001"
    assert item.source_available_at < item.frozen_at < item.forecast_origin
    assert item.prospective_feature_vector_frozen
    assert not item.prospective_forecast_run
    assert not item.q3_target_read
    assert not item.q3_source_outcome_loaded
    assert not item.q3_evaluated
    assert not item.numeric_forward_forecast_enabled


def test_feature_vector_rejects_cross_receipt_source_accounts() -> None:
    contract = _contract()
    selected = _selected()
    raw = _raw_payload(split_receipt=True)
    capture = build_prospective_source_capture(
        contract,
        historical_execution_evidence_id=selected.execution_evidence_id,
        forecast_origin=datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
        captured_at=datetime(2026, 8, 22, 15, 30, 0, tzinfo=_KST),
        raw_payload=raw,
    )

    with pytest.raises(ValueError, match="cross filing receipts"):
        build_prospective_feature_vector(
            contract,
            selected,
            protocol_evidence_id="6" * 64,
            historical_execution_evidence_id=selected.execution_evidence_id,
            capture=capture,
            raw_payload=raw,
            revenue_account_ids=("ifrs-full_Revenue",),
            cost_of_sales_account_ids=("ifrs-full_CostOfSales",),
            gross_profit_account_ids=("ifrs-full_GrossProfit",),
        )


def test_feature_vector_rejects_selected_predictor_drift() -> None:
    contract = _contract()
    selected = replace(
        _selected(),
        selected_candidate_id="lagged_gp_nand_mix_ols",
        parameter_count=3,
        predictors=("lagged_company_gross_profit", "lagged_nand_revenue_share"),
        predictor_means=(4_112_973.15, 0.4),
        predictor_scales=(3_276_259.848587155, 0.1),
        standardized_coefficients=(4_868_300.95, 3_608_978.24, 20.0),
        raw_unit_coefficients=(1.1015543, 200.0),
        design_rank=3,
        residual_degrees_of_freedom=17,
    )
    raw = _raw_payload()
    capture = build_prospective_source_capture(
        contract,
        historical_execution_evidence_id=selected.execution_evidence_id,
        forecast_origin=datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
        captured_at=datetime(2026, 8, 22, 15, 30, 0, tzinfo=_KST),
        raw_payload=raw,
    )

    with pytest.raises(ValueError, match="selected candidate binding drifted"):
        build_prospective_feature_vector(
            contract,
            selected,
            protocol_evidence_id="6" * 64,
            historical_execution_evidence_id=selected.execution_evidence_id,
            capture=capture,
            raw_payload=raw,
            revenue_account_ids=("ifrs-full_Revenue",),
            cost_of_sales_account_ids=("ifrs-full_CostOfSales",),
            gross_profit_account_ids=("ifrs-full_GrossProfit",),
        )
