"""Identify whether product profitability is a direct source fact or needs calibration.

Direct product revenue does not identify product gross profit or margin. For an
additive product block, revenue is one observed scalar while profitability is a
separate economic dimension. Company-level profit adds an aggregate constraint,
but it cannot uniquely solve multiple product margins without additional assumptions.

This module is deliberately non-estimating. It records the evidence gap and rejects
convenient revenue-share, residual, and peer-margin substitutions as source facts.
"""

from __future__ import annotations

from dataclasses import dataclass


_ALLOWED_STATUS = {
    "direct_product_profitability_source_facts_complete",
    "direct_product_profitability_source_facts_missing",
}


@dataclass(frozen=True)
class ProductProfitabilityIdentifiability:
    ticker: str
    required_product_blocks: tuple[str, ...]
    directly_disclosed_product_profitability_blocks: tuple[str, ...]
    direct_product_profitability_metrics_required: int
    direct_product_profitability_metrics_available: int
    identifiable_from_source_facts: bool
    calibrated_assumption_required: bool
    calibration_status: str
    revenue_share_profit_allocation_source_fact_allowed: bool = False
    residual_profit_allocation_source_fact_allowed: bool = False
    peer_margin_substitution_source_fact_allowed: bool = False
    product_profitability_certified: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Product-profitability ticker must be six digits")
        if not self.required_product_blocks:
            raise ValueError("Product-profitability assessment requires product blocks")
        if len(set(self.required_product_blocks)) != len(self.required_product_blocks):
            raise ValueError("Product-profitability required blocks must be unique")
        if len(set(self.directly_disclosed_product_profitability_blocks)) != len(
            self.directly_disclosed_product_profitability_blocks
        ):
            raise ValueError("Disclosed product-profitability blocks must be unique")
        if any(
            item not in self.required_product_blocks
            for item in self.directly_disclosed_product_profitability_blocks
        ):
            raise ValueError("Disclosed product-profitability block is outside the contract")
        if self.direct_product_profitability_metrics_required != len(
            self.required_product_blocks
        ):
            raise ValueError("Product-profitability required metric count is inconsistent")
        if self.direct_product_profitability_metrics_available != len(
            self.directly_disclosed_product_profitability_blocks
        ):
            raise ValueError("Product-profitability available metric count is inconsistent")
        if self.calibration_status not in _ALLOWED_STATUS:
            raise ValueError("Product-profitability calibration status is invalid")

        complete = set(self.directly_disclosed_product_profitability_blocks) == set(
            self.required_product_blocks
        )
        if self.identifiable_from_source_facts != complete:
            raise ValueError("Product-profitability identifiability is inconsistent")
        if self.calibrated_assumption_required == complete:
            raise ValueError("Product-profitability calibration requirement is inconsistent")
        expected_status = (
            "direct_product_profitability_source_facts_complete"
            if complete
            else "direct_product_profitability_source_facts_missing"
        )
        if self.calibration_status != expected_status:
            raise ValueError("Product-profitability status does not match source coverage")
        if (
            self.revenue_share_profit_allocation_source_fact_allowed
            or self.residual_profit_allocation_source_fact_allowed
            or self.peer_margin_substitution_source_fact_allowed
        ):
            raise ValueError("Derived product profitability cannot be promoted to source fact")
        if self.product_profitability_certified != complete:
            raise ValueError("Product-profitability certification must follow direct coverage")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Identifiability assessment cannot enable forecast or score")


def assess_product_profitability_identifiability(
    ticker: str,
    *,
    required_product_blocks: tuple[str, ...],
    directly_disclosed_product_profitability_blocks: tuple[str, ...] = (),
) -> ProductProfitabilityIdentifiability:
    """Assess direct product-profitability coverage without manufacturing estimates."""

    ticker_key = str(ticker).zfill(6)
    required = tuple(str(item).strip() for item in required_product_blocks if str(item).strip())
    disclosed = tuple(
        str(item).strip()
        for item in directly_disclosed_product_profitability_blocks
        if str(item).strip()
    )
    complete = set(disclosed) == set(required) and bool(required)
    return ProductProfitabilityIdentifiability(
        ticker=ticker_key,
        required_product_blocks=required,
        directly_disclosed_product_profitability_blocks=disclosed,
        direct_product_profitability_metrics_required=len(required),
        direct_product_profitability_metrics_available=len(disclosed),
        identifiable_from_source_facts=complete,
        calibrated_assumption_required=not complete,
        calibration_status=(
            "direct_product_profitability_source_facts_complete"
            if complete
            else "direct_product_profitability_source_facts_missing"
        ),
        product_profitability_certified=complete,
    )


__all__ = [
    "ProductProfitabilityIdentifiability",
    "assess_product_profitability_identifiability",
]
