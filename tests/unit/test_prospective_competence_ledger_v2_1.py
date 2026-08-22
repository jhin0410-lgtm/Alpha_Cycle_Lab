from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import alpha_cycle.intelligence.prospective_competence_ledger_v2_1 as competence_module
from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.prospective_causal_attribution_v2_1 import (
    AttributionDomain,
    AttributionHypothesis,
    AttributionHypothesisEvaluation,
    AttributionLayer,
    AttributionLayerSummary,
    ExpectedDirection,
    HypothesisEvaluationStatus,
    ObservedDirection,
    ProspectiveAttributionEvaluationSnapshot,
    ProspectiveAttributionPlanSnapshot,
)
from alpha_cycle.intelligence.prospective_competence_ledger_v2_1 import (
    CompetenceStatusCounts,
    build_competence_context_registration,
    build_competence_observation,
    build_prospective_competence_ledger,
    persist_competence_context,
    persist_competence_ledger,
    persist_competence_observation,
)
from alpha_cycle.intelligence.prospective_decision_ledger_v2_1 import (
    ObservedDecisionAttribution,
    ProspectiveDecisionLedgerEntry,
)
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    ProspectiveOpportunityRegistration,
    ScorekeepingEntryRule,
)

SEOUL = ZoneInfo("Asia/Seoul")
ENTRY_SESSION = date(2026, 8, 24)
TARGET_SESSION = date(2026, 11, 16)


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
        values: list[date] = []
        current = start
        while current <= end:
            if self.is_session(current):
                values.append(current)
            current += timedelta(days=1)
        if inclusive:
            return values
        return [item for item in values if start < item < end]

    def session_open(self, value: date) -> datetime:
        return datetime.combine(value, time(9, 0), tzinfo=self.timezone)

    def session_close(self, value: date) -> datetime:
        return datetime.combine(value, time(15, 30), tzinfo=self.timezone)

    def session_label(self, timestamp: datetime) -> date:
        return timestamp.astimezone(self.timezone).date()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _registration(
    primary_security_id: str = "A",
    *,
    suffix: str = "1",
) -> ProspectiveOpportunityRegistration:
    guardrail = load_decision_system_v21_guardrails()
    peer = f"PEER-{suffix}"
    return ProspectiveOpportunityRegistration(
        registration_id=f"registration-{suffix}",
        registered_at=datetime(2026, 8, 21, 18, 0, tzinfo=SEOUL),
        evaluation_date=date(2026, 8, 21),
        entry_session=ENTRY_SESSION,
        entry_rule=ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE,
        horizon_trading_days=60,
        opportunity_set_snapshot_id=_digest(f"opportunity-{suffix}"),
        expectation_overlay_snapshot_id=None,
        security_ids=(primary_security_id, peer),
        base_pareto_frontier_security_ids=(primary_security_id,),
        expectation_pareto_frontier_security_ids=(),
        unique_base_leader_security_id=primary_security_id,
        unique_expectation_leader_security_id=None,
        benchmark_security_id="BM",
        price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        source_evidence_ids=(_digest(f"source-{suffix}"),),
        guardrail_evidence_id=guardrail.evidence_id,
    )


def _hypotheses(suffix: str) -> tuple[AttributionHypothesis, ...]:
    specs = (
        (
            AttributionLayer.MARKET,
            AttributionDomain.MACRO_REGIME,
            ExpectedDirection.POSITIVE,
        ),
        (
            AttributionLayer.SECTOR_THEME,
            AttributionDomain.INDUSTRY_TRANSMISSION,
            ExpectedDirection.POSITIVE,
        ),
        (
            AttributionLayer.FACTOR_REGIME,
            AttributionDomain.VALUATION_REPRICING,
            ExpectedDirection.NEUTRAL,
        ),
        (
            AttributionLayer.SECURITY_SPECIFIC,
            AttributionDomain.COMPANY_FORECAST,
            ExpectedDirection.POSITIVE,
        ),
    )
    return tuple(
        AttributionHypothesis(
            hypothesis_id=f"{suffix}-{layer.value}",
            layer=layer,
            domain=domain,
            statement=f"{layer.value} prospective hypothesis",
            expected_direction=direction,
            observable_condition=f"observe {layer.value} state",
            predecision_evidence_refs=(f"evidence:{suffix}:{layer.value}",),
            invalidation_condition=f"invalidate {layer.value} hypothesis",
        )
        for layer, domain, direction in specs
    )


