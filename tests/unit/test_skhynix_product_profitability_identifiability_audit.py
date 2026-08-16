from __future__ import annotations

from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProfitabilityCalibrationEvidenceInventory,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_holdout import (
    ProductProfitabilityRetrospectiveHoldoutPlan,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_identifiability_audit import (
    audit_skhynix_product_profitability_identifiability,
)


def _inventory(*, direct_anchor_periods: tuple[str, ...] = ()):
    return ProfitabilityCalibrationEvidenceInventory(
        direct_product_revenue_evidence_id="d" * 64,
        direct_product_revenue_ready=True,
        direct_product_profitability_periods=direct_anchor_periods,
        historical_product_revenue_periods=("fy2023", "fy2024", "q1_2025"),
        company_profitability_constraint_periods=("fy2023", "fy2024", "q1_2025"),
        cycle_driver_history_periods=tuple(
            f"{year}Q{quarter}"
            for year, quarters in ((2023, 4), (2024, 4), (2025, 4), (2026, 1))
            for quarter in range(1, quarters + 1)
        ),
        holdout_periods=("q1_2026",),
        verified_evidence_ids=("a" * 64, "c" * 64),
        source_evidence_verified=True,
    )


def _holdout():
    return ProductProfitabilityRetrospectiveHoldoutPlan(
        evidence_id="e" * 64,
        source_profitability_support_evidence_id="a" * 64,
        calibration_period_ids=("fy2023", "fy2024", "q1_2025"),
        holdout_period_ids=("q1_2026",),
        holdout_cycle_driver_period_ids=("2026Q1",),
    )


def test_current_evidence_remains_structurally_unidentified_before_fitting() -> None:
    result = audit_skhynix_product_profitability_identifiability(_inventory(), _holdout())
    assert result.direct_product_profitability_anchor_periods == 0
    assert result.calibration_company_profitability_constraints == 3
    assert result.calibration_product_revenue_periods == 3
    assert result.textual_cycle_driver_periods == 13
    assert result.numeric_cycle_driver_periods == 0
    assert result.holdout_periods == 1
    assert result.registered_parameter_count == 0
    assert result.independent_training_constraint_count == 3
    assert result.structurally_identifiable is False
    assert result.fit_attempt_allowed is False
    assert result.holdout_evaluation_allowed is False
    assert result.reason == "structural_parameterization_not_registered"
    assert result.numeric_forecast_enabled is False
    assert result.fair_value_estimate_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False


def test_parameterization_and_driver_encoding_still_require_temporal_alignment() -> None:
    result = audit_skhynix_product_profitability_identifiability(
        _inventory(),
        _holdout(),
        parameterization_registered=True,
        registered_parameter_count=2,
        driver_encoding_method_registered=True,
        numeric_cycle_driver_periods=13,
    )
    assert result.structurally_identifiable is False
    assert result.fit_attempt_allowed is False
    assert result.reason == "cycle_driver_profitability_temporal_alignment_not_registered"


def test_full_rank_two_parameter_aggregate_design_can_be_identifiable() -> None:
    result = audit_skhynix_product_profitability_identifiability(
        _inventory(),
        _holdout(),
        parameterization_registered=True,
        registered_parameter_count=2,
        driver_encoding_method_registered=True,
        numeric_cycle_driver_periods=13,
        temporal_alignment_method_registered=True,
        design_rank_certified=True,
    )
    assert result.direct_product_profitability_anchor_periods == 0
    assert result.independent_training_constraint_count == 3
    assert result.structurally_identifiable is True
    assert result.fit_attempt_allowed is True
    assert result.holdout_evaluation_allowed is False
    assert result.reason == "pre_fit_identification_contract_satisfied"
    assert result.numeric_forecast_enabled is False


def test_more_parameters_than_independent_training_constraints_remain_blocked() -> None:
    result = audit_skhynix_product_profitability_identifiability(
        _inventory(direct_anchor_periods=("anchor_2022",)),
        _holdout(),
        parameterization_registered=True,
        registered_parameter_count=5,
        driver_encoding_method_registered=True,
        numeric_cycle_driver_periods=13,
        temporal_alignment_method_registered=True,
        design_rank_certified=False,
    )
    assert result.independent_training_constraint_count == 4
    assert result.structurally_identifiable is False
    assert result.reason == "insufficient_independent_training_constraints"
