"""Readiness contract for calibrated semiconductor product-profitability assumptions.

Product revenue and company-wide profitability may support a calibration exercise, but
they do not by themselves identify product margins. This module keeps evidence inventory,
method requirements, and calibration validation separate. It deliberately makes no numeric
margin estimate and cannot enable forecast, valuation, or decision scoring.
"""

from __future__ import annotations

from dataclasses import dataclass

_ALLOWED_STRATEGIES = frozenset({"direct_target_model", "aggregate_structural_model"})
_ALLOWED_STATUSES = frozenset(
    {
        "identification_method_not_selected",
        "calibration_method_not_documented",
        "calibration_evidence_incomplete",
        "calibration_evidence_unverified",
        "historical_validation_incomplete",
        "calibration_method_not_frozen",
        "observationally_calibrated",
    }
)
_ALLOWED_EVIDENCE_CATEGORIES = frozenset(
    {
        "direct_product_profitability",
        "historical_product_revenue",
        "company_profitability",
        "cycle_driver_history",
        "holdout_history",
    }
)


@dataclass(frozen=True)
class ProfitabilityCalibrationEvidenceInventory:
    ticker: str
    direct_product_profitability_periods: int
    historical_product_revenue_periods: int
    company_profitability_periods: int
    cycle_driver_periods: int
    holdout_periods: int
    supporting_evidence_ids: tuple[str, ...]
    supporting_evidence_verified: bool

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Profitability-calibration ticker must be six digits")
        counts = (
            self.direct_product_profitability_periods,
            self.historical_product_revenue_periods,
            self.company_profitability_periods,
            self.cycle_driver_periods,
            self.holdout_periods,
        )
        if any(item < 0 for item in counts):
            raise ValueError("Profitability-calibration evidence counts cannot be negative")
        if len(set(self.supporting_evidence_ids)) != len(self.supporting_evidence_ids):
            raise ValueError("Profitability-calibration evidence IDs must be unique")
        if any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
            for item in self.supporting_evidence_ids
        ):
            raise ValueError("Profitability-calibration evidence IDs must be SHA-256")
        if self.supporting_evidence_verified and not self.supporting_evidence_ids:
            raise ValueError("Verified profitability calibration requires evidence IDs")


@dataclass(frozen=True)
class ProductProfitabilityCalibrationMethod:
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
    method_version_frozen: bool

    def __post_init__(self) -> None:
        if not self.method_id.strip() or not self.method_version.strip():
            raise ValueError("Profitability-calibration method identity cannot be blank")
        if self.identification_strategy not in _ALLOWED_STRATEGIES:
            raise ValueError("Profitability-calibration identification strategy is invalid")
        if not self.target_metric.strip() or not self.target_product_blocks:
            raise ValueError("Profitability-calibration method requires targets")
        if len(set(self.target_product_blocks)) != len(self.target_product_blocks):
            raise ValueError("Profitability-calibration target blocks must be unique")
        minima = (
            self.minimum_direct_target_periods,
            self.minimum_product_revenue_periods,
            self.minimum_company_profitability_periods,
            self.minimum_cycle_driver_periods,
            self.minimum_holdout_periods,
        )
        if any(item < 0 for item in minima):
            raise ValueError("Profitability-calibration minimum evidence counts cannot be negative")
        if self.minimum_holdout_periods == 0 and self.historical_validation_complete:
            raise ValueError("Completed historical validation requires a holdout requirement")
        if self.method_version_frozen and not self.method_documented:
            raise ValueError("Frozen profitability-calibration method must be documented")