def _plan(
    registration: ProspectiveOpportunityRegistration,
    security_id: str,
    *,
    suffix: str,
) -> ProspectiveAttributionPlanSnapshot:
    guardrail = load_decision_system_v21_guardrails()
    return ProspectiveAttributionPlanSnapshot(
        plan_id=f"plan-{suffix}",
        planned_at=datetime(2026, 8, 23, 12, 0, tzinfo=SEOUL),
        registration_snapshot_id=registration.snapshot_id,
        registration_id=registration.registration_id,
        thesis_snapshot_id=_digest(f"thesis-snapshot-{suffix}"),
        thesis_id=f"thesis-{suffix}",
        security_id=security_id,
        evaluation_date=registration.evaluation_date,
        entry_session=registration.entry_session,
        horizon_trading_days=registration.horizon_trading_days,
        hypotheses=_hypotheses(suffix),
        guardrail_evidence_id=guardrail.evidence_id,
    )


def _ledger_entry(
    registration: ProspectiveOpportunityRegistration,
    *,
    suffix: str,
) -> ProspectiveDecisionLedgerEntry:
    primary = registration.security_ids[0]
    return ProspectiveDecisionLedgerEntry(
        registration_id=registration.registration_id,
        opportunity_set_snapshot_id=registration.opportunity_set_snapshot_id,
        expectation_overlay_snapshot_id=None,
        registration_snapshot_id=registration.snapshot_id,
        outcome_snapshot_id=_digest(f"outcome-{suffix}"),
        registered_at=registration.registered_at,
        scored_at=datetime(2026, 11, 16, 16, 0, tzinfo=SEOUL),
        evaluation_date=registration.evaluation_date,
        entry_session=ENTRY_SESSION,
        target_session=TARGET_SESSION,
        horizon_trading_days=60,
        price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        benchmark_security_id="BM",
        benchmark_return=0.05,
        security_ids=registration.security_ids,
        base_pareto_frontier_security_ids=(primary,),
        unique_base_leader_security_id=primary,
        expectation_comparable_security_ids=(),
        expectation_blocked_security_ids=(),
        expectation_pareto_frontier_security_ids=(),
        unique_expectation_leader_security_id=None,
        expectation_provider_id=None,
        expectation_metric=None,
        expectation_target_date=None,
        comparison_policy_snapshot_id=None,
        ex_post_winner_security_ids=(primary,),
        best_registered_candidate_return=0.20,
        base_frontier_best_return=0.20,
        base_frontier_regret=0.0,
        base_frontier_contains_ex_post_winner=True,
        unique_base_leader_regret=0.0,
        expectation_frontier_best_return=None,
        expectation_frontier_regret=None,
        expectation_frontier_contains_ex_post_winner=None,
        unique_expectation_leader_regret=None,
        expectation_overlay_incremental_best_return=None,
        observed_attributions=(
            ObservedDecisionAttribution.BASE_FRONTIER_RETAINED_BEST_REGISTERED_CANDIDATE,
            ObservedDecisionAttribution.UNIQUE_BASE_LEADER_MATCHED_BEST_REGISTERED_RETURN,
            ObservedDecisionAttribution.EXPECTATION_OVERLAY_NOT_REGISTERED,
        ),
        flags=(),
    )


def _directions_for_status(
    hypothesis: AttributionHypothesis,
    status: HypothesisEvaluationStatus,
) -> tuple[ObservedDirection, ...]:
    if status is HypothesisEvaluationStatus.CONSISTENT:
        return (ObservedDirection(hypothesis.expected_direction.value),)
    if status is HypothesisEvaluationStatus.INCONSISTENT:
        opposite = (
            ObservedDirection.NEGATIVE
            if hypothesis.expected_direction is ExpectedDirection.POSITIVE
            else ObservedDirection.POSITIVE
        )
        return (opposite,)
    if status is HypothesisEvaluationStatus.MIXED:
        return (ObservedDirection.MIXED,)
    return (ObservedDirection.UNKNOWN,)


