"""Retrospective holdout contract for SK hynix product-profitability calibration.

The 2026Q1 profitability observation is already historically known in the archived SEC
filing, so this cannot be represented as a genuinely never-seen label.  The useful and
honest contract is narrower: calibration code must receive a fit view that excludes the
2026Q1 company-profitability target, while validation code may receive it only after the
method specification and fitted parameters are frozen.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from alpha_cycle.intelligence.sec_product_profitability_support import (
    SecProductProfitabilitySupportEvidence,
)

_HOLDOUT_PERIOD_ID = "q1_2026"
_HOLDOUT_CYCLE_DRIVER_PERIOD_ID = "2026Q1"


def _sha_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class ProductProfitabilityRetrospectiveHoldoutPlan:
    evidence_id: str
    source_profitability_support_evidence_id: str
    calibration_period_ids: tuple[str, ...]
    holdout_period_ids: tuple[str, ...]
    holdout_cycle_driver_period_ids: tuple[str, ...]
    retrospective_holdout: bool = True
    fully_label_blind_historically: bool = False
    fit_view_excludes_holdout_profitability_labels: bool = True
    validation_view_requires_frozen_method: bool = True
    holdout_validation_complete: bool = False
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(
            self.source_profitability_support_evidence_id
        ):
            raise ValueError("Profitability holdout evidence IDs must be SHA-256")
        if self.holdout_period_ids != (_HOLDOUT_PERIOD_ID,):
            raise ValueError("Profitability holdout v1 must reserve q1_2026")
        if self.holdout_cycle_driver_period_ids != (_HOLDOUT_CYCLE_DRIVER_PERIOD_ID,):
            raise ValueError("Profitability holdout v1 must bind the 2026Q1 driver period")
        if set(self.calibration_period_ids) & set(self.holdout_period_ids):
            raise ValueError("Profitability calibration and holdout periods must be disjoint")
        if len(set(self.calibration_period_ids)) != len(self.calibration_period_ids):
            raise ValueError("Profitability holdout calibration periods must be unique")
        if (
            not self.retrospective_holdout
            or self.fully_label_blind_historically
            or not self.fit_view_excludes_holdout_profitability_labels
            or not self.validation_view_requires_frozen_method
            or self.holdout_validation_complete
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.fair_value_estimate_enabled
            or self.target_price_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Profitability holdout plan exceeds its pre-validation boundary")


def _independent_non_overlapping_periods(
    support: SecProductProfitabilitySupportEvidence,
) -> tuple[str, ...]:
    selected: list[str] = []
    last_end = None
    for item in sorted(
        support.observations,
        key=lambda value: (value.period_end, value.period_start, value.period_id),
    ):
        if last_end is None or item.period_start > last_end:
            selected.append(item.period_id)
            last_end = item.period_end
    return tuple(selected)


def build_skhynix_product_profitability_holdout_plan(
    support: SecProductProfitabilitySupportEvidence,
) -> ProductProfitabilityRetrospectiveHoldoutPlan:
    """Reserve Q1 2026 after reproducing the source's independent-period count."""

    if support.ticker != "000660":
        raise ValueError("SK hynix profitability holdout received another ticker")
    independent = _independent_non_overlapping_periods(support)
    if len(independent) != support.independent_non_overlapping_period_count:
        raise ValueError("SK hynix profitability support independent-period count does not reproduce")
    if _HOLDOUT_PERIOD_ID not in independent:
        raise ValueError("SK hynix profitability holdout period is unavailable")
    calibration_periods = tuple(
        period for period in independent if period != _HOLDOUT_PERIOD_ID
    )
    payload = {
        "source_profitability_support_evidence_id": support.evidence_id,
        "calibration_period_ids": calibration_periods,
        "holdout_period_ids": [_HOLDOUT_PERIOD_ID],
        "holdout_cycle_driver_period_ids": [_HOLDOUT_CYCLE_DRIVER_PERIOD_ID],
        "retrospective_holdout": True,
        "fully_label_blind_historically": False,
        "fit_view_excludes_holdout_profitability_labels": True,
        "validation_view_requires_frozen_method": True,
        "holdout_validation_complete": False,
    }
    return ProductProfitabilityRetrospectiveHoldoutPlan(
        evidence_id=_sha_payload(payload),
        source_profitability_support_evidence_id=support.evidence_id,
        calibration_period_ids=calibration_periods,
        holdout_period_ids=(_HOLDOUT_PERIOD_ID,),
        holdout_cycle_driver_period_ids=(_HOLDOUT_CYCLE_DRIVER_PERIOD_ID,),
    )


__all__ = [
    "ProductProfitabilityRetrospectiveHoldoutPlan",
    "build_skhynix_product_profitability_holdout_plan",
]