@dataclass(frozen=True)
class ProductProfitabilityCalibrationReadiness:
    ticker: str
    status: str
    missing_evidence_categories: tuple[str, ...]
    evidence_thresholds_met: bool
    identification_method_selected: bool
    method_documented: bool
    historical_validation_complete: bool
    method_version_frozen: bool
    supporting_evidence_verified: bool
    operating_assumption_model_use_ready: bool
    source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Profitability-calibration readiness ticker must be six digits")
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError("Profitability-calibration readiness status is invalid")
        if any(item not in _ALLOWED_EVIDENCE_CATEGORIES for item in self.missing_evidence_categories):
            raise ValueError("Profitability-calibration missing evidence category is invalid")
        if len(set(self.missing_evidence_categories)) != len(self.missing_evidence_categories):
            raise ValueError("Profitability-calibration missing evidence categories must be unique")
        ready = (
            self.status == "observationally_calibrated"
            and self.evidence_thresholds_met
            and self.identification_method_selected
            and self.method_documented
            and self.historical_validation_complete
            and self.method_version_frozen
            and self.supporting_evidence_verified
            and not self.missing_evidence_categories
        )
        if self.operating_assumption_model_use_ready != ready:
            raise ValueError("Profitability-calibration model-use readiness is inconsistent")
        if self.source_fact:
            raise ValueError("Calibrated product profitability cannot be labeled a source fact")
        if (
            self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Calibration readiness cannot enable downstream decision outputs")


def _missing_categories(
    inventory: ProfitabilityCalibrationEvidenceInventory,
    method: ProductProfitabilityCalibrationMethod,
) -> tuple[str, ...]:
    missing: list[str] = []
    requirements = (
        (
            "direct_product_profitability",
            inventory.direct_product_profitability_periods,
            method.minimum_direct_target_periods,
        ),
        (
            "historical_product_revenue",
            inventory.historical_product_revenue_periods,
            method.minimum_product_revenue_periods,
        ),
        (
            "company_profitability",
            inventory.company_profitability_periods,
            method.minimum_company_profitability_periods,
        ),
        (
            "cycle_driver_history",
            inventory.cycle_driver_periods,
            method.minimum_cycle_driver_periods,
        ),
        ("holdout_history", inventory.holdout_periods, method.minimum_holdout_periods),
    )
    for category, observed, required in requirements:
        if observed < required:
            missing.append(category)
    return tuple(missing)


def assess_product_profitability_calibration_readiness(
    inventory: ProfitabilityCalibrationEvidenceInventory,
    *,
    method: ProductProfitabilityCalibrationMethod | None,
) -> ProductProfitabilityCalibrationReadiness:
    """Assess whether a calibrated assumption method has crossed every trust gate."""

    if method is None:
        return ProductProfitabilityCalibrationReadiness(
            ticker=inventory.ticker,
            status="identification_method_not_selected",
            missing_evidence_categories=(),
            evidence_thresholds_met=False,
            identification_method_selected=False,
            method_documented=False,
            historical_validation_complete=False,
            method_version_frozen=False,
            supporting_evidence_verified=inventory.supporting_evidence_verified,
            operating_assumption_model_use_ready=False,
        )

    missing = _missing_categories(inventory, method)
    thresholds_met = not missing
    if not method.method_documented:
        status = "calibration_method_not_documented"
    elif missing:
        status = "calibration_evidence_incomplete"
    elif not inventory.supporting_evidence_verified:
        status = "calibration_evidence_unverified"
    elif not method.historical_validation_complete:
        status = "historical_validation_incomplete"
    elif not method.method_version_frozen:
        status = "calibration_method_not_frozen"
    else:
        status = "observationally_calibrated"
    ready = status == "observationally_calibrated"
    return ProductProfitabilityCalibrationReadiness(
        ticker=inventory.ticker,
        status=status,
        missing_evidence_categories=missing,
        evidence_thresholds_met=thresholds_met,
        identification_method_selected=True,
        method_documented=method.method_documented,
        historical_validation_complete=method.historical_validation_complete,
        method_version_frozen=method.method_version_frozen,
        supporting_evidence_verified=inventory.supporting_evidence_verified,
        operating_assumption_model_use_ready=ready,
    )


__all__ = [
    "ProductProfitabilityCalibrationMethod",
    "ProductProfitabilityCalibrationReadiness",
    "ProfitabilityCalibrationEvidenceInventory",
    "assess_product_profitability_calibration_readiness",
]
