from __future__ import annotations

import pytest

from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProductProfitabilityCalibrationEvidence,
    ProductProfitabilityCalibrationMethod,
    assess_product_profitability_calibration_readiness,
)


def _evidence() -> ProductProfitabilityCalibrationEvidence:
    return ProductProfitabilityCalibrationEvidence(
        direct_product_revenue_evidence_id="r" * 64,
        direct_product_revenue_ready=True,
        historical_periods=("2025Q3", "2025Q4", "2026Q1"),
        holdout_periods=("2026Q2",),
        company_profitability_evidence_ids=("g" * 64,),
        cycle_driver_evidence_ids=("d" * 64, "n" * 64),
        source_evidence_verified=True,
    )


def test_missing_calibration_evidence_stays_fail_closed() -> None:
    evidence = ProductProfitabilityCalibrationEvidence(
        direct_product_revenue_evidence_id="r" * 64,
        direct_product_revenue_ready=True,
        historical_periods=(),
        holdout_periods=(),
        company_profitability_evidence_ids=(),
        cycle_driver_evidence_ids=(),
        source_evidence_verified=True,
    )
    result = assess_product_profitability_calibration_readiness(evidence)
    assert result.calibration_required is True
    assert result.direct_product_profitability_source_fact is False
    assert result.model_input_ready is False
    assert result.method_registered is False
    assert "historical_calibration_periods" in result.missing_requirements
    assert "company_profitability_evidence" in result.missing_requirements
    assert "cycle_driver_evidence" in result.missing_requirements
    assert "holdout_periods" in result.missing_requirements
    assert "calibration_method" in result.missing_requirements
    assert result.numeric_forecast_enabled is False
    assert result.fair_value_estimate_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False


def test_observationally_calibrated_frozen_bound_holdout_method_can_be_model_input() -> None:
    evidence = _evidence()
    method = ProductProfitabilityCalibrationMethod(
        method_id="skhynix_product_margin_structural_calibration",
        method_version="1.0.0",
        status="observationally_calibrated",
        method_version_frozen=True,
        supporting_evidence_ids=evidence.evidence_ids,
        holdout_validated=True,
    )
    result = assess_product_profitability_calibration_readiness(evidence, method)
    assert result.method_registered is True
    assert result.method_status == "observationally_calibrated"
    assert result.method_version_frozen is True
    assert result.method_evidence_bound is True
    assert result.holdout_validated is True
    assert result.prohibited_shortcut_used is False
    assert result.missing_requirements == ()
    assert result.model_input_ready is True
    assert result.direct_product_profitability_source_fact is False
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_documented_but_uncalibrated_method_is_not_model_ready() -> None:
    evidence = _evidence()
    method = ProductProfitabilityCalibrationMethod(
        method_id="skhynix_product_margin_structural_calibration",
        method_version="0.1.0",
        status="documented",
        method_version_frozen=False,
        supporting_evidence_ids=evidence.evidence_ids,
        holdout_validated=False,
    )
    result = assess_product_profitability_calibration_readiness(evidence, method)
    assert result.model_input_ready is False
    assert "observational_calibration" in result.missing_requirements
    assert "frozen_method_version" in result.missing_requirements
    assert "holdout_validation" in result.missing_requirements


def test_prohibited_profit_allocation_shortcut_can_never_be_model_ready() -> None:
    evidence = _evidence()
    method = ProductProfitabilityCalibrationMethod(
        method_id="bad_revenue_share_allocation",
        method_version="1.0.0",
        status="observationally_calibrated",
        method_version_frozen=True,
        supporting_evidence_ids=evidence.evidence_ids,
        holdout_validated=True,
        uses_revenue_share_gross_profit_allocation=True,
    )
    result = assess_product_profitability_calibration_readiness(evidence, method)
    assert result.prohibited_shortcut_used is True
    assert result.model_input_ready is False
    assert "prohibited_allocation_shortcut" in result.missing_requirements


def test_method_must_bind_every_required_source_evidence_id() -> None:
    evidence = _evidence()
    method = ProductProfitabilityCalibrationMethod(
        method_id="incomplete_binding",
        method_version="1.0.0",
        status="observationally_calibrated",
        method_version_frozen=True,
        supporting_evidence_ids=("r" * 64,),
        holdout_validated=True,
    )
    result = assess_product_profitability_calibration_readiness(evidence, method)
    assert result.method_evidence_bound is False
    assert result.model_input_ready is False
    assert "method_evidence_binding" in result.missing_requirements


def test_calibration_and_holdout_periods_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="must be disjoint"):
        ProductProfitabilityCalibrationEvidence(
            direct_product_revenue_evidence_id="r" * 64,
            direct_product_revenue_ready=True,
            historical_periods=("2026Q1",),
            holdout_periods=("2026Q1",),
            company_profitability_evidence_ids=("g" * 64,),
            cycle_driver_evidence_ids=("d" * 64,),
            source_evidence_verified=True,
        )
