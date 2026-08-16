"""Evidence-bound calibration gate for latent semiconductor product profitability.

Direct product revenue can be a certified source fact even when product-level gross
profit or gross margin is not directly disclosed. This module keeps those concepts
separate. It never turns an allocation heuristic into a source fact and it cannot by
itself enable a numeric forecast, valuation, target price, or decision score.
"""

from __future__ import annotations

from dataclasses import dataclass

_ALLOWED_IDENTIFICATION_STRATEGIES = frozenset(
    {"direct_target_model", "aggregate_structural_model"}
)
_ALLOWED_READINESS_STATUSES = frozenset(
    {
        "identification_method_not_selected",
        "calibration_method_not_documented",
        "calibration_evidence_incomplete",
        "calibration_evidence_unverified",
        "historical_validation_incomplete",
        "calibration_method_not_frozen",
        "prohibited_allocation_shortcut",
        "observationally_calibrated",
    }
)


@dataclass(frozen=True)
class ProfitabilityCalibrationEvidenceInventory:
    """Observed evidence inventory; no product margin is estimated here."""

    direct_product_revenue_evidence_id: str
    direct_product_revenue_ready: bool
    direct_product_profitability_periods: tuple[str, ...]
    historical_product_revenue_periods: tuple[str, ...]
    company_profitability_constraint_periods: tuple[str, ...]
    cycle_driver_history_periods: tuple[str, ...]
    holdout_periods: tuple[str, ...]
    verified_evidence_ids: tuple[str, ...]
    source_evidence_verified: bool

    def __post_init__(self) -> None:
        if self.direct_product_revenue_ready and not self.direct_product_revenue_evidence_id:
            raise ValueError("Direct product revenue readiness requires an evidence id")
        period_groups = (
            self.direct_product_profitability_periods,
            self.historical_product_revenue_periods,
            self.company_profitability_constraint_periods,
            self.cycle_driver_history_periods,
            self.holdout_periods,
        )
        if any(len(set(group)) != len(group) for group in period_groups):
            raise ValueError("Profitability calibration periods must be unique within a group")
        calibration_periods = set(self.historical_product_revenue_periods)
        if calibration_periods & set(self.holdout_periods):
            raise ValueError("Calibration product-revenue and holdout periods must be disjoint")
        if len(set(self.verified_evidence_ids)) != len(self.verified_evidence_ids):
            raise ValueError("Verified profitability calibration evidence ids must be unique")

    @property
    def all_required_evidence_ids(self) -> tuple[str, ...]:
        values = (self.direct_product_revenue_evidence_id, *self.verified_evidence_ids)
        return tuple(dict.fromkeys(item for item in values if item))


@dataclass(frozen=True)
class ProductProfitabilityCalibrationMethod:
    """Explicit identification and validation contract for latent product margins."""

    method_id: str
    method_version: str
    identification_strategy: str
    target_metric: str
    target_product_blocks: tuple[str, ...]
    minimum_direct_target_periods: int
    minimum_product_revenue_periods: int
    minimum_company_profitability_periods: int
    minimum_cycle_driver_periods: int
    minimum_holdout_periods: int
    method_documented: bool
    historical_validation_complete: bool
    holdout_validation_complete: bool
    method_version_frozen: bool
    supporting_evidence_ids: tuple[str, ...]
    uses_revenue_share_gross_profit_allocation: bool = False
    uses_residual_profit_allocation: bool = False
    uses_peer_margin_as_source_fact: bool = False

    def __post_init__(self) -> None:
        if not self.method_id or not self.method_version:
            raise ValueError("Profitability calibration method id/version must be explicit")
        if self.identification_strategy not in _ALLOWED_IDENTIFICATION_STRATEGIES:
            raise ValueError("Unsupported profitability calibration identification strategy")
        if not self.target_metric.strip():
            raise ValueError("Profitability calibration target metric must be explicit")
        if not self.target_product_blocks or len(set(self.target_product_blocks)) != len(
            self.target_product_blocks
        ):
            raise ValueError("Profitability calibration target product blocks must be unique")
        minimums = (
            self.minimum_direct_target_periods,
            self.minimum_product_revenue_periods,
            self.minimum_company_profitability_periods,
            self.minimum_cycle_driver_periods,
            self.minimum_holdout_periods,
        )
        if any(value < 0 for value in minimums):
            raise ValueError("Profitability calibration evidence minimums cannot be negative")
        if len(set(self.supporting_evidence_ids)) != len(self.supporting_evidence_ids):
            raise ValueError("Profitability calibration method evidence ids must be unique")

    @property
    def prohibited_shortcut_used(self) -> bool:
        return any(
            (
                self.uses_revenue_share_gross_profit_allocation,
                self.uses_residual_profit_allocation,
                self.uses_peer_margin_as_source_fact,
            )
        )


