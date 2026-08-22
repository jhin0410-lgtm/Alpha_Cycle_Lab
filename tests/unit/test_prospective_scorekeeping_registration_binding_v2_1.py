from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.intelligence.expectation_gap_opportunity_set_v2_1 import (
    EXPECTATION_AUGMENTED_PARETO_DIMENSIONS,
    ExpectationAugmentedOpportunitySetSnapshot,
    ExpectationGapOpportunityCandidateSnapshot,
)
from alpha_cycle.intelligence.expectation_state import ExpectationMetric
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    PARETO_DIMENSIONS,
    DominanceRelation,
    OpportunityCandidateSnapshot,
    OpportunityResearchClass,
    OpportunitySetSnapshot,
)
from alpha_cycle.intelligence.prospective_scorekeeping_registration_binding_v2_1 import (
    register_prospective_opportunity_set,
)

SEOUL = ZoneInfo("Asia/Seoul")
EVALUATION_DATE = date(2026, 8, 22)
GUARDRAIL = "d" * 64
SOURCE = "a" * 64
POLICY = "c" * 64


class WeekdayCalendar:
    timezone = SEOUL

    def is_session(self, value: date) -> bool:
        return value.weekday() < 5

    def next_session(self, value: date) -> date:
        current = value + timedelta(days=1)
        while not self.is_session(current):
            current += timedelta(days=1)
        return current

    def previous_session(self, value: date) -> date:
        current = value - timedelta(days=1)
        while not self.is_session(current):
            current -= timedelta(days=1)
        return current

    def sessions_between(
        self,
        start: date,
        end: date,
        *,
        inclusive: bool = True,
    ) -> list[date]:
        sessions: list[date] = []
        current = start
        while current <= end:
            if self.is_session(current):
                sessions.append(current)
            current += timedelta(days=1)
        if inclusive:
            return sessions
        return [item for item in sessions if start < item < end]

    def session_open(self, value: date) -> datetime:
        return datetime.combine(value, time(9, 0), tzinfo=self.timezone)

    def session_close(self, value: date) -> datetime:
        return datetime.combine(value, time(15, 30), tzinfo=self.timezone)

    def session_label(self, timestamp: datetime) -> date:
        return timestamp.astimezone(self.timezone).date()


