from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.data.integrity import PriceBasis
from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import (
    ClaimDirection,
    EpistemicStatus,
    InvestmentThesisSnapshot,
    ThesisClaim,
    ThesisStatus,
    ThesisUncertainty,
    UncertaintyDimension,
    UncertaintyLevel,
)
from alpha_cycle.intelligence.prospective_causal_attribution_v2_1 import (
    AttributionDomain,
    AttributionHypothesis,
    AttributionLayer,
    AttributionObservation,
    ExpectedDirection,
    HypothesisEvaluationStatus,
    ObservedDirection,
    build_attribution_evaluation,
    build_attribution_outcome_evidence,
    build_prospective_attribution_plan,
    persist_attribution_evaluation,
    persist_attribution_outcome_evidence,
    persist_attribution_plan,
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
SHA_A = "a" * 64
SHA_B = "b" * 64


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


def _uncertainty() -> ThesisUncertainty:
    item = UncertaintyDimension(level=UncertaintyLevel.MEDIUM, rationale="prospective test")
    return ThesisUncertainty(
        evidence=item,
        model=item,
        regime=item,
        expectation=item,
        catalyst=item,
        valuation=item,
    )


def _thesis(*, security_id: str = "A", horizon: int = 60) -> InvestmentThesisSnapshot:
    return InvestmentThesisSnapshot(
        thesis_id="thesis-A",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=datetime(2026, 8, 21, 17, 0, tzinfo=SEOUL),
        security_id=security_id,
        horizon_trading_days=horizon,
        variant_view="earnings and repricing can outperform the registered set",
        why_now="prospective attribution boundary test",
        claims=(
            ThesisClaim(
                claim_id="claim-1",
                category="industry_cycle",
                statement="industry transmission should remain supportive",
                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
                direction=ClaimDirection.POSITIVE,
                evidence_refs=("evidence:industry",),
            ),
        ),
        catalysts=(),
        forecast_refs=("forecast:registered",),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=("industry transmission reverses",),
        first_rejection_risk="the expected transmission never reaches earnings",
        portfolio_overlap=(),
        opportunity_set_refs=("opportunity:set",),
        status=ThesisStatus.UNDERWRITING,
    )


def _registration(
    *,
    entry_session: date = ENTRY_SESSION,
) -> ProspectiveOpportunityRegistration:
    guardrail = load_decision_system_v21_guardrails()
    return ProspectiveOpportunityRegistration(
        registration_id="decision-set-2026-08-21-60d",
        registered_at=datetime(2026, 8, 21, 18, 0, tzinfo=SEOUL),
        evaluation_date=date(2026, 8, 21),
        entry_session=entry_session,
        entry_rule=ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE,
        horizon_trading_days=60,
        opportunity_set_snapshot_id=SHA_A,
        expectation_overlay_snapshot_id=None,
        security_ids=("A", "B"),
        base_pareto_frontier_security_ids=("A",),
        expectation_pareto_frontier_security_ids=(),
        unique_base_leader_security_id="A",
        unique_expectation_leader_security_id=None,
        benchmark_security_id="BM",
        price_basis=PriceBasis.TOTAL_RETURN_ADJUSTED,
        source_evidence_ids=(SHA_B,),
        guardrail_evidence_id=guardrail.evidence_id,
    )


def _hypotheses() -> tuple[AttributionHypothesis, ...]:
    return (
        AttributionHypothesis(
            hypothesis_id="market-liquidity",
            layer=AttributionLayer.MARKET,
            domain=AttributionDomain.MACRO_REGIME,
            statement="market liquidity remains supportive",
            expected_direction=ExpectedDirection.POSITIVE,
            observable_condition="broad liquidity and market breadth do not deteriorate",
            predecision_evidence_refs=("evidence:market",),
            invalidation_condition="broad liquidity contracts materially",
        ),
        AttributionHypothesis(
            hypothesis_id="sector-transmission",
            layer=AttributionLayer.SECTOR_THEME,
            domain=AttributionDomain.INDUSTRY_TRANSMISSION,
            statement="sector demand reaches company revenue",
            expected_direction=ExpectedDirection.POSITIVE,
            observable_condition="orders and revenue recognition remain supportive",
            predecision_evidence_refs=("evidence:sector",),
            invalidation_condition="orders or recognition reverse",
        ),
        AttributionHypothesis(
            hypothesis_id="factor-regime",
            layer=AttributionLayer.FACTOR_REGIME,
            domain=AttributionDomain.VALUATION_REPRICING,
            statement="factor regime is neutral to relative performance",
            expected_direction=ExpectedDirection.NEUTRAL,
            observable_condition="factor exposure contributes no clear directional tailwind",
            predecision_evidence_refs=("evidence:factor",),
            invalidation_condition="factor regime becomes clearly directional",
        ),
        AttributionHypothesis(
            hypothesis_id="security-forecast",
            layer=AttributionLayer.SECURITY_SPECIFIC,
            domain=AttributionDomain.COMPANY_FORECAST,
            statement="company earnings path remains supportive",
            expected_direction=ExpectedDirection.POSITIVE,
            observable_condition="reported earnings remain aligned with the frozen forecast",
            predecision_evidence_refs=("evidence:company",),
            invalidation_condition="reported earnings materially miss the frozen forecast",
        ),
    )


def _plan(
    registration: ProspectiveOpportunityRegistration,
    *,
    planned_at: datetime | None = None,
    hypotheses: tuple[AttributionHypothesis, ...] | None = None,
):
    return build_prospective_attribution_plan(
        registration,
        _thesis(),
        plan_id="attribution-plan-A-60d",
        planned_at=planned_at or datetime(2026, 8, 23, 12, 0, tzinfo=SEOUL),
        hypotheses=hypotheses or _hypotheses(),
        calendar=WeekdayCalendar(),
    )


def _ledger_entry(
    registration: ProspectiveOpportunityRegistration,
    *,
    target_session: date = TARGET_SESSION,
    scored_at: datetime | None = None,
) -> ProspectiveDecisionLedgerEntry:
    return ProspectiveDecisionLedgerEntry(
        registration_id=registration.registration_id,
        opportunity_set_snapshot_id=registration.opportunity_set_snapshot_id,
        expectation_overlay_snapshot_id=None,
        registration_snapshot_id=registration.snapshot_id,
        outcome_snapshot_id="c" * 64,
        registered_at=registration.registered_at,
        scored_at=scored_at or datetime(2026, 11, 16, 16, 0, tzinfo=SEOUL),
        evaluation_date=registration.evaluation_date,
        entry_session=registration.entry_session,
        target_session=target_session,
        horizon_trading_days=registration.horizon_trading_days,
        price_basis=registration.price_basis,
        benchmark_security_id=registration.benchmark_security_id,
        benchmark_return=0.05,
        security_ids=registration.security_ids,
        base_pareto_frontier_security_ids=("A",),
        unique_base_leader_security_id="A",
        expectation_comparable_security_ids=(),
        expectation_blocked_security_ids=(),
        expectation_pareto_frontier_security_ids=(),
        unique_expectation_leader_security_id=None,
        expectation_provider_id=None,
        expectation_metric=None,
        expectation_target_date=None,
        comparison_policy_snapshot_id=None,
        ex_post_winner_security_ids=("A",),
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


def _observation(
    observation_id: str,
    hypothesis: AttributionHypothesis,
    direction: ObservedDirection,
    *,
    observed_at: datetime | None = None,
) -> AttributionObservation:
    return AttributionObservation(
        observation_id=observation_id,
        hypothesis_id=hypothesis.hypothesis_id,
        layer=hypothesis.layer,
        domain=hypothesis.domain,
        statement=f"observed {hypothesis.hypothesis_id}",
        observed_direction=direction,
        evidence_refs=(f"evidence:outcome:{observation_id}",),
        observed_at=observed_at or datetime(2026, 11, 16, 16, 5, tzinfo=SEOUL),
    )


def test_plan_is_content_addressed_and_freezes_all_guardrail_layers() -> None:
    registration = _registration()
    plan = _plan(registration)

    assert len(plan.snapshot_id) == 64
    assert {item.layer for item in plan.hypotheses} == set(AttributionLayer)
    payload = plan.payload_without_id()
    assert payload["frozen_before_outcome"] is True
    assert payload["causal_conclusion_enabled"] is False
    assert payload["architecture_change_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_plan_rejects_after_entry_close_and_registration_entry_drift() -> None:
    registration = _registration()
    with pytest.raises(ValueError, match="entry-session close"):
        _plan(
            registration,
            planned_at=datetime(2026, 8, 24, 15, 31, tzinfo=SEOUL),
        )

    wrong_registration = _registration(entry_session=date(2026, 8, 25))
    with pytest.raises(ValueError, match="entry session has drifted"):
        _plan(wrong_registration)


def test_plan_rejects_wrong_thesis_security_horizon_and_missing_layer() -> None:
    registration = _registration()
    with pytest.raises(ValueError, match="security is not in registration universe"):
        build_prospective_attribution_plan(
            registration,
            _thesis(security_id="Z"),
            plan_id="wrong-security",
            planned_at=datetime(2026, 8, 23, 12, 0, tzinfo=SEOUL),
            hypotheses=_hypotheses(),
            calendar=WeekdayCalendar(),
        )

    with pytest.raises(ValueError, match="horizon differs"):
        build_prospective_attribution_plan(
            registration,
            _thesis(horizon=120),
            plan_id="wrong-horizon",
            planned_at=datetime(2026, 8, 23, 12, 0, tzinfo=SEOUL),
            hypotheses=_hypotheses(),
            calendar=WeekdayCalendar(),
        )

    with pytest.raises(ValueError, match="cover all frozen diagnostic layers"):
        _plan(registration, hypotheses=_hypotheses()[:-1])


def test_plan_rejects_duplicate_hypothesis_ids() -> None:
    registration = _registration()
    hypotheses = list(_hypotheses())
    hypotheses[-1] = replace(hypotheses[-1], hypothesis_id=hypotheses[0].hypothesis_id)
    with pytest.raises(ValueError, match="hypothesis_id must be unique"):
        _plan(registration, hypotheses=tuple(hypotheses))


def test_outcome_evidence_revalidates_target_close_and_ledger_binding() -> None:
    registration = _registration()
    plan = _plan(registration)
    ledger = _ledger_entry(registration)
    observation = _observation("market-1", plan.hypotheses[0], ObservedDirection.POSITIVE)

    with pytest.raises(ValueError, match="target-session close"):
        build_attribution_outcome_evidence(
            plan,
            registration,
            ledger,
            captured_at=datetime(2026, 11, 16, 15, 29, tzinfo=SEOUL),
            observations=(observation,),
            calendar=WeekdayCalendar(),
        )

    wrong_target = _ledger_entry(registration, target_session=date(2026, 11, 17))
    with pytest.raises(ValueError, match="target session differs"):
        build_attribution_outcome_evidence(
            plan,
            registration,
            wrong_target,
            captured_at=datetime(2026, 11, 17, 16, 0, tzinfo=SEOUL),
            observations=(
                replace(observation, observed_at=datetime(2026, 11, 17, 15, 40, tzinfo=SEOUL)),
            ),
            calendar=WeekdayCalendar(),
        )


def test_outcome_evidence_rejects_observation_reassignment() -> None:
    registration = _registration()
    plan = _plan(registration)
    ledger = _ledger_entry(registration)
    observation = _observation("market-1", plan.hypotheses[0], ObservedDirection.POSITIVE)
    wrong_layer = replace(observation, layer=AttributionLayer.SECURITY_SPECIFIC)

    with pytest.raises(ValueError, match="layer differs"):
        build_attribution_outcome_evidence(
            plan,
            registration,
            ledger,
            captured_at=datetime(2026, 11, 16, 16, 10, tzinfo=SEOUL),
            observations=(wrong_layer,),
            calendar=WeekdayCalendar(),
        )


def test_evaluation_mechanically_reports_consistent_inconsistent_mixed_insufficient() -> None:
    registration = _registration()
    plan = _plan(registration)
    ledger = _ledger_entry(registration)
    market, sector, factor, _security = plan.hypotheses
    observations = (
        _observation("market-1", market, ObservedDirection.POSITIVE),
        _observation("sector-1", sector, ObservedDirection.NEGATIVE),
        _observation("factor-1", factor, ObservedDirection.NEUTRAL),
        _observation("factor-2", factor, ObservedDirection.POSITIVE),
    )
    evidence = build_attribution_outcome_evidence(
        plan,
        registration,
        ledger,
        captured_at=datetime(2026, 11, 16, 16, 10, tzinfo=SEOUL),
        observations=observations,
        calendar=WeekdayCalendar(),
    )

    evaluation = build_attribution_evaluation(
        plan,
        evidence,
        ledger,
        evaluated_at=datetime(2026, 11, 16, 16, 20, tzinfo=SEOUL),
    )

    statuses = {item.hypothesis_id: item.status for item in evaluation.hypothesis_evaluations}
    assert statuses["market-liquidity"] is HypothesisEvaluationStatus.CONSISTENT
    assert statuses["sector-transmission"] is HypothesisEvaluationStatus.INCONSISTENT
    assert statuses["factor-regime"] is HypothesisEvaluationStatus.MIXED
    assert statuses["security-forecast"] is HypothesisEvaluationStatus.INSUFFICIENT
    assert evaluation.selection_diagnostics == ledger.observed_attributions
    assert {item.layer for item in evaluation.layer_summaries} == set(AttributionLayer)
    payload = evaluation.payload_without_id()
    assert payload["diagnostic_attribution_only"] is True
    assert payload["residual_is_causal_proof"] is False
    assert payload["causal_conclusion_enabled"] is False
    assert payload["single_trade_architecture_update_enabled"] is False
    assert payload["portfolio_recommendation_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_evaluation_rejects_another_ledger_entry() -> None:
    registration = _registration()
    plan = _plan(registration)
    ledger = _ledger_entry(registration)
    evidence = build_attribution_outcome_evidence(
        plan,
        registration,
        ledger,
        captured_at=datetime(2026, 11, 16, 16, 10, tzinfo=SEOUL),
        observations=(
            _observation("market-1", plan.hypotheses[0], ObservedDirection.POSITIVE),
        ),
        calendar=WeekdayCalendar(),
    )
    wrong_ledger = replace(ledger, outcome_snapshot_id="f" * 64)

    with pytest.raises(ValueError, match="another ledger entry"):
        build_attribution_evaluation(
            plan,
            evidence,
            wrong_ledger,
            evaluated_at=datetime(2026, 11, 16, 16, 20, tzinfo=SEOUL),
        )


def test_attribution_persistence_is_content_addressed_and_no_overwrite(tmp_path: Path) -> None:
    registration = _registration()
    plan = _plan(registration)
    ledger = _ledger_entry(registration)
    evidence = build_attribution_outcome_evidence(
        plan,
        registration,
        ledger,
        captured_at=datetime(2026, 11, 16, 16, 10, tzinfo=SEOUL),
        observations=(
            _observation("market-1", plan.hypotheses[0], ObservedDirection.POSITIVE),
        ),
        calendar=WeekdayCalendar(),
    )
    evaluation = build_attribution_evaluation(
        plan,
        evidence,
        ledger,
        evaluated_at=datetime(2026, 11, 16, 16, 20, tzinfo=SEOUL),
    )

    snapshots = (
        (plan, tmp_path / "plan.json", persist_attribution_plan),
        (evidence, tmp_path / "outcome.json", persist_attribution_outcome_evidence),
        (evaluation, tmp_path / "evaluation.json", persist_attribution_evaluation),
    )
    for snapshot, target, persist in snapshots:
        persist(snapshot, target)
        assert snapshot.snapshot_id in target.read_text(encoding="utf-8")
        with pytest.raises(FileExistsError, match="already exists"):
            persist(snapshot, target)
