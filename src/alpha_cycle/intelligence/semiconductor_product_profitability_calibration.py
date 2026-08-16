"""Evidence-bound calibration gate for latent semiconductor product profitability.

Direct product revenue can be a certified source fact even when product-level gross
profit or gross margin is not directly disclosed. This module keeps those concepts
separate. It never turns an allocation heuristic into a source fact and it cannot by
itself enable a numeric forecast, valuation, target price, or decision score.
"""

from __future__ import annotations

from dataclasses import dataclass

_ALLOWED_METHOD_STATUSES = frozenset(
    {"draft", "documented", "observationally_calibrated"}
)


@dataclass(frozen=True)
class ProductProfitabilityCalibrationEvidence:
    """Verified observations available to calibrate latent product profitability."""

    direct_product_revenue_evidence_id: str
    direct_product_revenue_ready: bool
    historical_periods: tuple[str, ...]
    holdout_periods: tuple[str, ...]
    company_profitability_evidence_ids: tuple[str, ...]
    cycle_driver_evidence_ids: tuple[str, ...]
    source_evidence_verified: bool

    def __post_init__(self) -> None:
        if self.direct_product_revenue_ready and not self.direct_product_revenue_evidence_id:
            raise ValueError("Direct product revenue readiness requires an evidence id")
        if len(set(self.historical_periods)) != len(self.historical_periods):
            raise ValueError("Historical calibration periods must be unique")
        if len(set(self.holdout_periods)) != len(self.holdout_periods):
            raise ValueError("Holdout periods must be unique")
        if set(self.historical_periods) & set(self.holdout_periods):
            raise ValueError("Calibration and holdout periods must be disjoint")

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        values = (
            self.direct_product_revenue_evidence_id,
            *self.company_profitability_evidence_ids,
            *self.cycle_driver_evidence_ids,
        )
        return tuple(dict.fromkeys(item for item in values if item))


@dataclass(frozen=True)
class ProductProfitabilityCalibrationMethod:
    """Method contract for estimating latent DRAM/NAND profitability."""

    method_id: str
    method_version: str
    status: str
    method_version_frozen: bool
    supporting_evidence_ids: tuple[str, ...]
    holdout_validated: bool
    uses_revenue_share_gross_profit_allocation: bool = False
    uses_residual_profit_allocation: bool = False
    uses_peer_margin_as_source_fact: bool = False

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_METHOD_STATUSES:
            raise ValueError(f"Unsupported profitability calibration method status: {self.status}")
        if not self.method_id or not self.method_version:
            raise ValueError("Profitability calibration method id/version must be explicit")

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
    """Fail-closed readiness result for model use of calibrated product profitability."""

    calibration_required: bool
    direct_product_profitability_source_fact: bool
    direct_product_revenue_ready: bool
    source_evidence_verified: bool
    historical_calibration_evidence_available: bool
    company_profitability_evidence_available: bool
    cycle_driver_evidence_available: bool
    holdout_evidence_available: bool
    method_registered: bool
    method_status: str
    method_version_frozen: bool
    method_evidence_bound: bool
    holdout_validated: bool
    prohibited_shortcut_used: bool
    model_input_ready: bool
    missing_requirements: tuple[str, ...]
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False


def assess_product_profitability_calibration_readiness(
    evidence: ProductProfitabilityCalibrationEvidence,
    method: ProductProfitabilityCalibrationMethod | None = None,
) -> ProductProfitabilityCalibrationReadiness:
    """Assess whether a calibrated profitability assumption is fit for model input.

    The function deliberately does not estimate a margin. It only evaluates whether
    the evidence and frozen methodology are sufficient to permit a separately produced
    calibrated assumption to enter an operating model.
    """

    historical_available = bool(evidence.historical_periods)
    company_profitability_available = bool(evidence.company_profitability_evidence_ids)
    cycle_driver_available = bool(evidence.cycle_driver_evidence_ids)
    holdout_available = bool(evidence.holdout_periods)
    method_registered = method is not None
    method_status = method.status if method is not None else "unregistered"
    method_frozen = method.method_version_frozen if method is not None else False
    holdout_validated = method.holdout_validated if method is not None else False
    prohibited_shortcut = method.prohibited_shortcut_used if method is not None else False

    required_evidence_ids = set(evidence.evidence_ids)
    bound_evidence_ids = set(method.supporting_evidence_ids) if method is not None else set()
    method_evidence_bound = bool(required_evidence_ids) and required_evidence_ids.issubset(
        bound_evidence_ids
    )

    missing: list[str] = []
    if not evidence.direct_product_revenue_ready:
        missing.append("direct_product_revenue")
    if not evidence.source_evidence_verified:
        missing.append("verified_source_evidence")
    if not historical_available:
        missing.append("historical_calibration_periods")
    if not company_profitability_available:
        missing.append("company_profitability_evidence")
    if not cycle_driver_available:
        missing.append("cycle_driver_evidence")
    if not holdout_available:
        missing.append("holdout_periods")
    if method is None:
        missing.append("calibration_method")
    else:
        if method.status != "observationally_calibrated":
            missing.append("observational_calibration")
        if not method.method_version_frozen:
            missing.append("frozen_method_version")
        if not method_evidence_bound:
            missing.append("method_evidence_binding")
        if not method.holdout_validated:
            missing.append("holdout_validation")
        if prohibited_shortcut:
            missing.append("prohibited_allocation_shortcut")

    ready = not missing
    return ProductProfitabilityCalibrationReadiness(
        calibration_required=True,
        direct_product_profitability_source_fact=False,
        direct_product_revenue_ready=evidence.direct_product_revenue_ready,
        source_evidence_verified=evidence.source_evidence_verified,
        historical_calibration_evidence_available=historical_available,
        company_profitability_evidence_available=company_profitability_available,
        cycle_driver_evidence_available=cycle_driver_available,
        holdout_evidence_available=holdout_available,
        method_registered=method_registered,
        method_status=method_status,
        method_version_frozen=method_frozen,
        method_evidence_bound=method_evidence_bound,
        holdout_validated=holdout_validated,
        prohibited_shortcut_used=prohibited_shortcut,
        model_input_ready=ready,
        missing_requirements=tuple(missing),
    )


__all__ = [
    "ProductProfitabilityCalibrationEvidence",
    "ProductProfitabilityCalibrationMethod",
    "ProductProfitabilityCalibrationReadiness",
    "assess_product_profitability_calibration_readiness",
]
