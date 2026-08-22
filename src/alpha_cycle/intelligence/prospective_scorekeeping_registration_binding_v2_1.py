"""Typed binding from Decision System opportunity snapshots to prospective scorekeeping.

The binding removes manual copying of candidate/frontier/leader identifiers into a prospective
registration. Only securities that were actually capital-allocation comparable in the frozen
base opportunity set enter the scored candidate universe.
"""

from __future__ import annotations

from datetime import datetime

from alpha_cycle.calendar.base import TradingCalendar
from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.intelligence.expectation_gap_opportunity_set_v2_1 import (
    ExpectationAugmentedOpportunitySetSnapshot,
)
from alpha_cycle.intelligence.opportunity_set_v2_1 import OpportunitySetSnapshot
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    ProspectiveOpportunityRegistration,
    ScorekeepingEntryRule,
    derive_entry_session,
)


def register_prospective_opportunity_set(
    opportunity_set: OpportunitySetSnapshot,
    *,
    registration_id: str,
    registered_at: datetime,
    benchmark_security_id: str,
    price_basis: PriceBasis,
    source_evidence_ids: tuple[str, ...],
    calendar: TradingCalendar,
    expectation_overlay: ExpectationAugmentedOpportunitySetSnapshot | None = None,
) -> ProspectiveOpportunityRegistration:
    """Freeze one typed opportunity set without permitting manual frontier substitution."""

    _require_aware(registered_at)
    if opportunity_set.captured_at > registered_at:
        raise ValueError("scorekeeping registration cannot precede opportunity-set capture")
    registration_date = registered_at.astimezone(calendar.timezone).date()
    if opportunity_set.evaluation_date > registration_date:
        raise ValueError("opportunity-set evaluation_date cannot follow registration date")

    comparable = tuple(sorted(opportunity_set.comparable_security_ids))
    if len(comparable) < 2:
        raise ValueError(
            "prospective cross-sectional scorekeeping requires at least two "
            "base-comparable securities"
        )
    base_frontier = tuple(sorted(opportunity_set.pareto_frontier_security_ids))
    if not base_frontier:
        raise ValueError("base opportunity set must contain a non-empty Pareto frontier")
    if not set(base_frontier).issubset(comparable):
        raise ValueError("base Pareto frontier is not contained in comparable securities")

    overlay_snapshot_id: str | None = None
    expectation_frontier: tuple[str, ...] = ()
    expectation_leader: str | None = None
    if expectation_overlay is not None:
        _validate_overlay(
            opportunity_set,
            expectation_overlay,
            registered_at=registered_at,
            comparable_security_ids=comparable,
        )
        overlay_snapshot_id = expectation_overlay.snapshot_id
        expectation_frontier = tuple(
            sorted(expectation_overlay.expectation_pareto_frontier_security_ids)
        )
        expectation_leader = (
            expectation_overlay.unique_expectation_pareto_leader_security_id
        )

    return ProspectiveOpportunityRegistration(
        registration_id=registration_id,
        registered_at=registered_at,
        evaluation_date=opportunity_set.evaluation_date,
        entry_session=derive_entry_session(registered_at, calendar=calendar),
        entry_rule=ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE,
        horizon_trading_days=opportunity_set.horizon_trading_days,
        opportunity_set_snapshot_id=opportunity_set.snapshot_id,
        expectation_overlay_snapshot_id=overlay_snapshot_id,
        security_ids=comparable,
        base_pareto_frontier_security_ids=base_frontier,
        expectation_pareto_frontier_security_ids=expectation_frontier,
        unique_base_leader_security_id=opportunity_set.unique_pareto_leader_security_id,
        unique_expectation_leader_security_id=expectation_leader,
        benchmark_security_id=benchmark_security_id,
        price_basis=price_basis,
        source_evidence_ids=source_evidence_ids,
        guardrail_evidence_id=opportunity_set.guardrail_evidence_id,
    )


def _validate_overlay(
    base: OpportunitySetSnapshot,
    overlay: ExpectationAugmentedOpportunitySetSnapshot,
    *,
    registered_at: datetime,
    comparable_security_ids: tuple[str, ...],
) -> None:
    if overlay.captured_at > registered_at:
        raise ValueError("scorekeeping registration cannot precede expectation-overlay capture")
    if overlay.base_opportunity_set_snapshot_id != base.snapshot_id:
        raise ValueError("expectation overlay is bound to a different base opportunity set")
    if overlay.evaluation_date != base.evaluation_date:
        raise ValueError("expectation overlay evaluation_date differs from base opportunity set")
    if overlay.horizon_trading_days != base.horizon_trading_days:
        raise ValueError("expectation overlay horizon differs from base opportunity set")
    if overlay.guardrail_evidence_id != base.guardrail_evidence_id:
        raise ValueError("expectation overlay guardrail evidence differs from base opportunity set")

    overlay_candidate_ids = tuple(sorted(item.security_id for item in overlay.candidates))
    if overlay_candidate_ids != comparable_security_ids:
        raise ValueError(
            "expectation overlay must represent every and only base-comparable security"
        )
    for candidate in overlay.candidates:
        if candidate.comparison_policy_snapshot_id != overlay.comparison_policy_snapshot_id:
            raise ValueError("expectation overlay candidate comparison policy mismatch")
        base_matches = tuple(
            item for item in base.candidates if item.security_id == candidate.security_id
        )
        if len(base_matches) != 1:
            raise ValueError("base opportunity set must contain exactly one overlay security")
        if candidate.opportunity_candidate_snapshot_id != base_matches[0].snapshot_id:
            raise ValueError("expectation overlay candidate is bound to a different base candidate")

    derived_comparable = tuple(
        sorted(item.security_id for item in overlay.candidates if item.expectation_gap_comparable)
    )
    derived_blocked = tuple(
        sorted(
            item.security_id
            for item in overlay.candidates
            if not item.expectation_gap_comparable
        )
    )
    if tuple(sorted(overlay.expectation_comparable_security_ids)) != derived_comparable:
        raise ValueError("expectation overlay comparable-security registry has drifted")
    if tuple(sorted(overlay.expectation_blocked_security_ids)) != derived_blocked:
        raise ValueError("expectation overlay blocked-security registry has drifted")
    if set(overlay.base_pareto_frontier_security_ids) != set(
        base.pareto_frontier_security_ids
    ):
        raise ValueError("expectation overlay base Pareto frontier differs from base snapshot")
    if len(overlay.expectation_comparable_security_ids) < 2:
        raise ValueError(
            "expectation overlay requires at least two expectation-comparable securities "
            "for prospective cross-sectional scorekeeping"
        )
    if not overlay.expectation_pareto_frontier_security_ids:
        raise ValueError("expectation overlay requires a non-empty expectation Pareto frontier")
    if not set(overlay.expectation_pareto_frontier_security_ids).issubset(
        comparable_security_ids
    ):
        raise ValueError(
            "expectation Pareto frontier is not contained in the registered candidate universe"
        )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("registered_at must be timezone-aware")
