"""Prospective diagnostic attribution contracts for Decision System v2.1.

The module separates an ex-ante attribution plan, post-outcome observations, and a mechanical
hypothesis evaluation. It records diagnostic consistency; it never promotes residual or
single-trade evidence into causal proof, portfolio advice, or an architecture change.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from alpha_cycle.calendar.base import TradingCalendar
from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    EXPECTED_ATTRIBUTION_LAYERS,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot
from alpha_cycle.intelligence.prospective_decision_ledger_v2_1 import (
    ObservedDecisionAttribution,
    ProspectiveDecisionLedgerEntry,
)
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    ProspectiveOpportunityRegistration,
    ScorekeepingEntryRule,
    derive_entry_session,
)

PROSPECTIVE_CAUSAL_ATTRIBUTION_SCHEMA_VERSION = 1
_SUPPORTED_HORIZONS = frozenset({60, 120, 250})


class AttributionLayer(StrEnum):
    """Frozen broad diagnostic decomposition from Decision System v2.1."""

    MARKET = "market"
    SECTOR_THEME = "sector_theme"
    FACTOR_REGIME = "factor_regime"
    SECURITY_SPECIFIC = "security_specific"


class AttributionDomain(StrEnum):
    """More specific research-error domain under the frozen broad layers."""

    MACRO_REGIME = "macro_regime"
    INDUSTRY_TRANSMISSION = "industry_transmission"
    COMPANY_FORECAST = "company_forecast"
    MARKET_EXPECTATION = "market_expectation"
    CATALYST_TIMING = "catalyst_timing"
    VALUATION_REPRICING = "valuation_repricing"
    OPPORTUNITY_SELECTION = "opportunity_selection"


class ExpectedDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class ObservedDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class HypothesisEvaluationStatus(StrEnum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    MIXED = "mixed"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class AttributionHypothesis:
    """One pre-outcome diagnostic hypothesis."""

    hypothesis_id: str
    layer: AttributionLayer
    domain: AttributionDomain
    statement: str
    expected_direction: ExpectedDirection
    observable_condition: str
    predecision_evidence_refs: tuple[str, ...]
    invalidation_condition: str

    def __post_init__(self) -> None:
        _require_text(self.hypothesis_id, "hypothesis_id")
        if not isinstance(self.layer, AttributionLayer):
            raise ValueError("layer must be an AttributionLayer")
        if not isinstance(self.domain, AttributionDomain):
            raise ValueError("domain must be an AttributionDomain")
        if not isinstance(self.expected_direction, ExpectedDirection):
            raise ValueError("expected_direction must be an ExpectedDirection")
        _require_text(self.statement, "hypothesis statement")
        _require_text(self.observable_condition, "observable_condition")
        _require_text(self.invalidation_condition, "invalidation_condition")
        _validate_refs(self.predecision_evidence_refs, "predecision_evidence_refs")
        if not self.predecision_evidence_refs:
            raise ValueError("attribution hypothesis requires predecision evidence")

    def payload(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "layer": self.layer.value,
            "domain": self.domain.value,
            "statement": self.statement,
            "expected_direction": self.expected_direction.value,
            "observable_condition": self.observable_condition,
            "predecision_evidence_refs": list(self.predecision_evidence_refs),
            "invalidation_condition": self.invalidation_condition,
        }


@dataclass(frozen=True)
class AttributionObservation:
    """One post-outcome observation bound to a preregistered hypothesis."""

    observation_id: str
    hypothesis_id: str
    layer: AttributionLayer
    domain: AttributionDomain
    statement: str
    observed_direction: ObservedDirection
    evidence_refs: tuple[str, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.observation_id, "observation_id")
        _require_text(self.hypothesis_id, "hypothesis_id")
        if not isinstance(self.layer, AttributionLayer):
            raise ValueError("observation layer must be an AttributionLayer")
        if not isinstance(self.domain, AttributionDomain):
            raise ValueError("observation domain must be an AttributionDomain")
        if not isinstance(self.observed_direction, ObservedDirection):
            raise ValueError("observed_direction must be an ObservedDirection")
        _require_text(self.statement, "observation statement")
        _validate_refs(self.evidence_refs, "observation evidence_refs")
        if not self.evidence_refs:
            raise ValueError("attribution observation requires outcome evidence")
        _require_aware(self.observed_at, "observed_at")

    def payload(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "hypothesis_id": self.hypothesis_id,
            "layer": self.layer.value,
            "domain": self.domain.value,
            "statement": self.statement,
            "observed_direction": self.observed_direction.value,
            "evidence_refs": list(self.evidence_refs),
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True)
class ProspectiveAttributionPlanSnapshot:
    """Immutable ex-ante diagnostic plan frozen before the scored entry close."""

    plan_id: str
    planned_at: datetime
    registration_snapshot_id: str
    registration_id: str
    thesis_snapshot_id: str
    thesis_id: str
    security_id: str
    evaluation_date: date
    entry_session: date
    horizon_trading_days: int
    hypotheses: tuple[AttributionHypothesis, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.plan_id, "plan_id")
        _require_aware(self.planned_at, "planned_at")
        for sha_value, field in (
            (self.registration_snapshot_id, "registration_snapshot_id"),
            (self.thesis_snapshot_id, "thesis_snapshot_id"),
            (self.guardrail_evidence_id, "guardrail_evidence_id"),
        ):
            _validate_sha(sha_value, field)
        _require_text(self.registration_id, "registration_id")
        _require_text(self.thesis_id, "thesis_id")
        _require_text(self.security_id, "security_id")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("attribution plan horizon must be 60, 120, or 250 trading days")
        if not self.hypotheses:
            raise ValueError("attribution plan requires at least one hypothesis")
        _validate_unique_ids(
            (item.hypothesis_id for item in self.hypotheses),
            "hypothesis_id",
        )
        observed_layers = {item.layer.value for item in self.hypotheses}
        if observed_layers != set(EXPECTED_ATTRIBUTION_LAYERS):
            raise ValueError("attribution plan must cover all frozen diagnostic layers")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_CAUSAL_ATTRIBUTION_SCHEMA_VERSION,
            "plan_id": self.plan_id,
            "planned_at": self.planned_at.isoformat(),
            "registration_snapshot_id": self.registration_snapshot_id,
            "registration_id": self.registration_id,
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "thesis_id": self.thesis_id,
            "security_id": self.security_id,
            "evaluation_date": self.evaluation_date.isoformat(),
            "entry_session": self.entry_session.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "hypotheses": [item.payload() for item in self.hypotheses],
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "frozen_before_outcome": True,
            "causal_conclusion_enabled": False,
            "portfolio_recommendation_enabled": False,
            "architecture_change_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class AttributionOutcomeEvidenceSnapshot:
    """Immutable post-outcome observations, separate from the frozen decision plan."""

    captured_at: datetime
    plan_snapshot_id: str
    registration_snapshot_id: str
    ledger_entry_snapshot_id: str
    security_id: str
    evaluation_date: date
    entry_session: date
    target_session: date
    horizon_trading_days: int
    observations: tuple[AttributionObservation, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        for sha_value, field in (
            (self.plan_snapshot_id, "plan_snapshot_id"),
            (self.registration_snapshot_id, "registration_snapshot_id"),
            (self.ledger_entry_snapshot_id, "ledger_entry_snapshot_id"),
            (self.guardrail_evidence_id, "guardrail_evidence_id"),
        ):
            _validate_sha(sha_value, field)
        _require_text(self.security_id, "security_id")
        if self.target_session <= self.entry_session:
            raise ValueError("attribution target_session must follow entry_session")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("attribution outcome horizon must be 60, 120, or 250")
        if not self.observations:
            raise ValueError("attribution outcome requires at least one observation")
        _validate_unique_ids(
            (item.observation_id for item in self.observations),
            "observation_id",
        )

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_CAUSAL_ATTRIBUTION_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "plan_snapshot_id": self.plan_snapshot_id,
            "registration_snapshot_id": self.registration_snapshot_id,
            "ledger_entry_snapshot_id": self.ledger_entry_snapshot_id,
            "security_id": self.security_id,
            "evaluation_date": self.evaluation_date.isoformat(),
            "entry_session": self.entry_session.isoformat(),
            "target_session": self.target_session.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "observations": [item.payload() for item in self.observations],
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "decision_snapshot_mutated": False,
            "causal_conclusion_enabled": False,
            "portfolio_recommendation_enabled": False,
            "architecture_change_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class AttributionHypothesisEvaluation:
    hypothesis_id: str
    layer: AttributionLayer
    domain: AttributionDomain
    expected_direction: ExpectedDirection
    observed_directions: tuple[ObservedDirection, ...]
    observation_ids: tuple[str, ...]
    status: HypothesisEvaluationStatus

    def __post_init__(self) -> None:
        _require_text(self.hypothesis_id, "hypothesis_id")
        _validate_unique_ids(self.observation_ids, "observation_id")
        if len(self.observed_directions) != len(self.observation_ids):
            raise ValueError("evaluation directions must align with observation ids")

    def payload(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "layer": self.layer.value,
            "domain": self.domain.value,
            "expected_direction": self.expected_direction.value,
            "observed_directions": [item.value for item in self.observed_directions],
            "observation_ids": list(self.observation_ids),
            "status": self.status.value,
        }


@dataclass(frozen=True)
class AttributionLayerSummary:
    layer: AttributionLayer
    hypothesis_count: int
    consistent_count: int
    inconsistent_count: int
    mixed_count: int
    insufficient_count: int

    def __post_init__(self) -> None:
        if self.hypothesis_count < 1:
            raise ValueError("layer summary requires at least one hypothesis")
        counts = (
            self.consistent_count,
            self.inconsistent_count,
            self.mixed_count,
            self.insufficient_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("layer summary counts cannot be negative")
        if sum(counts) != self.hypothesis_count:
            raise ValueError("layer summary statuses must partition hypotheses")

    def payload(self) -> dict[str, object]:
        return {
            "layer": self.layer.value,
            "hypothesis_count": self.hypothesis_count,
            "consistent_count": self.consistent_count,
            "inconsistent_count": self.inconsistent_count,
            "mixed_count": self.mixed_count,
            "insufficient_count": self.insufficient_count,
        }


@dataclass(frozen=True)
class ProspectiveAttributionEvaluationSnapshot:
    """Mechanical diagnostic evaluation; explicitly not a causal proof."""

    evaluated_at: datetime
    plan_snapshot_id: str
    outcome_evidence_snapshot_id: str
    ledger_entry_snapshot_id: str
    security_id: str
    horizon_trading_days: int
    hypothesis_evaluations: tuple[AttributionHypothesisEvaluation, ...]
    layer_summaries: tuple[AttributionLayerSummary, ...]
    selection_diagnostics: tuple[ObservedDecisionAttribution, ...]
    flags: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.evaluated_at, "evaluated_at")
        for sha_value, field in (
            (self.plan_snapshot_id, "plan_snapshot_id"),
            (self.outcome_evidence_snapshot_id, "outcome_evidence_snapshot_id"),
            (self.ledger_entry_snapshot_id, "ledger_entry_snapshot_id"),
            (self.guardrail_evidence_id, "guardrail_evidence_id"),
        ):
            _validate_sha(sha_value, field)
        _require_text(self.security_id, "security_id")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("attribution evaluation horizon must be 60, 120, or 250")
        if not self.hypothesis_evaluations:
            raise ValueError("attribution evaluation requires hypothesis results")
        _validate_unique_ids(
            (item.hypothesis_id for item in self.hypothesis_evaluations),
            "hypothesis_id",
        )
        summary_layers = tuple(item.layer.value for item in self.layer_summaries)
        if len(set(summary_layers)) != len(summary_layers):
            raise ValueError("attribution layer summaries must be unique")
        if set(summary_layers) != set(EXPECTED_ATTRIBUTION_LAYERS):
            raise ValueError("attribution evaluation must summarize all frozen layers")
        if len(set(self.selection_diagnostics)) != len(self.selection_diagnostics):
            raise ValueError("selection diagnostics must be unique")
        _validate_text_tuple(self.flags, "flags")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_CAUSAL_ATTRIBUTION_SCHEMA_VERSION,
            "evaluated_at": self.evaluated_at.isoformat(),
            "plan_snapshot_id": self.plan_snapshot_id,
            "outcome_evidence_snapshot_id": self.outcome_evidence_snapshot_id,
            "ledger_entry_snapshot_id": self.ledger_entry_snapshot_id,
            "security_id": self.security_id,
            "horizon_trading_days": self.horizon_trading_days,
            "hypothesis_evaluations": [
                item.payload() for item in self.hypothesis_evaluations
            ],
            "layer_summaries": [item.payload() for item in self.layer_summaries],
            "selection_diagnostics": [item.value for item in self.selection_diagnostics],
            "flags": list(self.flags),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "diagnostic_attribution_only": True,
            "residual_is_causal_proof": False,
            "causal_conclusion_enabled": False,
            "single_trade_architecture_update_enabled": False,
            "portfolio_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


def build_prospective_attribution_plan(
    registration: ProspectiveOpportunityRegistration,
    thesis: InvestmentThesisSnapshot,
    *,
    plan_id: str,
    planned_at: datetime,
    hypotheses: tuple[AttributionHypothesis, ...],
    calendar: TradingCalendar,
) -> ProspectiveAttributionPlanSnapshot:
    """Freeze a diagnostic plan no later than the scored entry-session close."""

    guardrails = load_decision_system_v21_guardrails()
    _validate_guardrail_contract(guardrails.attribution_required_diagnostic_layers)
    if registration.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("attribution plan registration uses another guardrail snapshot")
    _require_aware(planned_at, "planned_at")
    if thesis.captured_at > registration.registered_at:
        raise ValueError("attribution thesis must exist before registration")
    if planned_at < registration.registered_at:
        raise ValueError("attribution plan cannot predate registration")
    expected_entry = derive_entry_session(registration.registered_at, calendar=calendar)
    if registration.entry_rule is not ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE:
        raise ValueError("unsupported attribution entry rule")
    if registration.entry_session != expected_entry:
        raise ValueError("attribution registration entry session has drifted")
    if planned_at.astimezone(calendar.timezone) > calendar.session_close(expected_entry):
        raise ValueError("attribution plan must be frozen by entry-session close")
    if thesis.security_id not in registration.security_ids:
        raise ValueError("attribution thesis security is not in registration universe")
    if thesis.horizon_trading_days != registration.horizon_trading_days:
        raise ValueError("attribution thesis horizon differs from registration")
    if registration.horizon_trading_days not in _SUPPORTED_HORIZONS:
        raise ValueError("unsupported attribution horizon")
    return ProspectiveAttributionPlanSnapshot(
        plan_id=plan_id,
        planned_at=planned_at,
        registration_snapshot_id=registration.snapshot_id,
        registration_id=registration.registration_id,
        thesis_snapshot_id=thesis.snapshot_id,
        thesis_id=thesis.thesis_id,
        security_id=thesis.security_id,
        evaluation_date=registration.evaluation_date,
        entry_session=registration.entry_session,
        horizon_trading_days=registration.horizon_trading_days,
        hypotheses=hypotheses,
        guardrail_evidence_id=guardrails.evidence_id,
    )


def build_attribution_outcome_evidence(
    plan: ProspectiveAttributionPlanSnapshot,
    registration: ProspectiveOpportunityRegistration,
    ledger_entry: ProspectiveDecisionLedgerEntry,
    *,
    captured_at: datetime,
    observations: tuple[AttributionObservation, ...],
    calendar: TradingCalendar,
) -> AttributionOutcomeEvidenceSnapshot:
    """Bind post-outcome observations to the exact preregistered plan and ledger entry."""

    guardrails = load_decision_system_v21_guardrails()
    _validate_guardrail_contract(guardrails.attribution_required_diagnostic_layers)
    _validate_plan_registration_binding(plan, registration, guardrails.evidence_id)
    _validate_ledger_binding(plan, registration, ledger_entry, calendar=calendar)
    _require_aware(captured_at, "captured_at")
    target_session = _target_session(
        registration.entry_session,
        registration.horizon_trading_days,
        calendar=calendar,
    )
    target_close = calendar.session_close(target_session)
    if captured_at.astimezone(calendar.timezone) < target_close:
        raise ValueError("attribution outcome evidence cannot precede target-session close")
    if captured_at < ledger_entry.scored_at:
        raise ValueError("attribution outcome evidence cannot predate ledger scoring")
    hypotheses = {item.hypothesis_id: item for item in plan.hypotheses}
    for observation in observations:
        hypothesis = hypotheses.get(observation.hypothesis_id)
        if hypothesis is None:
            raise ValueError("attribution observation references an unregistered hypothesis")
        if observation.layer is not hypothesis.layer:
            raise ValueError("attribution observation layer differs from frozen hypothesis")
        if observation.domain is not hypothesis.domain:
            raise ValueError("attribution observation domain differs from frozen hypothesis")
        if observation.observed_at.astimezone(calendar.timezone) < target_close:
            raise ValueError("attribution observation cannot precede target-session close")
        if observation.observed_at > captured_at:
            raise ValueError("attribution observation cannot postdate evidence snapshot")
    return AttributionOutcomeEvidenceSnapshot(
        captured_at=captured_at,
        plan_snapshot_id=plan.snapshot_id,
        registration_snapshot_id=registration.snapshot_id,
        ledger_entry_snapshot_id=ledger_entry.snapshot_id,
        security_id=plan.security_id,
        evaluation_date=plan.evaluation_date,
        entry_session=plan.entry_session,
        target_session=target_session,
        horizon_trading_days=plan.horizon_trading_days,
        observations=observations,
        guardrail_evidence_id=guardrails.evidence_id,
    )


def build_attribution_evaluation(
    plan: ProspectiveAttributionPlanSnapshot,
    outcome_evidence: AttributionOutcomeEvidenceSnapshot,
    ledger_entry: ProspectiveDecisionLedgerEntry,
    *,
    evaluated_at: datetime,
) -> ProspectiveAttributionEvaluationSnapshot:
    """Mechanically compare frozen expected directions with observed directions."""

    guardrails = load_decision_system_v21_guardrails()
    _validate_guardrail_contract(guardrails.attribution_required_diagnostic_layers)
    if plan.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("attribution plan uses another guardrail snapshot")
    if outcome_evidence.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("attribution outcome evidence uses another guardrail snapshot")
    if outcome_evidence.plan_snapshot_id != plan.snapshot_id:
        raise ValueError("attribution outcome evidence is bound to another plan")
    if outcome_evidence.ledger_entry_snapshot_id != ledger_entry.snapshot_id:
        raise ValueError("attribution outcome evidence is bound to another ledger entry")
    if ledger_entry.registration_snapshot_id != plan.registration_snapshot_id:
        raise ValueError("attribution ledger entry is bound to another registration")
    if plan.security_id not in ledger_entry.security_ids:
        raise ValueError("attribution security is absent from ledger candidate universe")
    if outcome_evidence.security_id != plan.security_id:
        raise ValueError("attribution outcome security differs from plan")
    if outcome_evidence.horizon_trading_days != plan.horizon_trading_days:
        raise ValueError("attribution outcome horizon differs from plan")
    _require_aware(evaluated_at, "evaluated_at")
    if evaluated_at < outcome_evidence.captured_at:
        raise ValueError("attribution evaluation cannot predate outcome evidence")
    if evaluated_at < ledger_entry.scored_at:
        raise ValueError("attribution evaluation cannot predate ledger scoring")

    by_hypothesis: dict[str, list[AttributionObservation]] = {
        item.hypothesis_id: [] for item in plan.hypotheses
    }
    for observation in outcome_evidence.observations:
        if observation.hypothesis_id not in by_hypothesis:
            raise ValueError("outcome evidence contains an unregistered hypothesis")
        by_hypothesis[observation.hypothesis_id].append(observation)

    evaluations = tuple(
        _evaluate_hypothesis(item, tuple(by_hypothesis[item.hypothesis_id]))
        for item in plan.hypotheses
    )
    layer_summaries = tuple(
        _summarize_layer(layer, evaluations)
        for layer in AttributionLayer
    )
    flags: list[str] = []
    statuses = {item.status for item in evaluations}
    if HypothesisEvaluationStatus.INCONSISTENT in statuses:
        flags.append("one_or_more_predeclared_hypotheses_inconsistent")
    if HypothesisEvaluationStatus.MIXED in statuses:
        flags.append("one_or_more_predeclared_hypotheses_mixed")
    if HypothesisEvaluationStatus.INSUFFICIENT in statuses:
        flags.append("one_or_more_predeclared_hypotheses_insufficient")
    flags.append("diagnostic_only_no_causal_proof")
    return ProspectiveAttributionEvaluationSnapshot(
        evaluated_at=evaluated_at,
        plan_snapshot_id=plan.snapshot_id,
        outcome_evidence_snapshot_id=outcome_evidence.snapshot_id,
        ledger_entry_snapshot_id=ledger_entry.snapshot_id,
        security_id=plan.security_id,
        horizon_trading_days=plan.horizon_trading_days,
        hypothesis_evaluations=evaluations,
        layer_summaries=layer_summaries,
        selection_diagnostics=ledger_entry.observed_attributions,
        flags=tuple(flags),
        guardrail_evidence_id=guardrails.evidence_id,
    )


def persist_attribution_plan(
    snapshot: ProspectiveAttributionPlanSnapshot,
    path: Path,
) -> None:
    _persist_snapshot(snapshot.snapshot_id, snapshot.payload_without_id(), path)


def persist_attribution_outcome_evidence(
    snapshot: AttributionOutcomeEvidenceSnapshot,
    path: Path,
) -> None:
    _persist_snapshot(snapshot.snapshot_id, snapshot.payload_without_id(), path)


def persist_attribution_evaluation(
    snapshot: ProspectiveAttributionEvaluationSnapshot,
    path: Path,
) -> None:
    _persist_snapshot(snapshot.snapshot_id, snapshot.payload_without_id(), path)


def _validate_plan_registration_binding(
    plan: ProspectiveAttributionPlanSnapshot,
    registration: ProspectiveOpportunityRegistration,
    guardrail_evidence_id: str,
) -> None:
    if plan.registration_snapshot_id != registration.snapshot_id:
        raise ValueError("attribution plan is bound to another registration")
    if plan.registration_id != registration.registration_id:
        raise ValueError("attribution plan registration id differs")
    if plan.evaluation_date != registration.evaluation_date:
        raise ValueError("attribution plan evaluation date differs from registration")
    if plan.entry_session != registration.entry_session:
        raise ValueError("attribution plan entry session differs from registration")
    if plan.horizon_trading_days != registration.horizon_trading_days:
        raise ValueError("attribution plan horizon differs from registration")
    if plan.security_id not in registration.security_ids:
        raise ValueError("attribution plan security is absent from registration")
    if plan.guardrail_evidence_id != guardrail_evidence_id:
        raise ValueError("attribution plan uses another guardrail snapshot")
    if registration.guardrail_evidence_id != guardrail_evidence_id:
        raise ValueError("attribution registration uses another guardrail snapshot")


def _validate_ledger_binding(
    plan: ProspectiveAttributionPlanSnapshot,
    registration: ProspectiveOpportunityRegistration,
    ledger_entry: ProspectiveDecisionLedgerEntry,
    *,
    calendar: TradingCalendar,
) -> None:
    expected_entry = derive_entry_session(registration.registered_at, calendar=calendar)
    if registration.entry_rule is not ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE:
        raise ValueError("unsupported attribution entry rule")
    if registration.entry_session != expected_entry:
        raise ValueError("attribution registration entry session has drifted")
    if ledger_entry.registration_snapshot_id != registration.snapshot_id:
        raise ValueError("attribution ledger entry is bound to another registration")
    if ledger_entry.registration_id != registration.registration_id:
        raise ValueError("attribution ledger registration id differs")
    if plan.security_id not in ledger_entry.security_ids:
        raise ValueError("attribution security is absent from ledger candidate universe")
    if ledger_entry.evaluation_date != plan.evaluation_date:
        raise ValueError("attribution ledger evaluation date differs from plan")
    if ledger_entry.entry_session != registration.entry_session:
        raise ValueError("attribution ledger entry session differs from registration")
    if ledger_entry.horizon_trading_days != registration.horizon_trading_days:
        raise ValueError("attribution ledger horizon differs from registration")
    target_session = _target_session(
        registration.entry_session,
        registration.horizon_trading_days,
        calendar=calendar,
    )
    if ledger_entry.target_session != target_session:
        raise ValueError("attribution ledger target session differs from declared horizon")
    if ledger_entry.scored_at.astimezone(calendar.timezone) < calendar.session_close(target_session):
        raise ValueError("attribution ledger was scored before target-session close")


def _evaluate_hypothesis(
    hypothesis: AttributionHypothesis,
    observations: tuple[AttributionObservation, ...],
) -> AttributionHypothesisEvaluation:
    known = tuple(
        item for item in observations if item.observed_direction is not ObservedDirection.UNKNOWN
    )
    if not known:
        status = HypothesisEvaluationStatus.INSUFFICIENT
    elif any(item.observed_direction is ObservedDirection.MIXED for item in known):
        status = HypothesisEvaluationStatus.MIXED
    else:
        expected = hypothesis.expected_direction.value
        observed_values = {item.observed_direction.value for item in known}
        if observed_values == {expected}:
            status = HypothesisEvaluationStatus.CONSISTENT
        elif expected not in observed_values and len(observed_values) == 1:
            status = HypothesisEvaluationStatus.INCONSISTENT
        else:
            status = HypothesisEvaluationStatus.MIXED
    return AttributionHypothesisEvaluation(
        hypothesis_id=hypothesis.hypothesis_id,
        layer=hypothesis.layer,
        domain=hypothesis.domain,
        expected_direction=hypothesis.expected_direction,
        observed_directions=tuple(item.observed_direction for item in observations),
        observation_ids=tuple(item.observation_id for item in observations),
        status=status,
    )


def _summarize_layer(
    layer: AttributionLayer,
    evaluations: tuple[AttributionHypothesisEvaluation, ...],
) -> AttributionLayerSummary:
    items = tuple(item for item in evaluations if item.layer is layer)
    if not items:
        raise ValueError("all frozen attribution layers require at least one hypothesis")
    return AttributionLayerSummary(
        layer=layer,
        hypothesis_count=len(items),
        consistent_count=sum(
            item.status is HypothesisEvaluationStatus.CONSISTENT for item in items
        ),
        inconsistent_count=sum(
            item.status is HypothesisEvaluationStatus.INCONSISTENT for item in items
        ),
        mixed_count=sum(item.status is HypothesisEvaluationStatus.MIXED for item in items),
        insufficient_count=sum(
            item.status is HypothesisEvaluationStatus.INSUFFICIENT for item in items
        ),
    )


def _target_session(
    entry_session: date,
    horizon_trading_days: int,
    *,
    calendar: TradingCalendar,
) -> date:
    if horizon_trading_days not in _SUPPORTED_HORIZONS:
        raise ValueError("unsupported attribution horizon")
    if not calendar.is_session(entry_session):
        raise ValueError("attribution entry session is not a trading session")
    current = entry_session
    for _ in range(horizon_trading_days):
        current = calendar.next_session(current)
    return current


def _validate_guardrail_contract(layers: tuple[str, ...]) -> None:
    enum_layers = tuple(item.value for item in AttributionLayer)
    if layers != EXPECTED_ATTRIBUTION_LAYERS:
        raise ValueError("active guardrail attribution layers have drifted")
    if enum_layers != EXPECTED_ATTRIBUTION_LAYERS:
        raise ValueError("attribution enum differs from frozen guardrail layers")


def _persist_snapshot(
    snapshot_id: str,
    payload_without_id: dict[str, object],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"snapshot_id": snapshot_id, **payload_without_id}
    encoded = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise FileExistsError(f"attribution snapshot already exists: {path}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _require_text(value: str, field: str) -> None:
    if not value.strip():
        raise ValueError(f"{field} cannot be empty")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _validate_refs(values: tuple[str, ...], field: str) -> None:
    _validate_text_tuple(values, field)


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")
    for value in values:
        _require_text(value, field)


def _validate_unique_ids(values: object, field: str) -> None:
    items = tuple(values)  # type: ignore[arg-type]
    if len(set(items)) != len(items):
        raise ValueError(f"{field} must be unique")
    for value in items:
        if not isinstance(value, str):
            raise ValueError(f"{field} must contain strings")
        _require_text(value, field)


def _sha(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
