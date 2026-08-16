"""Build SK hynix product-profitability calibration inventory from verified source artifacts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_product_cycle_driver_support_verifier import (
    load_sec_product_cycle_driver_support_evidence,
)
from alpha_cycle.intelligence.sec_product_profitability_support import (
    HistoricalProductProfitabilityConstraint,
)
from alpha_cycle.intelligence.sec_product_profitability_support_verifier import (
    load_sec_product_profitability_support_evidence,
)
from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProfitabilityCalibrationEvidenceInventory,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability_verifier import (
    load_quarterly_company_profitability_evidence,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_holdout import (
    build_skhynix_product_profitability_holdout_plan,
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
    cycle_driver_support_pointer: str | Path | None = None,
    quarterly_company_profitability_pointer: str | Path | None = None,
    historical_product_revenue_pointer: str | Path | None = None,
    reserve_q1_2026_holdout: bool = False,
) -> ProfitabilityCalibrationEvidenceInventory:
    """Replay verified evidence and optionally reserve Q1 2026 from the fit view."""

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
        raise ValueError(
            "Historical profitability support cannot claim product-margin source facts"
        )
    if support.direct_product_profitability_observations != 0:
        raise ValueError(
            "Historical support cannot contain direct product-profitability observations"
        )
    period_ids = _independent_period_ids(support.observations)
    if len(period_ids) != support.independent_non_overlapping_period_count:
        raise ValueError(
            "Historical profitability support independent-period count does not reproduce"
        )

    evidence_ids: list[str] = [support.evidence_id]
    cycle_period_ids: tuple[str, ...] = ()
    if cycle_driver_support_pointer is not None:
        cycle = load_sec_product_cycle_driver_support_evidence(
            cycle_driver_support_pointer,
            evaluation_date=evaluation_date,
        )
        if cycle.ticker != "000660":
            raise ValueError("SK hynix profitability cycle-driver evidence has another ticker")
        if cycle.source_profitability_support_evidence_id != support.evidence_id:
            raise ValueError(
                "SK hynix profitability cycle-driver evidence is not bound to support evidence"
            )
        if not cycle.textual_band_source_facts or cycle.numeric_driver_values_available:
            raise ValueError("SK hynix profitability cycle-driver trust boundary is invalid")
        cycle_period_ids = tuple(item.period_id for item in cycle.observations)
        evidence_ids.append(cycle.evidence_id)

    holdout_periods: tuple[str, ...] = ()
    calibration_period_ids = period_ids
    if reserve_q1_2026_holdout:
        holdout = build_skhynix_product_profitability_holdout_plan(support)
        calibration_period_ids = holdout.calibration_period_ids
        holdout_periods = holdout.holdout_period_ids
        if cycle_driver_support_pointer is not None and not set(
            holdout.holdout_cycle_driver_period_ids
        ).issubset(cycle_period_ids):
            raise ValueError("SK hynix holdout cycle-driver period is not available")

    company_period_ids: tuple[str, ...] = calibration_period_ids
    if quarterly_company_profitability_pointer is not None:
        quarterly = load_quarterly_company_profitability_evidence(
            quarterly_company_profitability_pointer,
            evaluation_date=evaluation_date,
        )
        if quarterly.ticker != "000660":
            raise ValueError("SK hynix quarterly company profitability has another ticker")
        if (
            not quarterly.calibration_support_only
            or quarterly.product_profitability_source_fact
            or quarterly.point_in_time_backtest_eligible
        ):
            raise ValueError("SK hynix quarterly company profitability trust boundary is invalid")
        quarterly_periods = tuple(item.period_id for item in quarterly.observations)
        if reserve_q1_2026_holdout:
            quarterly_periods = tuple(
                period for period in quarterly_periods if period != "2026Q1"
            )
            if "2026Q1" in quarterly_periods:
                raise ValueError("SK hynix Q1 2026 quarterly profitability leaked into fit view")
        company_period_ids = tuple(
            dict.fromkeys((*calibration_period_ids, *quarterly_periods))
        )
        evidence_ids.append(quarterly.evidence_id)

    product_period_ids: tuple[str, ...] = calibration_period_ids
    if historical_product_revenue_pointer is not None:
        historical = load_historical_product_revenue_panel_evidence(
            historical_product_revenue_pointer,
            evaluation_date=evaluation_date,
        )
        if historical.ticker != "000660":
            raise ValueError("SK hynix historical product revenue has another ticker")
        if not historical.calibration_support_only or historical.product_profitability_source_fact:
            raise ValueError("SK hynix historical product revenue trust boundary is invalid")
        historical_periods = historical.successful_periods
        if reserve_q1_2026_holdout:
            historical_periods = tuple(
                period for period in historical_periods if period != "2026Q1"
            )
            if "2026Q1" in historical_periods:
                raise ValueError("SK hynix Q1 2026 historical product revenue leaked into fit view")
        product_period_ids = tuple(
            dict.fromkeys((*calibration_period_ids, *historical_periods))
        )
        evidence_ids.append(historical.evidence_id)

    return ProfitabilityCalibrationEvidenceInventory(
        direct_product_revenue_evidence_id=revenue.evidence_id,
        direct_product_revenue_ready=True,
        direct_product_profitability_periods=(),
        historical_product_revenue_periods=product_period_ids,
        company_profitability_constraint_periods=company_period_ids,
        cycle_driver_history_periods=cycle_period_ids,
        holdout_periods=holdout_periods,
        verified_evidence_ids=tuple(evidence_ids),
        source_evidence_verified=True,
    )


__all__ = [
    "_independent_period_ids",
    "build_skhynix_product_profitability_calibration_inventory",
]
