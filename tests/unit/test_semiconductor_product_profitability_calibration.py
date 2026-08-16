from __future__ import annotations

import pytest

from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProductProfitabilityCalibrationMethod,
    ProfitabilityCalibrationEvidenceInventory,
    assess_product_profitability_calibration_readiness,
)


def _inventory() -> ProfitabilityCalibrationEvidenceInventory:
    return ProfitabilityCalibrationEvidenceInventory(
        direct_product_revenue_evidence_id="r" * 64,
        direct_product_revenue_ready=True,
        direct_product_profitability_periods=(),
        historical_product_revenue_periods=("2025Q3", "2025Q4", "2026Q1"),
        company_profitability_constraint_periods=("2025Q3", "2025Q4", "2026Q1"),
        cycle_driver_history_periods=("2025Q3", "2025Q4", "2026Q1"),
        holdout_periods=("2026Q2",),
        verified_evidence_ids=("g" * 64, "d" * 64, "n" * 64),
        source_evidence_verified=True,
    )


def _method(
    inventory: ProfitabilityCalibrationEvidenceInventory,
    *,
    documented: bool = True,
    historical_validated: bool = True,
    holdout_validated: bool = True,
    frozen: bool = True,
    supporting_evidence_ids: tuple[str, ...] | None = None,
    revenue_share_shortcut: bool = False,
) -> ProductProfitabilityCalibrationMethod:
    return ProductProfitabilityCalibrationMethod(
        method_id="skhynix_product_margin_structural_calibration",
        method_version="1.0.0",
        identification_strategy="aggregate_structural_model",
        target_metric="gross_margin",
        target_product_blocks=("dram_total", "nand_and_solutions"),
        minimum_direct_target_periods=0,
        minimum_product_revenue_periods=3,
        minimum_company_profitability_periods=3,
        minimum_cycle_driver_periods=3,
        minimum_holdout_periods=1,
        method_documented=documented,
        historical_validation_complete=historical_validated,
        holdout_validation_complete=holdout_validated,
        method_version_frozen=frozen,
        supporting_evidence_ids=(
            inventory.all_required_evidence_ids
            if supporting_evidence_ids is None
            else supporting_evidence_ids
        ),
        uses_revenue_share_gross_profit_allocation=revenue_share_shortcut,
    )


def test_unselected_identification_method_stays_fail_closed_without_inventing_sample_rule() -> None:
    result = assess_product_profitability_calibration_readiness(_inventory())
    assert result.status == "identification_method_not_selected"
    assert result.calibration_required is True
    assert result.direct_product_profitability_source_fact is False
    assert result.method_registered is False
    assert result.model_input_ready is False
    assert result.missing_requirements == ("identification_method",)
    assert result.numeric_forecast_enabled is False
    assert result.fair_value_estimate_enabled is False
    assert result.target_price_enabled is False
    assert result.decision_score_enabled is False


def test_documented_method_declares_its_own_evidence_minimums() -> None:
    inventory = ProfitabilityCalibrationEvidenceInventory(
        direct_product_revenue_evidence_id="r" * 64,
        direct_product_revenue_ready=True,
        direct_product_profitability_periods=(),
        historical_product_revenue_periods=("2026Q1",),
        company_profitability_constraint_periods=("2026Q1",),
        cycle_driver_history_periods=("2026Q1",),
        holdout_periods=(),
        verified_evidence_ids=("g" * 64,),
        source_evidence_verified=True,
    )
    result = assess_product_profitability_calibration_readiness(
        inventory,
        _method(inventory),
    )
    assert result.status == "calibration_evidence_incomplete"
    assert result.model_input_ready is False
    assert "historical_product_revenue_periods" in result.missing_requirements
    assert "company_profitability_constraint_periods" in result.missing_requirements
    assert "cycle_driver_history_periods" in result.missing_requirements
    assert "holdout_periods" in result.missing_requirements


def test_observationally_calibrated_frozen_bound_holdout_method_can_be_model_input() -> None:
    inventory = _inventory()
    result = assess_product_profitability_calibration_readiness(
        inventory,
        _method(inventory),
    )
    assert result.status == "observationally_calibrated"
    assert result.method_registered is True
    assert result.method_documented is True
    assert result.identification_strategy == "aggregate_structural_model"
    assert result.method_version_frozen is True
    assert result.method_evidence_bound is True
    assert result.historical_validation_complete is True
    assert result.holdout_validation_complete is True
    assert result.prohibited_shortcut_used is False
    assert result.missing_requirements == ()
    assert result.model_input_ready is True
    assert result.direct_product_profitability_source_fact is False
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_unvalidated_method_cannot_become_model_ready() -> None:
    inventory = _inventory()
    result = assess_product_profitability_calibration_readiness(
        inventory,
        _method(inventory, historical_validated=False, holdout_validated=False),
    )
    assert result.status == "historical_validation_incomplete"
    assert result.model_input_ready is False
    assert "historical_validation" in result.missing_requirements
    assert "holdout_validation" in result.missing_requirements


def test_method_must_be_frozen_after_validation() -> None:
    inventory = _inventory()
    result = assess_product_profitability_calibration_readiness(
        inventory,
        _method(inventory, frozen=False),
    )
    assert result.status == "calibration_method_not_frozen"
    assert result.model_input_ready is False
    assert result.missing_requirements == ("frozen_method_version",)


def test_prohibited_profit_allocation_shortcut_can_never_be_model_ready() -> None:
    inventory = _inventory()
    result = assess_product_profitability_calibration_readiness(
        inventory,
        _method(inventory, revenue_share_shortcut=True),
    )
    assert result.status == "prohibited_allocation_shortcut"
    assert result.prohibited_shortcut_used is True
    assert result.model_input_ready is False
    assert result.missing_requirements == ("prohibited_allocation_shortcut",)


def test_method_must_bind_every_required_source_evidence_id() -> None:
    inventory = _inventory()
    result = assess_product_profitability_calibration_readiness(
        inventory,
        _method(inventory, supporting_evidence_ids=("r" * 64,)),
    )
    assert result.status == "calibration_evidence_unverified"
    assert result.method_evidence_bound is False
    assert result.model_input_ready is False
    assert result.missing_requirements == ("method_evidence_binding",)


def test_calibration_product_revenue_and_holdout_periods_must_be_disjoint() -> None:
    with pytest.raises(ValueError, match="must be disjoint"):
        ProfitabilityCalibrationEvidenceInventory(
            direct_product_revenue_evidence_id="r" * 64,
            direct_product_revenue_ready=True,
            direct_product_profitability_periods=(),
            historical_product_revenue_periods=("2026Q1",),
            company_profitability_constraint_periods=("2026Q1",),
            cycle_driver_history_periods=("2026Q1",),
            holdout_periods=("2026Q1",),
            verified_evidence_ids=("g" * 64,),
            source_evidence_verified=True,
        )