@dataclass(frozen=True)
class ProductProfitabilityCalibrationReadiness:
    """Fail-closed readiness result for a calibrated profitability assumption."""

    status: str
    calibration_required: bool
    direct_product_profitability_source_fact: bool
    direct_product_revenue_ready: bool
    source_evidence_verified: bool
    method_registered: bool
    method_documented: bool
    identification_strategy: str
    method_version_frozen: bool
    method_evidence_bound: bool
    historical_validation_complete: bool
    holdout_validation_complete: bool
    prohibited_shortcut_used: bool
    model_input_ready: bool
    missing_requirements: tuple[str, ...]
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_READINESS_STATUSES:
            raise ValueError("Product-profitability calibration readiness status is invalid")
        if self.direct_product_profitability_source_fact:
            raise ValueError("Calibrated product profitability cannot become a source fact")
        if self.model_input_ready != (self.status == "observationally_calibrated"):
            raise ValueError("Profitability calibration readiness status/model gate mismatch")
        if (
            self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Profitability calibration gate cannot enable downstream outputs")


def _evidence_count_requirements(
    inventory: ProfitabilityCalibrationEvidenceInventory,
    method: ProductProfitabilityCalibrationMethod,
) -> tuple[str, ...]:
    missing: list[str] = []
    if len(inventory.direct_product_profitability_periods) < method.minimum_direct_target_periods:
        missing.append("direct_product_profitability_periods")
    if len(inventory.historical_product_revenue_periods) < method.minimum_product_revenue_periods:
        missing.append("historical_product_revenue_periods")
    if (
        len(inventory.company_profitability_constraint_periods)
        < method.minimum_company_profitability_periods
    ):
        missing.append("company_profitability_constraint_periods")
    if len(inventory.cycle_driver_history_periods) < method.minimum_cycle_driver_periods:
        missing.append("cycle_driver_history_periods")
    if len(inventory.holdout_periods) < method.minimum_holdout_periods:
        missing.append("holdout_periods")
    return tuple(missing)


def assess_product_profitability_calibration_readiness(
    inventory: ProfitabilityCalibrationEvidenceInventory,
    method: ProductProfitabilityCalibrationMethod | None = None,
) -> ProductProfitabilityCalibrationReadiness:
    """Evaluate a documented calibration method without estimating product margins."""

    method_registered = method is not None
    strategy = method.identification_strategy if method is not None else "unselected"
    method_documented = method.method_documented if method is not None else False
    method_frozen = method.method_version_frozen if method is not None else False
    historical_validated = (
        method.historical_validation_complete if method is not None else False
    )
    holdout_validated = method.holdout_validation_complete if method is not None else False
    prohibited_shortcut = method.prohibited_shortcut_used if method is not None else False

    required_ids = set(inventory.all_required_evidence_ids)
    bound_ids = set(method.supporting_evidence_ids) if method is not None else set()
    evidence_bound = bool(required_ids) and required_ids.issubset(bound_ids)

    missing: list[str] = []
    if not inventory.direct_product_revenue_ready:
        missing.append("direct_product_revenue")

    if method is None:
        status = "identification_method_not_selected"
        missing.append("identification_method")
    elif not method.method_documented:
        status = "calibration_method_not_documented"
        missing.append("documented_calibration_method")
    else:
        evidence_missing = _evidence_count_requirements(inventory, method)
        missing.extend(evidence_missing)
        if evidence_missing:
            status = "calibration_evidence_incomplete"
        elif not inventory.source_evidence_verified or not evidence_bound:
            status = "calibration_evidence_unverified"
            if not inventory.source_evidence_verified:
                missing.append("verified_source_evidence")
            if not evidence_bound:
                missing.append("method_evidence_binding")
        elif not method.historical_validation_complete or not method.holdout_validation_complete:
            status = "historical_validation_incomplete"
            if not method.historical_validation_complete:
                missing.append("historical_validation")
            if not method.holdout_validation_complete:
                missing.append("holdout_validation")
        elif not method.method_version_frozen:
            status = "calibration_method_not_frozen"
            missing.append("frozen_method_version")
        elif prohibited_shortcut:
            status = "prohibited_allocation_shortcut"
            missing.append("prohibited_allocation_shortcut")
        elif not inventory.direct_product_revenue_ready:
            status = "calibration_evidence_incomplete"
        else:
            status = "observationally_calibrated"

    return ProductProfitabilityCalibrationReadiness(
        status=status,
        calibration_required=True,
        direct_product_profitability_source_fact=False,
        direct_product_revenue_ready=inventory.direct_product_revenue_ready,
        source_evidence_verified=inventory.source_evidence_verified,
        method_registered=method_registered,
        method_documented=method_documented,
        identification_strategy=strategy,
        method_version_frozen=method_frozen,
        method_evidence_bound=evidence_bound,
        historical_validation_complete=historical_validated,
        holdout_validation_complete=holdout_validated,
        prohibited_shortcut_used=prohibited_shortcut,
        model_input_ready=status == "observationally_calibrated",
        missing_requirements=tuple(dict.fromkeys(missing)),
    )


# Compatibility alias for early callers on the feature branch.
ProductProfitabilityCalibrationEvidence = ProfitabilityCalibrationEvidenceInventory


__all__ = [
    "ProductProfitabilityCalibrationEvidence",
    "ProfitabilityCalibrationEvidenceInventory",
    "ProductProfitabilityCalibrationMethod",
    "ProductProfitabilityCalibrationReadiness",
    "assess_product_profitability_calibration_readiness",
]
