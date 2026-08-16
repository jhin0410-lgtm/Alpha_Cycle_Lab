"""Structural identifiability audit for latent SK hynix DRAM/NAND profitability.

This audit runs before any parameter estimation. Aggregate company gross-profit
constraints and textual product-cycle-driver bands are useful calibration support, but
they do not by themselves identify two separately varying product margins. A method may
only proceed after an explicit low-dimensional parameterization and a numeric/interval
encoding contract are registered and independently reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProfitabilityCalibrationEvidenceInventory,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_holdout import (
    ProductProfitabilityRetrospectiveHoldoutPlan,
)


@dataclass(frozen=True)
class ProductProfitabilityIdentifiabilityAudit:
    target_product_blocks: tuple[str, ...]
    direct_product_profitability_anchor_periods: int
    calibration_company_profitability_constraints: int
    calibration_product_revenue_periods: int
    textual_cycle_driver_periods: int
    numeric_cycle_driver_periods: int
    holdout_periods: int
    parameterization_registered: bool
    driver_encoding_method_registered: bool
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
            self.textual_cycle_driver_periods,
            self.numeric_cycle_driver_periods,
            self.holdout_periods,
        )
        if any(value < 0 for value in counts):
            raise ValueError("SK hynix profitability audit counts cannot be negative")
        if self.numeric_cycle_driver_periods > self.textual_cycle_driver_periods:
            raise ValueError("Numeric cycle-driver coverage cannot exceed source-text coverage")
        ready = (
            self.parameterization_registered
            and self.driver_encoding_method_registered
            and self.direct_product_profitability_anchor_periods > 0
        )
        if self.structurally_identifiable and not ready:
            raise ValueError("Profitability audit cannot claim identification without anchors/methods")
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
    driver_encoding_method_registered: bool = False,
    numeric_cycle_driver_periods: int = 0,
) -> ProductProfitabilityIdentifiabilityAudit:
    """Fail closed unless the missing identification contracts are explicitly supplied."""

    if holdout.source_profitability_support_evidence_id not in inventory.verified_evidence_ids:
        raise ValueError("Profitability holdout is not bound to the calibration inventory")
    if tuple(inventory.holdout_periods) != holdout.holdout_period_ids:
        raise ValueError("Profitability inventory and holdout period bindings disagree")
    if set(inventory.historical_product_revenue_periods) != set(holdout.calibration_period_ids):
        raise ValueError("Profitability inventory fit periods do not match the holdout plan")

    direct_anchors = len(inventory.direct_product_profitability_periods)
    company_constraints = len(inventory.company_profitability_constraint_periods)
    product_revenue_periods = len(inventory.historical_product_revenue_periods)
    textual_drivers = len(inventory.cycle_driver_history_periods)

    identifiable = bool(
        direct_anchors > 0
        and parameterization_registered
        and driver_encoding_method_registered
        and numeric_cycle_driver_periods > 0
    )
    if direct_anchors == 0:
        reason = "no_direct_product_profitability_anchors"
    elif not parameterization_registered:
        reason = "structural_parameterization_not_registered"
    elif not driver_encoding_method_registered or numeric_cycle_driver_periods == 0:
        reason = "cycle_driver_numeric_encoding_not_registered"
    else:
        reason = "pre_fit_identification_contract_satisfied"

    return ProductProfitabilityIdentifiabilityAudit(
        target_product_blocks=("dram_total", "nand_and_solutions"),
        direct_product_profitability_anchor_periods=direct_anchors,
        calibration_company_profitability_constraints=company_constraints,
        calibration_product_revenue_periods=product_revenue_periods,
        textual_cycle_driver_periods=textual_drivers,
        numeric_cycle_driver_periods=numeric_cycle_driver_periods,
        holdout_periods=len(inventory.holdout_periods),
        parameterization_registered=parameterization_registered,
        driver_encoding_method_registered=driver_encoding_method_registered,
        structurally_identifiable=identifiable,
        fit_attempt_allowed=identifiable,
        holdout_evaluation_allowed=False,
        reason=reason,
    )


__all__ = [
    "ProductProfitabilityIdentifiabilityAudit",
    "audit_skhynix_product_profitability_identifiability",
]