def _evaluation(
    plan: ProspectiveAttributionPlanSnapshot,
    ledger: ProspectiveDecisionLedgerEntry,
    *,
    sector_status: HypothesisEvaluationStatus,
) -> ProspectiveAttributionEvaluationSnapshot:
    statuses = (
        HypothesisEvaluationStatus.CONSISTENT,
        sector_status,
        HypothesisEvaluationStatus.MIXED,
        HypothesisEvaluationStatus.INSUFFICIENT,
    )
    evaluations = tuple(
        AttributionHypothesisEvaluation(
            hypothesis_id=hypothesis.hypothesis_id,
            layer=hypothesis.layer,
            domain=hypothesis.domain,
            expected_direction=hypothesis.expected_direction,
            observed_directions=_directions_for_status(hypothesis, status),
            observation_ids=(f"obs-{hypothesis.hypothesis_id}",),
            status=status,
        )
        for hypothesis, status in zip(plan.hypotheses, statuses, strict=True)
    )
    summaries = tuple(
        AttributionLayerSummary(
            layer=evaluation.layer,
            hypothesis_count=1,
            consistent_count=int(
                evaluation.status is HypothesisEvaluationStatus.CONSISTENT
            ),
            inconsistent_count=int(
                evaluation.status is HypothesisEvaluationStatus.INCONSISTENT
            ),
            mixed_count=int(evaluation.status is HypothesisEvaluationStatus.MIXED),
            insufficient_count=int(
                evaluation.status is HypothesisEvaluationStatus.INSUFFICIENT
            ),
        )
        for evaluation in evaluations
    )
    guardrail = load_decision_system_v21_guardrails()
    return ProspectiveAttributionEvaluationSnapshot(
        evaluated_at=datetime(2026, 11, 16, 16, 20, tzinfo=SEOUL),
        plan_snapshot_id=plan.snapshot_id,
        outcome_evidence_snapshot_id=_digest(f"outcome-evidence-{plan.plan_id}"),
        ledger_entry_snapshot_id=ledger.snapshot_id,
        security_id=plan.security_id,
        horizon_trading_days=plan.horizon_trading_days,
        hypothesis_evaluations=evaluations,
        layer_summaries=summaries,
        selection_diagnostics=ledger.observed_attributions,
        flags=("diagnostic_only_no_causal_proof",),
        guardrail_evidence_id=guardrail.evidence_id,
    )


def _context(
    registration: ProspectiveOpportunityRegistration,
    plan: ProspectiveAttributionPlanSnapshot,
    *,
    suffix: str,
    dependency_cluster_id: str,
):
    return build_competence_context_registration(
        plan,
        registration,
        context_id=f"context-{suffix}",
        registered_at=datetime(2026, 8, 23, 13, 0, tzinfo=SEOUL),
        dependency_cluster_id=dependency_cluster_id,
        regime_taxonomy_id="macro-cycle-v1",
        regime_bucket_id="expansion",
        regime_evidence_refs=(f"evidence:regime:{suffix}",),
        calendar=WeekdayCalendar(),
    )


def _completed_observation(
    security_id: str,
    suffix: str,
    *,
    dependency_cluster_id: str,
    sector_status: HypothesisEvaluationStatus,
):
    registration = _registration(security_id, suffix=suffix)
    plan = _plan(registration, security_id, suffix=suffix)
    context = _context(
        registration,
        plan,
        suffix=suffix,
        dependency_cluster_id=dependency_cluster_id,
    )
    ledger = _ledger_entry(registration, suffix=suffix)
    evaluation = _evaluation(plan, ledger, sector_status=sector_status)
    observation = build_competence_observation(
        context,
        plan,
        evaluation,
        ledger,
        observed_at=datetime(2026, 11, 16, 16, 30, tzinfo=SEOUL),
    )
    return registration, plan, context, ledger, evaluation, observation


def test_context_freezes_grouping_labels_before_entry_close() -> None:
    registration = _registration()
    plan = _plan(registration, "A", suffix="1")
    context = _context(
        registration,
        plan,
        suffix="1",
        dependency_cluster_id="memory-cycle",
    )

    assert context.attribution_plan_snapshot_id == plan.snapshot_id
    assert context.dependency_cluster_id == "memory-cycle"
    payload = context.payload_without_id()
    assert payload["grouping_labels_frozen_before_outcome"] is True
    assert payload["statistical_effective_sample_size_claimed"] is False


def test_context_rejects_backdated_plan_and_late_context() -> None:
    registration = _registration()
    plan = _plan(registration, "A", suffix="1")
    backdated = replace(
        plan,
        planned_at=registration.registered_at - timedelta(minutes=1),
    )
    with pytest.raises(ValueError, match="cannot predate opportunity registration"):
        _context(
            registration,
            backdated,
            suffix="backdated",
            dependency_cluster_id="cluster-1",
        )

    with pytest.raises(ValueError, match="entry-session close"):
        build_competence_context_registration(
            plan,
            registration,
            context_id="late-context",
            registered_at=datetime(2026, 8, 24, 15, 31, tzinfo=SEOUL),
            dependency_cluster_id="cluster-1",
            regime_taxonomy_id="macro-cycle-v1",
            regime_bucket_id="expansion",
            regime_evidence_refs=("evidence:regime:late",),
            calendar=WeekdayCalendar(),
        )


