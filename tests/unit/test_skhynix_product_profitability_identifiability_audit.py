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
    assert result.structurally_identifiable is False
    assert result.fit_attempt_allowed is False
    assert result.holdout_evaluation_allowed is False
    assert result.reason == "no_direct_product_profitability_anchors"
    assert result.numeric_forecast_enabled is False
    assert result.fair_value_estimate_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False


def test_method_flags_cannot_bypass_missing_direct_product_profitability_anchor() -> None:
    result = audit_skhynix_product_profitability_identifiability(
        _inventory(),
        _holdout(),
        parameterization_registered=True,
        driver_encoding_method_registered=True,
        numeric_cycle_driver_periods=13,
    )
    assert result.structurally_identifiable is False
    assert result.fit_attempt_allowed is False
    assert result.reason == "no_direct_product_profitability_anchors"


def test_with_anchor_parameterization_and_numeric_driver_contract_pre_fit_gate_can_open() -> None:
    result = audit_skhynix_product_profitability_identifiability(
        _inventory(direct_anchor_periods=("anchor_2022",)),
        _holdout(),
        parameterization_registered=True,
        driver_encoding_method_registered=True,
        numeric_cycle_driver_periods=13,
    )
    assert result.structurally_identifiable is True
    assert result.fit_attempt_allowed is True
    assert result.holdout_evaluation_allowed is False
    assert result.reason == "pre_fit_identification_contract_satisfied"
    assert result.numeric_forecast_enabled is False
