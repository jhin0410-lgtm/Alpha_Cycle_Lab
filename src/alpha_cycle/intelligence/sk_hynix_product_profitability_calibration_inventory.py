"""Build SK hynix product-profitability calibration inventory from verified source artifacts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_product_profitability_support import (
    HistoricalProductProfitabilityConstraint,
)
from alpha_cycle.intelligence.sec_product_profitability_support_verifier import (
    load_sec_product_profitability_support_evidence,
)
from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProfitabilityCalibrationEvidenceInventory,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)


def _independent_period_ids(
    observations: tuple[HistoricalProductProfitabilityConstraint, ...],
) -> tuple[str, ...]:
    """Select a deterministic maximum set of non-overlapping accounting periods."""

    ordered = sorted(
        observations,
        key=lambda item: (item.period_end, item.period_start, item.period_id),
    )
    selected: list[HistoricalProductProfitabilityConstraint] = []
    last_end: date | None = None
    for item in ordered:
        if last_end is None or item.period_start > last_end:
            selected.append(item)
            last_end = item.period_end
    return tuple(item.period_id for item in selected)


def build_skhynix_product_profitability_calibration_inventory(
    *,
    evaluation_date: date,
    product_revenue_pointer: str | Path = DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER,
    profitability_support_pointer: str | Path,
) -> ProfitabilityCalibrationEvidenceInventory:
    """Replay current direct revenue and historical SEC support into one fail-closed inventory."""

    revenue = load_periodic_product_revenue_certification(
        product_revenue_pointer,
        evaluation_date=evaluation_date,
    )
    support = load_sec_product_profitability_support_evidence(
        profitability_support_pointer,
        evaluation_date=evaluation_date,
    )
    if revenue.ticker != "000660" or support.ticker != "000660":
        raise ValueError("SK hynix profitability calibration inventory received another ticker")
    if not revenue.product_revenue_baseline_eligible:
        raise ValueError("Current direct product revenue is not baseline eligible")
    if support.product_profitability_source_fact:
        raise ValueError("Historical profitability support cannot claim product-margin source facts")
    if support.direct_product_profitability_observations != 0:
        raise ValueError("Historical support cannot contain direct product-profitability observations")
    period_ids = _independent_period_ids(support.observations)
    if len(period_ids) != support.independent_non_overlapping_period_count:
        raise ValueError("Historical profitability support independent-period count does not reproduce")

    return ProfitabilityCalibrationEvidenceInventory(
        direct_product_revenue_evidence_id=revenue.evidence_id,
        direct_product_revenue_ready=True,
        direct_product_profitability_periods=(),
        historical_product_revenue_periods=period_ids,
        company_profitability_constraint_periods=period_ids,
        cycle_driver_history_periods=(),
        holdout_periods=(),
        verified_evidence_ids=(support.evidence_id,),
        source_evidence_verified=True,
    )


__all__ = [
    "_independent_period_ids",
    "build_skhynix_product_profitability_calibration_inventory",
]