def _candidate(
    security_id: str,
    *,
    comparable: bool,
    suffix: str,
) -> OpportunityCandidateSnapshot:
    research_class = (
        OpportunityResearchClass.DEEP_READY
        if comparable
        else OpportunityResearchClass.FAST_READY
    )
    blockers = () if comparable else ("underwriter_not_deep_ready",)
    return OpportunityCandidateSnapshot(
        captured_at=datetime(2026, 8, 22, 17, 30, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        security_id=security_id,
        thesis_snapshot_id=suffix * 64,
        underwriting_readiness_snapshot_id="b" * 64,
        payoff_surface_snapshot_id="e" * 64,
        horizon_trading_days=120,
        research_class=research_class,
        bear_return_lower=-0.10,
        base_return_lower=0.10,
        base_return_upper=0.20,
        bull_return_upper=0.40,
        nearest_catalyst_id=f"{security_id}-catalyst",
        nearest_catalyst_days=20,
        nearest_catalyst_evidence_refs=(f"evidence:{security_id}:catalyst",),
        comparison_blockers=blockers,
        flags=(),
        guardrail_evidence_id=GUARDRAIL,
    )


def _base() -> OpportunitySetSnapshot:
    candidate_a = _candidate("A", comparable=True, suffix="1")
    candidate_b = _candidate("B", comparable=True, suffix="2")
    candidate_c = _candidate("C", comparable=False, suffix="3")
    return OpportunitySetSnapshot(
        captured_at=datetime(2026, 8, 22, 18, 0, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        candidates=(candidate_a, candidate_b, candidate_c),
        pareto_dimensions=PARETO_DIMENSIONS,
        dominance_relations=(
            DominanceRelation(
                dominator_security_id="A",
                dominated_security_id="B",
                strictly_better_dimensions=("base_return_upper",),
            ),
        ),
        pareto_frontier_security_ids=("A",),
        comparable_security_ids=("A", "B"),
        fast_lane_research_security_ids=("C",),
        blocked_security_ids=(),
        epistemically_flagged_security_ids=(),
        unique_pareto_leader_security_id="A",
        flags=(),
        guardrail_evidence_id=GUARDRAIL,
    )


def _base_candidate(base: OpportunitySetSnapshot, security_id: str) -> OpportunityCandidateSnapshot:
    return next(item for item in base.candidates if item.security_id == security_id)


def _gap_candidate(
    base: OpportunitySetSnapshot,
    security_id: str,
    *,
    relative_gap: float | None,
    suffix: str,
    blockers: tuple[str, ...] = (),
) -> ExpectationGapOpportunityCandidateSnapshot:
    original = _base_candidate(base, security_id)
    return ExpectationGapOpportunityCandidateSnapshot(
        captured_at=datetime(2026, 8, 22, 18, 5, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        security_id=security_id,
        opportunity_candidate_snapshot_id=original.snapshot_id,
        decision_expectation_gap_snapshot_id=suffix * 64,
        comparison_policy_snapshot_id=POLICY,
        consensus_provider_id="provider-x",
        metric=ExpectationMetric.OPERATING_INCOME,
        target_date=date(2026, 12, 31),
        consensus_relative_gap=relative_gap,
        comparison_blockers=blockers,
        flags=(),
        guardrail_evidence_id=GUARDRAIL,
    )


def _overlay(base: OpportunitySetSnapshot) -> ExpectationAugmentedOpportunitySetSnapshot:
    candidate_a = _gap_candidate(base, "A", relative_gap=0.05, suffix="4")
    candidate_b = _gap_candidate(base, "B", relative_gap=0.20, suffix="5")
    return ExpectationAugmentedOpportunitySetSnapshot(
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        base_opportunity_set_snapshot_id=base.snapshot_id,
        comparison_policy_snapshot_id=POLICY,
        candidates=(candidate_a, candidate_b),
        pareto_dimensions=EXPECTATION_AUGMENTED_PARETO_DIMENSIONS,
        dominance_relations=(),
        base_pareto_frontier_security_ids=("A",),
        expectation_pareto_frontier_security_ids=("B",),
        expectation_comparable_security_ids=("A", "B"),
        expectation_blocked_security_ids=(),
        unique_expectation_pareto_leader_security_id="B",
        flags=("expectation_gap_changes_pareto_frontier",),
        guardrail_evidence_id=GUARDRAIL,
    )


def _register(
    base: OpportunitySetSnapshot,
    *,
    overlay: ExpectationAugmentedOpportunitySetSnapshot | None,
):
    return register_prospective_opportunity_set(
        base,
        registration_id="typed-binding-2026-08-22-120d",
        registered_at=datetime(2026, 8, 22, 18, 20, tzinfo=SEOUL),
        benchmark_security_id="BM",
        price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        source_evidence_ids=(SOURCE,),
        calendar=WeekdayCalendar(),
        expectation_overlay=overlay,
    )


def test_binding_extracts_only_base_comparable_candidates_and_both_frontiers() -> None:
    base = _base()
    overlay = _overlay(base)

    registration = _register(base, overlay=overlay)

    assert registration.security_ids == ("A", "B")
    assert "C" not in registration.security_ids
    assert registration.opportunity_set_snapshot_id == base.snapshot_id
    assert registration.expectation_overlay_snapshot_id == overlay.snapshot_id
    assert registration.base_pareto_frontier_security_ids == ("A",)
    assert registration.unique_base_leader_security_id == "A"
    assert registration.expectation_pareto_frontier_security_ids == ("B",)
    assert registration.unique_expectation_leader_security_id == "B"
    assert registration.horizon_trading_days == 120
    assert registration.entry_session == date(2026, 8, 24)
    assert registration.guardrail_evidence_id == GUARDRAIL


def test_binding_without_overlay_preserves_base_only_experiment() -> None:
    base = _base()

    registration = _register(base, overlay=None)

    assert registration.security_ids == ("A", "B")
    assert registration.expectation_overlay_snapshot_id is None
    assert registration.expectation_pareto_frontier_security_ids == ()
    assert registration.unique_expectation_leader_security_id is None


def test_binding_rejects_overlay_from_a_different_base_snapshot() -> None:
    base = _base()
    overlay = replace(_overlay(base), base_opportunity_set_snapshot_id="f" * 64)

    with pytest.raises(ValueError, match="different base opportunity set"):
        _register(base, overlay=overlay)


def test_binding_rejects_overlay_candidate_policy_drift() -> None:
    base = _base()
    overlay = _overlay(base)
    candidate_a = replace(overlay.candidates[0], comparison_policy_snapshot_id="f" * 64)
    tampered = replace(overlay, candidates=(candidate_a, overlay.candidates[1]))

    with pytest.raises(ValueError, match="candidate comparison policy mismatch"):
        _register(base, overlay=tampered)


def test_binding_rejects_overlay_candidate_bound_to_wrong_base_candidate() -> None:
    base = _base()
    overlay = _overlay(base)
    candidate_a = replace(
        overlay.candidates[0],
        opportunity_candidate_snapshot_id="f" * 64,
    )
    tampered = replace(overlay, candidates=(candidate_a, overlay.candidates[1]))

    with pytest.raises(ValueError, match="different base candidate"):
        _register(base, overlay=tampered)


def test_binding_rejects_overlay_captured_before_base_snapshot() -> None:
    base = replace(
        _base(),
        captured_at=datetime(2026, 8, 22, 18, 8, tzinfo=SEOUL),
    )
    overlay = replace(
        _overlay(base),
        captured_at=datetime(2026, 8, 22, 18, 7, tzinfo=SEOUL),
    )

    with pytest.raises(ValueError, match="cannot precede base opportunity-set capture"):
        _register(base, overlay=overlay)


def test_binding_rejects_snapshot_captured_after_registration() -> None:
    base = replace(
        _base(),
        captured_at=datetime(2026, 8, 22, 18, 30, tzinfo=SEOUL),
    )

    with pytest.raises(ValueError, match="cannot precede opportunity-set capture"):
        _register(base, overlay=None)


def test_binding_rejects_base_comparable_registry_drift() -> None:
    base = replace(
        _base(),
        comparable_security_ids=("A",),
        pareto_frontier_security_ids=("A",),
        dominance_relations=(),
        unique_pareto_leader_security_id=None,
    )

    with pytest.raises(ValueError, match="comparable-security registry has drifted"):
        _register(base, overlay=None)


def test_binding_rejects_insufficient_base_comparable_candidates() -> None:
    original = _base()
    candidate_b = replace(
        original.candidates[1],
        research_class=OpportunityResearchClass.FAST_READY,
        comparison_blockers=("underwriter_not_deep_ready",),
    )
    base = replace(
        original,
        candidates=(original.candidates[0], candidate_b, original.candidates[2]),
        comparable_security_ids=("A",),
        pareto_frontier_security_ids=("A",),
        fast_lane_research_security_ids=("B", "C"),
        dominance_relations=(),
        unique_pareto_leader_security_id=None,
    )

    with pytest.raises(ValueError, match="at least two base-comparable"):
        _register(base, overlay=None)


def test_binding_rejects_expectation_comparable_registry_drift() -> None:
    base = _base()
    original = _overlay(base)
    blocked_b = replace(
        original.candidates[1],
        consensus_relative_gap=None,
        comparison_blockers=("consensus_relative_gap_unavailable",),
    )
    overlay = replace(
        original,
        candidates=(original.candidates[0], blocked_b),
    )

    with pytest.raises(ValueError, match="comparable-security registry has drifted"):
        _register(base, overlay=overlay)


def test_binding_rejects_overlay_without_two_expectation_comparable_candidates() -> None:
    base = _base()
    original = _overlay(base)
    blocked_b = replace(
        original.candidates[1],
        consensus_relative_gap=None,
        comparison_blockers=("consensus_relative_gap_unavailable",),
    )
    overlay = replace(
        original,
        candidates=(original.candidates[0], blocked_b),
        expectation_comparable_security_ids=("A",),
        expectation_blocked_security_ids=("B",),
        expectation_pareto_frontier_security_ids=("A",),
        unique_expectation_pareto_leader_security_id=None,
    )

    with pytest.raises(ValueError, match="at least two expectation-comparable"):
        _register(base, overlay=overlay)
