from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
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
from alpha_cycle.intelligence.prospective_decision_ledger_v2_1 import (
    ObservedDecisionAttribution,
    build_prospective_decision_ledger,
    build_prospective_decision_ledger_entry,
    persist_prospective_decision_ledger,
)
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    CandidateRealizedOutcome,
    ProspectiveOpportunityOutcomeSnapshot,
    ProspectiveOpportunityRegistration,
    ScorekeepingEntryRule,
)

SEOUL = ZoneInfo("Asia/Seoul")
EVALUATION_DATE = date(2026, 8, 21)
ENTRY_SESSION = date(2026, 8, 24)
TARGET_SESSION = date(2026, 11, 16)
GUARDRAIL = "d" * 64
SOURCE = "a" * 64
POLICY = "c" * 64


def _candidate(
    security_id: str,
    *,
    suffix: str,
    bear: float,
    base_lower: float,
    base_upper: float,
    bull: float,
    catalyst_days: int,
) -> OpportunityCandidateSnapshot:
    return OpportunityCandidateSnapshot(
        captured_at=datetime(2026, 8, 21, 16, 30, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        security_id=security_id,
        thesis_snapshot_id=suffix * 64,
        underwriting_readiness_snapshot_id=(suffix.upper().lower()) * 64,
        payoff_surface_snapshot_id=("e" if suffix != "e" else "f") * 64,
        horizon_trading_days=60,
        research_class=OpportunityResearchClass.DEEP_READY,
        bear_return_lower=bear,
        base_return_lower=base_lower,
        base_return_upper=base_upper,
        bull_return_upper=bull,
        nearest_catalyst_id=f"{security_id}-catalyst",
        nearest_catalyst_days=catalyst_days,
        nearest_catalyst_evidence_refs=(f"evidence:{security_id}:catalyst",),
        comparison_blockers=(),
        flags=(),
        guardrail_evidence_id=GUARDRAIL,
    )


def _base() -> OpportunitySetSnapshot:
    candidate_a = _candidate(
        "A",
        suffix="1",
        bear=-0.20,
        base_lower=0.02,
        base_upper=0.10,
        bull=0.25,
        catalyst_days=25,
    )
    candidate_b = _candidate(
        "B",
        suffix="2",
        bear=-0.10,
        base_lower=0.08,
        base_upper=0.18,
        bull=0.35,
        catalyst_days=15,
    )
    candidate_c = _candidate(
        "C",
        suffix="3",
        bear=-0.15,
        base_lower=0.05,
        base_upper=0.22,
        bull=0.45,
        catalyst_days=8,
    )
    return OpportunitySetSnapshot(
        captured_at=datetime(2026, 8, 21, 17, 0, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=60,
        candidates=(candidate_a, candidate_b, candidate_c),
        pareto_dimensions=PARETO_DIMENSIONS,
        dominance_relations=(
            DominanceRelation(
                dominator_security_id="B",
                dominated_security_id="A",
                strictly_better_dimensions=(
                    "bear_return_lower",
                    "base_return_lower",
                    "base_return_upper",
                    "bull_return_upper",
                    "nearest_catalyst_days",
                ),
            ),
        ),
        pareto_frontier_security_ids=("B", "C"),
        comparable_security_ids=("A", "B", "C"),
        fast_lane_research_security_ids=(),
        blocked_security_ids=(),
        epistemically_flagged_security_ids=(),
        unique_pareto_leader_security_id="B",
        flags=("multiple_non_dominated_opportunities",),
        guardrail_evidence_id=GUARDRAIL,
    )


def _base_candidate(
    base: OpportunitySetSnapshot,
    security_id: str,
) -> OpportunityCandidateSnapshot:
    return next(item for item in base.candidates if item.security_id == security_id)


def _gap_candidate(
    base: OpportunitySetSnapshot,
    security_id: str,
    *,
    relative_gap: float,
    suffix: str,
) -> ExpectationGapOpportunityCandidateSnapshot:
    return ExpectationGapOpportunityCandidateSnapshot(
        captured_at=datetime(2026, 8, 21, 17, 10, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        security_id=security_id,
        opportunity_candidate_snapshot_id=_base_candidate(base, security_id).snapshot_id,
        decision_expectation_gap_snapshot_id=suffix * 64,
        comparison_policy_snapshot_id=POLICY,
        consensus_provider_id="provider-x",
        metric=ExpectationMetric.OPERATING_INCOME,
        target_date=date(2026, 12, 31),
        consensus_relative_gap=relative_gap,
        comparison_blockers=(),
        flags=(),
        guardrail_evidence_id=GUARDRAIL,
    )


def _overlay(base: OpportunitySetSnapshot) -> ExpectationAugmentedOpportunitySetSnapshot:
    candidate_a = _gap_candidate(base, "A", relative_gap=0.20, suffix="4")
    candidate_b = _gap_candidate(base, "B", relative_gap=0.05, suffix="5")
    candidate_c = _gap_candidate(base, "C", relative_gap=0.10, suffix="6")
    return ExpectationAugmentedOpportunitySetSnapshot(
        captured_at=datetime(2026, 8, 21, 17, 20, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=60,
        base_opportunity_set_snapshot_id=base.snapshot_id,
        comparison_policy_snapshot_id=POLICY,
        candidates=(candidate_a, candidate_b, candidate_c),
        pareto_dimensions=EXPECTATION_AUGMENTED_PARETO_DIMENSIONS,
        dominance_relations=(),
        base_pareto_frontier_security_ids=("B", "C"),
        expectation_pareto_frontier_security_ids=("A", "C"),
        expectation_comparable_security_ids=("A", "B", "C"),
        expectation_blocked_security_ids=(),
        unique_expectation_pareto_leader_security_id="A",
        flags=("expectation_gap_changes_pareto_frontier",),
        guardrail_evidence_id=GUARDRAIL,
    )


def _registration(
    base: OpportunitySetSnapshot,
    *,
    registration_id: str,
    overlay: ExpectationAugmentedOpportunitySetSnapshot | None,
) -> ProspectiveOpportunityRegistration:
    return ProspectiveOpportunityRegistration(
        registration_id=registration_id,
        registered_at=datetime(2026, 8, 21, 18, 0, tzinfo=SEOUL),
        evaluation_date=EVALUATION_DATE,
        entry_session=ENTRY_SESSION,
        entry_rule=ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE,
        horizon_trading_days=60,
        opportunity_set_snapshot_id=base.snapshot_id,
        expectation_overlay_snapshot_id=(overlay.snapshot_id if overlay is not None else None),
        security_ids=("A", "B", "C"),
        base_pareto_frontier_security_ids=("B", "C"),
        expectation_pareto_frontier_security_ids=(
            ("A", "C") if overlay is not None else ()
        ),
        unique_base_leader_security_id="B",
        unique_expectation_leader_security_id=("A" if overlay is not None else None),
        benchmark_security_id="BM",
        price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        source_evidence_ids=(SOURCE,),
        guardrail_evidence_id=GUARDRAIL,
    )


def _realized(
    security_id: str,
    realized_return: float,
    *,
    benchmark_return: float,
) -> CandidateRealizedOutcome:
    return CandidateRealizedOutcome(
        security_id=security_id,
        entry_price=100.0,
        exit_price=100.0 * (1.0 + realized_return),
        realized_basis_return=realized_return,
        benchmark_excess_return=realized_return - benchmark_return,
        max_close_favorable_excursion=max(0.0, realized_return),
        max_close_adverse_excursion=min(0.0, realized_return),
    )


def _outcome_overlay(
    registration: ProspectiveOpportunityRegistration,
) -> ProspectiveOpportunityOutcomeSnapshot:
    benchmark_return = 0.05
    return ProspectiveOpportunityOutcomeSnapshot(
        scored_at=datetime(2026, 11, 16, 16, 0, tzinfo=SEOUL),
        registration_snapshot_id=registration.snapshot_id,
        entry_session=ENTRY_SESSION,
        target_session=TARGET_SESSION,
        horizon_trading_days=60,
        price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        benchmark_security_id="BM",
        benchmark_return=benchmark_return,
        candidate_outcomes=(
            _realized("A", 0.30, benchmark_return=benchmark_return),
            _realized("B", 0.10, benchmark_return=benchmark_return),
            _realized("C", 0.20, benchmark_return=benchmark_return),
        ),
        ex_post_winner_security_ids=("A",),
        base_frontier_best_return=0.20,
        base_frontier_regret=0.10,
        base_frontier_contains_ex_post_winner=False,
        unique_base_leader_regret=0.20,
        expectation_frontier_best_return=0.30,
        expectation_frontier_regret=0.0,
        expectation_frontier_contains_ex_post_winner=True,
        unique_expectation_leader_regret=0.0,
        expectation_overlay_incremental_best_return=0.10,
        flags=("base_pareto_frontier_missed_ex_post_winner",),
    )


def _outcome_base_only(
    registration: ProspectiveOpportunityRegistration,
) -> ProspectiveOpportunityOutcomeSnapshot:
    benchmark_return = 0.05
    return ProspectiveOpportunityOutcomeSnapshot(
        scored_at=datetime(2026, 11, 16, 16, 5, tzinfo=SEOUL),
        registration_snapshot_id=registration.snapshot_id,
        entry_session=ENTRY_SESSION,
        target_session=TARGET_SESSION,
        horizon_trading_days=60,
        price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        benchmark_security_id="BM",
        benchmark_return=benchmark_return,
        candidate_outcomes=(
            _realized("A", 0.10, benchmark_return=benchmark_return),
            _realized("B", 0.30, benchmark_return=benchmark_return),
            _realized("C", 0.20, benchmark_return=benchmark_return),
        ),
        ex_post_winner_security_ids=("B",),
        base_frontier_best_return=0.30,
        base_frontier_regret=0.0,
        base_frontier_contains_ex_post_winner=True,
        unique_base_leader_regret=0.0,
        expectation_frontier_best_return=None,
        expectation_frontier_regret=None,
        expectation_frontier_contains_ex_post_winner=None,
        unique_expectation_leader_regret=None,
        expectation_overlay_incremental_best_return=None,
        flags=(),
    )


def test_overlay_entry_records_only_observed_selection_attribution() -> None:
    base = _base()
    overlay = _overlay(base)
    registration = _registration(base, registration_id="overlay-60d", overlay=overlay)
    outcome = _outcome_overlay(registration)

    entry = build_prospective_decision_ledger_entry(
        base,
        registration,
        outcome,
        expectation_overlay=overlay,
    )

    assert entry.ex_post_winner_security_ids == ("A",)
    assert entry.base_frontier_regret == pytest.approx(0.10)
    assert entry.expectation_frontier_regret == pytest.approx(0.0)
    assert entry.expectation_overlay_incremental_best_return == pytest.approx(0.10)
    assert entry.expectation_provider_id == "provider-x"
    assert entry.expectation_metric is ExpectationMetric.OPERATING_INCOME
    assert ObservedDecisionAttribution.BASE_FRONTIER_MISSED_BEST_REGISTERED_CANDIDATE in (
        entry.observed_attributions
    )
    assert ObservedDecisionAttribution.EXPECTATION_OVERLAY_IMPROVED_FRONTIER_BEST_RETURN in (
        entry.observed_attributions
    )
    assert ObservedDecisionAttribution.EXPECTATION_COVERAGE_COMPLETE in (
        entry.observed_attributions
    )
    payload = entry.payload_without_id()
    assert payload["causal_skill_inference_enabled"] is False
    assert payload["weighted_score_training_enabled"] is False


def test_base_only_entry_does_not_invent_expectation_metadata() -> None:
    base = _base()
    registration = _registration(base, registration_id="base-only-60d", overlay=None)
    outcome = _outcome_base_only(registration)

    entry = build_prospective_decision_ledger_entry(base, registration, outcome)

    assert entry.expectation_overlay_snapshot_id is None
    assert entry.expectation_comparable_security_ids == ()
    assert entry.expectation_frontier_best_return is None
    assert ObservedDecisionAttribution.BASE_FRONTIER_RETAINED_BEST_REGISTERED_CANDIDATE in (
        entry.observed_attributions
    )
    assert ObservedDecisionAttribution.EXPECTATION_OVERLAY_NOT_REGISTERED in (
        entry.observed_attributions
    )


def test_ledger_aggregates_base_and_overlay_observations_without_refitting_score() -> None:
    base = _base()
    overlay = _overlay(base)
    overlay_registration = _registration(
        base,
        registration_id="overlay-60d",
        overlay=overlay,
    )
    base_registration = _registration(
        base,
        registration_id="base-only-60d",
        overlay=None,
    )
    overlay_entry = build_prospective_decision_ledger_entry(
        base,
        overlay_registration,
        _outcome_overlay(overlay_registration),
        expectation_overlay=overlay,
    )
    base_entry = build_prospective_decision_ledger_entry(
        base,
        base_registration,
        _outcome_base_only(base_registration),
    )

    ledger = build_prospective_decision_ledger(
        (overlay_entry, base_entry),
        built_at=datetime(2026, 11, 16, 17, 0, tzinfo=SEOUL),
    )

    assert len(ledger.cohort_summaries) == 1
    summary = ledger.cohort_summaries[0]
    assert summary.observation_count == 2
    assert summary.base_frontier_contains_winner_count == 1
    assert summary.base_frontier_contains_winner_rate == pytest.approx(0.5)
    assert summary.mean_base_frontier_regret == pytest.approx(0.05)
    assert summary.unique_base_leader_observation_count == 2
    assert summary.unique_base_leader_matched_best_count == 1
    assert summary.unique_base_leader_matched_best_rate == pytest.approx(0.5)
    assert summary.expectation_overlay_observation_count == 1
    assert summary.expectation_complete_coverage_count == 1
    assert summary.expectation_partial_coverage_count == 0
    assert summary.expectation_frontier_contains_winner_rate == pytest.approx(1.0)
    assert summary.expectation_overlay_improved_count == 1
    assert summary.expectation_overlay_degraded_count == 0
    assert summary.expectation_overlay_unchanged_count == 0
    assert summary.mean_expectation_overlay_incremental_best_return == pytest.approx(0.10)
    payload = ledger.payload_without_id()
    assert payload["descriptive_statistics_only"] is True
    assert payload["probability_estimation_enabled"] is False
    assert payload["portfolio_optimization_enabled"] is False


def test_ledger_rejects_outcome_metric_drift() -> None:
    base = _base()
    overlay = _overlay(base)
    registration = _registration(base, registration_id="overlay-60d", overlay=overlay)
    outcome = replace(_outcome_overlay(registration), base_frontier_regret=0.01)

    with pytest.raises(ValueError, match="base frontier regret has drifted"):
        build_prospective_decision_ledger_entry(
            base,
            registration,
            outcome,
            expectation_overlay=overlay,
        )


def test_ledger_rejects_registration_bound_to_another_opportunity_snapshot() -> None:
    base = _base()
    registration = _registration(base, registration_id="base-only-60d", overlay=None)
    wrong_registration = replace(registration, opportunity_set_snapshot_id="f" * 64)
    outcome = _outcome_base_only(wrong_registration)

    with pytest.raises(ValueError, match="different opportunity set"):
        build_prospective_decision_ledger_entry(base, wrong_registration, outcome)


def test_ledger_requires_the_exact_registered_expectation_overlay() -> None:
    base = _base()
    overlay = _overlay(base)
    registration = _registration(base, registration_id="overlay-60d", overlay=overlay)
    outcome = _outcome_overlay(registration)
    wrong_overlay = replace(overlay, comparison_policy_snapshot_id="f" * 64)

    with pytest.raises(ValueError, match="expectation overlay differs from registration"):
        build_prospective_decision_ledger_entry(
            base,
            registration,
            outcome,
            expectation_overlay=wrong_overlay,
        )


def test_ledger_snapshot_refuses_duplicate_registration_and_persistence_overwrite(
    tmp_path: Path,
) -> None:
    base = _base()
    registration = _registration(base, registration_id="base-only-60d", overlay=None)
    entry = build_prospective_decision_ledger_entry(
        base,
        registration,
        _outcome_base_only(registration),
    )

    with pytest.raises(ValueError, match="registration ids must be unique"):
        build_prospective_decision_ledger(
            (entry, entry),
            built_at=datetime(2026, 11, 16, 17, 0, tzinfo=SEOUL),
        )

    ledger = build_prospective_decision_ledger(
        (entry,),
        built_at=datetime(2026, 11, 16, 17, 0, tzinfo=SEOUL),
    )
    target = tmp_path / "prospective-decision-ledger.json"
    persist_prospective_decision_ledger(ledger, target)
    persisted = target.read_text(encoding="utf-8")
    assert ledger.snapshot_id in persisted

    with pytest.raises(FileExistsError, match="already exists"):
        persist_prospective_decision_ledger(ledger, target)