def test_observation_recomputes_expected_direction_and_status() -> None:
    _registration_obj, plan, context, ledger, evaluation, _observation = (
        _completed_observation(
            "A",
            "1",
            dependency_cluster_id="cluster-1",
            sector_status=HypothesisEvaluationStatus.INCONSISTENT,
        )
    )
    first = evaluation.hypothesis_evaluations[0]
    wrong_direction = replace(first, expected_direction=ExpectedDirection.NEGATIVE)
    tampered_direction = replace(
        evaluation,
        hypothesis_evaluations=(
            wrong_direction,
            *evaluation.hypothesis_evaluations[1:],
        ),
    )
    with pytest.raises(ValueError, match="expected direction differs"):
        build_competence_observation(
            context,
            plan,
            tampered_direction,
            ledger,
            observed_at=datetime(2026, 11, 16, 16, 30, tzinfo=SEOUL),
        )

    wrong_status = replace(first, status=HypothesisEvaluationStatus.INCONSISTENT)
    tampered_status = replace(
        evaluation,
        hypothesis_evaluations=(wrong_status, *evaluation.hypothesis_evaluations[1:]),
    )
    with pytest.raises(ValueError, match="mechanical recomputation"):
        build_competence_observation(
            context,
            plan,
            tampered_status,
            ledger,
            observed_at=datetime(2026, 11, 16, 16, 30, tzinfo=SEOUL),
        )


def test_observation_revalidates_layer_summary() -> None:
    _registration_obj, plan, context, ledger, evaluation, _observation = (
        _completed_observation(
            "A",
            "1",
            dependency_cluster_id="cluster-1",
            sector_status=HypothesisEvaluationStatus.INCONSISTENT,
        )
    )
    market_summary = evaluation.layer_summaries[0]
    tampered_summary = replace(
        market_summary,
        consistent_count=0,
        inconsistent_count=1,
    )
    tampered = replace(
        evaluation,
        layer_summaries=(tampered_summary, *evaluation.layer_summaries[1:]),
    )
    with pytest.raises(ValueError, match="layer summary differs"):
        build_competence_observation(
            context,
            plan,
            tampered,
            ledger,
            observed_at=datetime(2026, 11, 16, 16, 30, tzinfo=SEOUL),
        )


def test_two_security_evaluations_may_share_one_decision_ledger_entry() -> None:
    registration = _registration("A", suffix="1")
    ledger = _ledger_entry(registration, suffix="shared")
    plan_a = _plan(registration, "A", suffix="A")
    plan_b = _plan(registration, "PEER-1", suffix="B")
    context_a = _context(
        registration,
        plan_a,
        suffix="A",
        dependency_cluster_id="shared-cycle",
    )
    context_b = _context(
        registration,
        plan_b,
        suffix="B",
        dependency_cluster_id="shared-cycle",
    )
    evaluation_a = _evaluation(
        plan_a,
        ledger,
        sector_status=HypothesisEvaluationStatus.INCONSISTENT,
    )
    evaluation_b = _evaluation(
        plan_b,
        ledger,
        sector_status=HypothesisEvaluationStatus.CONSISTENT,
    )
    observed_at = datetime(2026, 11, 16, 16, 30, tzinfo=SEOUL)
    observation_a = build_competence_observation(
        context_a,
        plan_a,
        evaluation_a,
        ledger,
        observed_at=observed_at,
    )
    observation_b = build_competence_observation(
        context_b,
        plan_b,
        evaluation_b,
        ledger,
        observed_at=observed_at,
    )

    competence = build_prospective_competence_ledger(
        (observation_a, observation_b),
        built_at=datetime(2026, 11, 16, 17, 0, tzinfo=SEOUL),
    )
    assert len(competence.observations) == 2
    assert {
        item.ledger_entry_snapshot_id for item in competence.observations
    } == {ledger.snapshot_id}
    assert competence.cohort_summaries[0].raw_observation_count == 2


