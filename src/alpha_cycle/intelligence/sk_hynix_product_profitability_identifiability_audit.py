"""Structural identifiability audit for latent SK hynix DRAM/NAND profitability.

A company-profitability observation contributes a structural equation only when direct
product revenue is observed for the same economic period. Source modules historically
used both ``q1_2025`` and ``2025Q1`` naming, so the audit canonicalizes period aliases
before counting equations and before checking holdout leakage.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProfitabilityCalibrationEvidenceInventory,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_holdout import (
    ProductProfitabilityRetrospectiveHoldoutPlan,
)


def _canonical_period_id(value: str) -> str:
    text = value.strip()
    if text.startswith("q1_") and len(text) == 7 and text[3:].isdigit():
        return f"{text[3:]}Q1"
    if text.startswith("fy") and len(text) == 6 and text[2:].isdigit():
        return f"{text[2:]}FY"
    return text


def _canonical_periods(values: tuple[str, ...]) -> set[str]:
    return {_canonical_period_id(value) for value in values}


@dataclass(frozen=True)
class ProductProfitabilityIdentifiabilityAudit:
    target_product_blocks: tuple[str, ...]
    direct_product_profitability_anchor_periods: int
    calibration_company_profitability_constraints: int
    calibration_product_revenue_periods: int
    aligned_company_product_constraint_periods: int
    textual_cycle_driver_periods: int
    numeric_cycle_driver_periods: int
    holdout_periods: int
    registered_parameter_count: int
    independent_training_constraint_count: int
    parameterization_registered: bool
    driver_encoding_method_registered: bool
    temporal_alignment_method_registered: bool
    design_rank_certified: bool
    structurally_identifiable: bool
    fit_attempt_allowed: bool
    holdout_evaluation_allowed: bool
    reason: str
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if self.target_product_blocks != ("dram_total", "nand_and_solutions"):
            raise ValueError("SK hynix profitability audit target blocks are invalid")
        counts = (
            self.direct_product_profitability_anchor_periods,
            self.calibration_company_profitability_constraints,
            self.calibration_product_revenue_periods,
            self.aligned_company_product_constraint_periods,
            self.textual_cycle_driver_periods,
            self.numeric_cycle_driver_periods,
            self.holdout_periods,
            self.registered_parameter_count,
            self.independent_training_constraint_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("SK hynix profitability audit counts cannot be negative")
        if (
            self.aligned_company_product_constraint_periods
            > self.calibration_product_revenue_periods
        ):
            raise ValueError("Aligned profitability constraints exceed product-revenue periods")
        if (
            self.aligned_company_product_constraint_periods
            > self.calibration_company_profitability_constraints
        ):
            raise ValueError("Aligned profitability constraints exceed company constraints")
        if self.numeric_cycle_driver_periods > self.textual_cycle_driver_periods:
            raise ValueError("Numeric cycle-driver coverage cannot exceed source-text coverage")
        if self.design_rank_certified and self.registered_parameter_count <= 0:
            raise ValueError("Certified profitability design rank requires registered parameters")
        prerequisites = (
            self.parameterization_registered
            and self.driver_encoding_method_registered
            and self.temporal_alignment_method_registered
            and self.numeric_cycle_driver_periods > 0
            and self.registered_parameter_count > 0
            and self.independent_training_constraint_count >= self.registered_parameter_count
            and self.design_rank_certified
        )
        if self.structurally_identifiable != prerequisites:
            raise ValueError("Profitability audit structural-identification result is inconsistent")
        if self.fit_attempt_allowed != self.structurally_identifiable:
            raise ValueError("Profitability audit fit gate is inconsistent")
        if self.holdout_evaluation_allowed:
            raise ValueError("Pre-fit profitability audit cannot open holdout evaluation")
        if (
            self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Profitability identifiability audit exceeds its trust boundary")


def audit_skhynix_product_profitability_identifiability(
    inventory: ProfitabilityCalibrationEvidenceInventory,
    holdout: ProductProfitabilityRetrospectiveHoldoutPlan,
    *,
    parameterization_registered: bool = False,
    registered_parameter_count: int = 0,
    driver_encoding_method_registered: bool = False,
    numeric_cycle_driver_periods: int = 0,
    temporal_alignment_method_registered: bool = False,
    design_rank_certified: bool = False,
) -> ProductProfitabilityIdentifiabilityAudit:
    """Fail closed until a period-aligned aggregate structural design is identified."""

    if holdout.source_profitability_support_evidence_id not in inventory.verified_evidence_ids:
        raise ValueError("Profitability holdout is not bound to the calibration inventory")
    if tuple(inventory.holdout_periods) != holdout.holdout_period_ids:
        raise ValueError("Profitability inventory and holdout period bindings disagree")

    company_periods = _canonical_periods(inventory.company_profitability_constraint_periods)
    product_periods = _canonical_periods(inventory.historical_product_revenue_periods)
    holdout_keys = _canonical_periods(
        (*holdout.holdout_period_ids, *holdout.holdout_cycle_driver_period_ids)
    )
    required_fit_keys = _canonical_periods(holdout.calibration_period_ids)
    if not required_fit_keys.issubset(product_periods):
        raise ValueError("Profitability inventory lost required fit periods from holdout plan")
    if product_periods & holdout_keys:
        raise ValueError("Profitability product-revenue fit view contains holdout period")
    if company_periods & holdout_keys:
        raise ValueError("Profitability company fit view contains holdout period")

    direct_anchors = len(inventory.direct_product_profitability_periods)
    company_constraints = len(company_periods)
    product_revenue_periods = len(product_periods)
    aligned_constraints = len(company_periods & product_periods)
    textual_drivers = len(inventory.cycle_driver_history_periods)
    independent_constraints = aligned_constraints + direct_anchors

    identifiable = bool(
        parameterization_registered
        and driver_encoding_method_registered
        and temporal_alignment_method_registered
        and numeric_cycle_driver_periods > 0
        and registered_parameter_count > 0
        and independent_constraints >= registered_parameter_count
        and design_rank_certified
    )
    if not parameterization_registered or registered_parameter_count <= 0:
        reason = "structural_parameterization_not_registered"
    elif not driver_encoding_method_registered or numeric_cycle_driver_periods == 0:
        reason = "cycle_driver_numeric_encoding_not_registered"
    elif not temporal_alignment_method_registered:
        reason = "cycle_driver_profitability_temporal_alignment_not_registered"
    elif independent_constraints < registered_parameter_count:
        reason = "insufficient_period_aligned_training_constraints"
    elif not design_rank_certified:
        reason = "structural_design_rank_not_certified"
    else:
        reason = "pre_fit_identification_contract_satisfied"

    return ProductProfitabilityIdentifiabilityAudit(
        target_product_blocks=("dram_total", "nand_and_solutions"),
        direct_product_profitability_anchor_periods=direct_anchors,
        calibration_company_profitability_constraints=company_constraints,
        calibration_product_revenue_periods=product_revenue_periods,
        aligned_company_product_constraint_periods=aligned_constraints,
        textual_cycle_driver_periods=textual_drivers,
        numeric_cycle_driver_periods=numeric_cycle_driver_periods,
        holdout_periods=len(inventory.holdout_periods),
        registered_parameter_count=registered_parameter_count,
        independent_training_constraint_count=independent_constraints,
        parameterization_registered=parameterization_registered,
        driver_encoding_method_registered=driver_encoding_method_registered,
        temporal_alignment_method_registered=temporal_alignment_method_registered,
        design_rank_certified=design_rank_certified,
        structurally_identifiable=identifiable,
        fit_attempt_allowed=identifiable,
        holdout_evaluation_allowed=False,
        reason=reason,
    )


__all__ = [
    "ProductProfitabilityIdentifiabilityAudit",
    "_canonical_period_id",
    "audit_skhynix_product_profitability_identifiability",
]
