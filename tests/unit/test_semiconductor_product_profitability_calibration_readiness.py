from __future__ import annotations

import pytest

from alpha_cycle.intelligence.semiconductor_product_profitability_calibration_readiness import (
    ProductProfitabilityCalibrationMethod,
    ProfitabilityCalibrationEvidenceInventory,
    assess_product_profitability_calibration_readiness,
)

_EVIDENCE = "a" * 64


def _inventory(
    *,
    direct_targets: int = 0,
    product_revenue: int = 0,
    company_profitability: int = 0,
    drivers: int = 0,
    holdout: int = 0,
    verified: bool = False,
) -> ProfitabilityCalibrationEvidenceInventory:
    return ProfitabilityCalibrationEvidenceInventory(
        ticker="000660",
        direct_product_profitability_periods=direct_targets,
        historical_product_revenue_periods=product_revenue,
        company_profitability_periods=company_profitability,
        cycle_driver_periods=drivers,
        holdout_periods=holdout,
        supporting_evidence_ids=(_EVIDENCE,) if verified else (),
        supporting_evidence_verified=verified,
    )


def _method(
    *,
    documented: bool = True,
    validated: bool = False,
    frozen: bool = False,
) -> ProductProfitabilityCalibrationMethod:
    return ProductProfitabilityCalibrationMethod(
        method_id="skhynix_product_profitability_structural_v1",
        method_version="0.1",
        identification_strategy="aggregate_structural_model",
        target_metric="gross_profit_or_margin",
        target_product_blocks=("dram_total", "nand_and_solutions"),
        minimum_direct_target_periods=0,
        minimum_product_revenue_periods=4,
        minimum_company_profitability_periods=4,
        minimum_cycle_driver_periods=4,
        minimum_holdout_periods=1,
        method_documented=documented,
        historical_validation_complete=validated,
        method_version_frozen=frozen,
    )


def test_no_method_cannot_be_declared_ready_from_data_counts_alone() -> None:
    result = assess_product_profitability_calibration_readiness(
        _inventory(
            product_revenue=20,
            company_profitability=20,
            drivers=20,
            holdout=5,
            verified=True,
        ),
        method=None,
    )
    assert result.status == "identification_method_not_selected"
    assert result.identification_method_selected is False
    assert result.evidence_thresholds_met is False
    assert result.operating_assumption_model_use_ready is False
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_documented_method_reports_exact_missing_evidence_categories() -> None:
    result = assess_product_profitability_calibration_readiness(
        _inventory(product_revenue=1),
        method=_method(),
    )
    assert result.status == "calibration_evidence_incomplete"
    assert result.missing_evidence_categories == (
        "historical_product_revenue",
        "company_profitability",
        "cycle_driver_history",
        "holdout_history",
    )
    assert result.evidence_thresholds_met is False
    assert result.operating_assumption_model_use_ready is False


def test_verified_complete_history_is_still_blocked_until_holdout_validation() -> None:
    result = assess_product_profitability_calibration_readiness(
        _inventory(
            product_revenue=6,
            company_profitability=6,
            drivers=6,
            holdout=2,
            verified=True,
        ),
        method=_method(validated=False, frozen=False),
    )
    assert result.evidence_thresholds_met is True
    assert result.status == "historical_validation_incomplete"
    assert result.operating_assumption_model_use_ready is False


def test_validated_method_is_still_blocked_until_version_is_frozen() -> None:
    result = assess_product_profitability_calibration_readiness(
        _inventory(
            product_revenue=6,
            company_profitability=6,
            drivers=6,
            holdout=2,
            verified=True,
        ),
        method=_method(validated=True, frozen=False),
    )
    assert result.status == "calibration_method_not_frozen"
    assert result.operating_assumption_model_use_ready is False


def test_observationally_calibrated_method_only_unlocks_assumption_model_use() -> None:
    result = assess_product_profitability_calibration_readiness(
        _inventory(
            product_revenue=6,
            company_profitability=6,
            drivers=6,
            holdout=2,
            verified=True,
        ),
        method=_method(validated=True, frozen=True),
    )
    assert result.status == "observationally_calibrated"
    assert result.missing_evidence_categories == ()
    assert result.operating_assumption_model_use_ready is True
    assert result.source_fact is False
    assert result.numeric_forecast_enabled is False
    assert result.fair_value_estimate_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False


def test_calibration_inventory_rejects_unverified_claim_without_evidence_ids() -> None:
    with pytest.raises(ValueError, match="requires evidence IDs"):
        ProfitabilityCalibrationEvidenceInventory(
            ticker="000660",
            direct_product_profitability_periods=0,
            historical_product_revenue_periods=1,
            company_profitability_periods=1,
            cycle_driver_periods=1,
            holdout_periods=1,
            supporting_evidence_ids=(),
            supporting_evidence_verified=True,
        )


def test_completed_validation_requires_a_holdout_requirement() -> None:
    with pytest.raises(ValueError, match="holdout requirement"):
        ProductProfitabilityCalibrationMethod(
            method_id="bad",
            method_version="1",
            identification_strategy="aggregate_structural_model",
            target_metric="gross_profit_or_margin",
            target_product_blocks=("dram_total", "nand_and_solutions"),
            minimum_direct_target_periods=0,
            minimum_product_revenue_periods=1,
            minimum_company_profitability_periods=1,
            minimum_cycle_driver_periods=1,
            minimum_holdout_periods=0,
            method_documented=True,
            historical_validation_complete=True,
            method_version_frozen=False,
        )