def test_ledger_separates_raw_observations_from_dependency_clusters() -> None:
    observations = (
        _completed_observation(
            "A",
            "1",
            dependency_cluster_id="shared-memory-cycle",
            sector_status=HypothesisEvaluationStatus.INCONSISTENT,
        )[-1],
        _completed_observation(
            "B",
            "2",
            dependency_cluster_id="shared-memory-cycle",
            sector_status=HypothesisEvaluationStatus.INCONSISTENT,
        )[-1],
        _completed_observation(
            "C",
            "3",
            dependency_cluster_id="independent-defense-cycle",
            sector_status=HypothesisEvaluationStatus.CONSISTENT,
        )[-1],
    )
    ledger = build_prospective_competence_ledger(
        observations,
        built_at=datetime(2026, 11, 16, 17, 0, tzinfo=SEOUL),
    )

    cohort = ledger.cohort_summaries[0]
    assert cohort.raw_observation_count == 3
    assert cohort.independent_dependency_cluster_count == 2
    assert dict(cohort.dependency_cluster_counts) == {
        "independent-defense-cycle": 1,
        "shared-memory-cycle": 2,
    }
    sector = next(
        item
        for item in cohort.dimension_summaries
        if item.layer is AttributionLayer.SECTOR_THEME
        and item.domain is AttributionDomain.INDUSTRY_TRANSMISSION
    )
    assert sector.status_counts.inconsistent_count == 2
    assert sector.status_counts.consistent_count == 1
    payload = ledger.payload_without_id()
    assert payload["statistical_effective_sample_size_claimed"] is False
    assert payload["causal_skill_claim_enabled"] is False
    assert payload["composite_competence_score_enabled"] is False
    assert payload["single_trade_architecture_update_enabled"] is False


def test_ledger_recomputes_and_rejects_stale_cohort_summary() -> None:
    observation = _completed_observation(
        "A",
        "1",
        dependency_cluster_id="cluster-1",
        sector_status=HypothesisEvaluationStatus.INCONSISTENT,
    )[-1]
    ledger = build_prospective_competence_ledger(
        (observation,),
        built_at=datetime(2026, 11, 16, 17, 0, tzinfo=SEOUL),
    )
    cohort = ledger.cohort_summaries[0]
    sector_index = next(
        index
        for index, item in enumerate(cohort.dimension_summaries)
        if item.layer is AttributionLayer.SECTOR_THEME
        and item.domain is AttributionDomain.INDUSTRY_TRANSMISSION
    )
    sector = cohort.dimension_summaries[sector_index]
    counts = sector.status_counts
    swapped = CompetenceStatusCounts(
        consistent_count=counts.inconsistent_count,
        inconsistent_count=counts.consistent_count,
        mixed_count=counts.mixed_count,
        insufficient_count=counts.insufficient_count,
    )
    stale_sector = replace(sector, status_counts=swapped)
    dimensions = list(cohort.dimension_summaries)
    dimensions[sector_index] = stale_sector
    stale_cohort = replace(cohort, dimension_summaries=tuple(dimensions))

    with pytest.raises(ValueError, match="drifted from observations"):
        replace(ledger, cohort_summaries=(stale_cohort,))


def test_interrupted_persistence_removes_partial_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _registration_obj, _plan_obj, context, _ledger_obj, _evaluation_obj, _observation = (
        _completed_observation(
            "A",
            "1",
            dependency_cluster_id="cluster-1",
            sector_status=HypothesisEvaluationStatus.INCONSISTENT,
        )
    )
    path = tmp_path / "context.json"

    def interrupt_fsync(_descriptor: int) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(competence_module.os, "fsync", interrupt_fsync)
    with pytest.raises(KeyboardInterrupt):
        persist_competence_context(context, path)
    assert not path.exists()


def test_persistence_is_content_addressed_and_no_overwrite(tmp_path: Path) -> None:
    _registration_obj, _plan_obj, context, _ledger_obj, _evaluation_obj, observation = (
        _completed_observation(
            "A",
            "1",
            dependency_cluster_id="cluster-1",
            sector_status=HypothesisEvaluationStatus.INCONSISTENT,
        )
    )
    ledger = build_prospective_competence_ledger(
        (observation,),
        built_at=datetime(2026, 11, 16, 17, 0, tzinfo=SEOUL),
    )
    context_path = tmp_path / "context.json"
    observation_path = tmp_path / "observation.json"
    ledger_path = tmp_path / "ledger.json"

    persist_competence_context(context, context_path)
    persist_competence_observation(observation, observation_path)
    persist_competence_ledger(ledger, ledger_path)
    assert context.snapshot_id in context_path.read_text(encoding="utf-8")
    assert observation.snapshot_id in observation_path.read_text(encoding="utf-8")
    assert ledger.snapshot_id in ledger_path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        persist_competence_context(context, context_path)
    with pytest.raises(FileExistsError, match="already exists"):
        persist_competence_observation(observation, observation_path)
    with pytest.raises(FileExistsError, match="already exists"):
        persist_competence_ledger(ledger, ledger_path)
