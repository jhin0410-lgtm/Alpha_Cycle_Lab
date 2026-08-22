"""Dependency-aware prospective competence ledger for Decision System v2.1.

This module learns only descriptive recurrence patterns across completed prospective attribution
experiments. Regime and dependency-cluster labels are frozen before the outcome so later grouping
cannot be chosen after seeing performance. Raw observations and independent cluster counts remain
separate; no statistical effective sample size, composite skill score, or architecture update is
claimed.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alpha_cycle.calendar.base import TradingCalendar
from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.prospective_causal_attribution_v2_1 import (
    AttributionDomain,
    AttributionLayer,
    HypothesisEvaluationStatus,
    ProspectiveAttributionEvaluationSnapshot,
    ProspectiveAttributionPlanSnapshot,
)
from alpha_cycle.intelligence.prospective_decision_ledger_v2_1 import (
    ObservedDecisionAttribution,
    ProspectiveDecisionLedgerEntry,
)
from alpha_cycle.intelligence.prospective_opportunity_scorekeeping_v2_1 import (
    ProspectiveOpportunityRegistration,
    ScorekeepingEntryRule,
    derive_entry_session,
)

PROSPECTIVE_COMPETENCE_LEDGER_SCHEMA_VERSION = 1
_SUPPORTED_HORIZONS = frozenset({60, 120, 250})


@dataclass(frozen=True)
class CompetenceContextRegistration:
    """Ex-ante regime and dependency labels for one attribution plan."""

    context_id: str
    registered_at: datetime
    attribution_plan_snapshot_id: str
    registration_snapshot_id: str
    security_id: str
    horizon_trading_days: int
    dependency_cluster_id: str
    regime_taxonomy_id: str
    regime_bucket_id: str
    regime_evidence_refs: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.context_id, "context_id")
        _require_aware(self.registered_at, "registered_at")
        for sha_value, field in (
            (self.attribution_plan_snapshot_id, "attribution_plan_snapshot_id"),
            (self.registration_snapshot_id, "registration_snapshot_id"),
            (self.guardrail_evidence_id, "guardrail_evidence_id"),
        ):
            _validate_sha(sha_value, field)
        _require_text(self.security_id, "security_id")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("competence context horizon must be 60, 120, or 250")
        _require_text(self.dependency_cluster_id, "dependency_cluster_id")
        _require_text(self.regime_taxonomy_id, "regime_taxonomy_id")
        _require_text(self.regime_bucket_id, "regime_bucket_id")
        _validate_refs(self.regime_evidence_refs, "regime_evidence_refs")
        if not self.regime_evidence_refs:
            raise ValueError("competence context requires pre-outcome regime evidence")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_COMPETENCE_LEDGER_SCHEMA_VERSION,
            "context_id": self.context_id,
            "registered_at": self.registered_at.isoformat(),
            "attribution_plan_snapshot_id": self.attribution_plan_snapshot_id,
            "registration_snapshot_id": self.registration_snapshot_id,
            "security_id": self.security_id,
            "horizon_trading_days": self.horizon_trading_days,
            "dependency_cluster_id": self.dependency_cluster_id,
            "regime_taxonomy_id": self.regime_taxonomy_id,
            "regime_bucket_id": self.regime_bucket_id,
            "regime_evidence_refs": list(self.regime_evidence_refs),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "grouping_labels_frozen_before_outcome": True,
            "statistical_effective_sample_size_claimed": False,
            "composite_competence_score_enabled": False,
            "architecture_change_enabled": False,
            "portfolio_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class CompetenceHypothesisResult:
    hypothesis_id: str
    layer: AttributionLayer
    domain: AttributionDomain
    status: HypothesisEvaluationStatus

    def __post_init__(self) -> None:
        _require_text(self.hypothesis_id, "hypothesis_id")
        if not isinstance(self.layer, AttributionLayer):
            raise ValueError("competence result layer must be AttributionLayer")
        if not isinstance(self.domain, AttributionDomain):
            raise ValueError("competence result domain must be AttributionDomain")
        if not isinstance(self.status, HypothesisEvaluationStatus):
            raise ValueError("competence result status must be HypothesisEvaluationStatus")

    def payload(self) -> dict[str, str]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "layer": self.layer.value,
            "domain": self.domain.value,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class CompetenceObservationSnapshot:
    """One completed attribution evaluation with frozen grouping context."""

    observed_at: datetime
    context_snapshot_id: str
    attribution_plan_snapshot_id: str
    attribution_evaluation_snapshot_id: str
    ledger_entry_snapshot_id: str
    security_id: str
    horizon_trading_days: int
    dependency_cluster_id: str
    regime_taxonomy_id: str
    regime_bucket_id: str
    hypothesis_results: tuple[CompetenceHypothesisResult, ...]
    selection_diagnostics: tuple[ObservedDecisionAttribution, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        for sha_value, field in (
            (self.context_snapshot_id, "context_snapshot_id"),
            (self.attribution_plan_snapshot_id, "attribution_plan_snapshot_id"),
            (self.attribution_evaluation_snapshot_id, "attribution_evaluation_snapshot_id"),
            (self.ledger_entry_snapshot_id, "ledger_entry_snapshot_id"),
            (self.guardrail_evidence_id, "guardrail_evidence_id"),
        ):
            _validate_sha(sha_value, field)
        _require_text(self.security_id, "security_id")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("competence observation horizon must be 60, 120, or 250")
        _require_text(self.dependency_cluster_id, "dependency_cluster_id")
        _require_text(self.regime_taxonomy_id, "regime_taxonomy_id")
        _require_text(self.regime_bucket_id, "regime_bucket_id")
        if not self.hypothesis_results:
            raise ValueError("competence observation requires hypothesis results")
        _validate_unique_ids(
            (item.hypothesis_id for item in self.hypothesis_results),
            "hypothesis_id",
        )
        observed_layers = {item.layer for item in self.hypothesis_results}
        if observed_layers != set(AttributionLayer):
            raise ValueError("competence observation must retain all attribution layers")
        if len(set(self.selection_diagnostics)) != len(self.selection_diagnostics):
            raise ValueError("competence selection diagnostics must be unique")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": PROSPECTIVE_COMPETENCE_LEDGER_SCHEMA_VERSION,
            "observed_at": self.observed_at.isoformat(),
            "context_snapshot_id": self.context_snapshot_id,
            "attribution_plan_snapshot_id": self.attribution_plan_snapshot_id,
            "attribution_evaluation_snapshot_id": (
                self.attribution_evaluation_snapshot_id
            ),
            "ledger_entry_snapshot_id": self.ledger_entry_snapshot_id,
            "security_id": self.security_id,
            "horizon_trading_days": self.horizon_trading_days,
            "dependency_cluster_id": self.dependency_cluster_id,
            "regime_taxonomy_id": self.regime_taxonomy_id,
            "regime_bucket_id": self.regime_bucket_id,
            "hypothesis_results": [item.payload() for item in self.hypothesis_results],
            "selection_diagnostics": [item.value for item in self.selection_diagnostics],
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "descriptive_learning_only": True,
            "statistical_effective_sample_size_claimed": False,
            "causal_skill_claim_enabled": False,
            "composite_competence_score_enabled": False,
            "single_trade_architecture_update_enabled": False,
            "portfolio_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class CompetenceStatusCounts:
    consistent_count: int
    inconsistent_count: int
    mixed_count: int
    insufficient_count: int

    def __post_init__(self) -> None:
        values = (
            self.consistent_count,
            self.inconsistent_count,
            self.mixed_count,
            self.insufficient_count,
        )
        if any(value < 0 for value in values):
            raise ValueError("competence status counts cannot be negative")
        if sum(values) <= 0:
            raise ValueError("competence status counts require at least one result")

    @property
    def total(self) -> int:
        return (
            self.consistent_count
            + self.inconsistent_count
            + self.mixed_count
            + self.insufficient_count
        )

    def payload(self) -> dict[str, int]:
        return {
            "consistent_count": self.consistent_count,
            "inconsistent_count": self.inconsistent_count,
            "mixed_count": self.mixed_count,
            "insufficient_count": self.insufficient_count,
            "total": self.total,
        }


@dataclass(frozen=True)
class CompetenceDimensionSummary:
    layer: AttributionLayer
    domain: AttributionDomain
    status_counts: CompetenceStatusCounts

    def payload(self) -> dict[str, object]:
        return {
            "layer": self.layer.value,
            "domain": self.domain.value,
            "status_counts": self.status_counts.payload(),
        }


@dataclass(frozen=True)
class CompetenceCohortSummary:
    """One horizon × preregistered regime cohort, with dependency counts kept explicit."""

    horizon_trading_days: int
    regime_taxonomy_id: str
    regime_bucket_id: str
    raw_observation_count: int
    independent_dependency_cluster_count: int
    dependency_cluster_counts: tuple[tuple[str, int], ...]
    dimension_summaries: tuple[CompetenceDimensionSummary, ...]

    def __post_init__(self) -> None:
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("competence cohort horizon must be 60, 120, or 250")
        _require_text(self.regime_taxonomy_id, "regime_taxonomy_id")
        _require_text(self.regime_bucket_id, "regime_bucket_id")
        if self.raw_observation_count <= 0:
            raise ValueError("competence cohort requires observations")
        if self.independent_dependency_cluster_count <= 0:
            raise ValueError("competence cohort requires dependency clusters")
        if self.independent_dependency_cluster_count > self.raw_observation_count:
            raise ValueError("dependency cluster count cannot exceed raw observation count")
        if len(self.dependency_cluster_counts) != self.independent_dependency_cluster_count:
            raise ValueError("dependency cluster registry must contain each cluster once")
        cluster_ids = tuple(item[0] for item in self.dependency_cluster_counts)
        if len(set(cluster_ids)) != len(cluster_ids):
            raise ValueError("dependency cluster ids must be unique")
        if any(count <= 0 for _, count in self.dependency_cluster_counts):
            raise ValueError("dependency cluster counts must be positive")
        if sum(count for _, count in self.dependency_cluster_counts) != self.raw_observation_count:
            raise ValueError("dependency cluster counts must partition raw observations")
        dimension_keys = tuple(
            (item.layer, item.domain) for item in self.dimension_summaries
        )
        if len(set(dimension_keys)) != len(dimension_keys):
            raise ValueError("competence dimension summaries must be unique")
        if not self.dimension_summaries:
            raise ValueError("competence cohort requires dimension summaries")

    def payload(self) -> dict[str, object]:
        return {
            "horizon_trading_days": self.horizon_trading_days,
            "regime_taxonomy_id": self.regime_taxonomy_id,
            "regime_bucket_id": self.regime_bucket_id,
            "raw_observation_count": self.raw_observation_count,
            "independent_dependency_cluster_count": (
                self.independent_dependency_cluster_count
            ),
            "dependency_cluster_counts": [
                {"dependency_cluster_id": cluster_id, "observation_count": count}
                for cluster_id, count in self.dependency_cluster_counts
            ],
            "dimension_summaries": [item.payload() for item in self.dimension_summaries],
            "statistical_effective_sample_size_claimed": False,
            "cluster_balanced_skill_score_enabled": False,
        }


@dataclass(frozen=True)
class ProspectiveCompetenceLedgerSnapshot:
    """Content-addressed descriptive learning surface across completed observations."""

    built_at: datetime
    observations: tuple[CompetenceObservationSnapshot, ...]
    cohort_summaries: tuple[CompetenceCohortSummary, ...]
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_aware(self.built_at, "built_at")
        if not self.observations:
            raise ValueError("competence ledger requires at least one observation")
        context_ids = tuple(item.context_snapshot_id for item in self.observations)
        evaluation_ids = tuple(
            item.attribution_evaluation_snapshot_id for item in self.observations
        )
        ledger_ids = tuple(item.ledger_entry_snapshot_id for item in self.observations)
        if len(set(context_ids)) != len(context_ids):
            raise ValueError("competence context snapshots must be unique")
        if len(set(evaluation_ids)) != len(evaluation_ids):
            raise ValueError("competence attribution evaluations must be unique")
        if len(set(ledger_ids)) != len(ledger_ids):
            raise ValueError("competence ledger entries must be unique")
        if any(item.observed_at > self.built_at for item in self.observations):
            raise ValueError("competence ledger cannot predate an included observation")
        expected = _build_cohort_summaries(self.observations)
        if len(expected) != len(self.cohort_summaries):
            raise ValueError("competence cohort summary count has drifted")
        expected_payloads = {item.cohort_key: item.payload() for item in expected}
        actual_payloads = {
            item.cohort_key: item.payload() for item in self.cohort_summaries
        }
        if actual_payloads != expected_payloads:
            raise ValueError("competence cohort summaries have drifted from observations")
        _validate_text_tuple(self.flags, "flags")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        ordered_observations = sorted(
            self.observations,
            key=lambda item: (
                item.horizon_trading_days,
                item.regime_taxonomy_id,
                item.regime_bucket_id,
                item.dependency_cluster_id,
                item.security_id,
                item.context_snapshot_id,
            ),
        )
        ordered_cohorts = sorted(
            self.cohort_summaries,
            key=lambda item: item.cohort_key,
        )
        return {
            "schema_version": PROSPECTIVE_COMPETENCE_LEDGER_SCHEMA_VERSION,
            "built_at": self.built_at.isoformat(),
            "observations": [item.payload_without_id() for item in ordered_observations],
            "cohort_summaries": [item.payload() for item in ordered_cohorts],
            "flags": list(self.flags),
            "descriptive_learning_only": True,
            "dependency_clusters_not_raw_rows_define_independence_boundary": True,
            "statistical_effective_sample_size_claimed": False,
            "causal_skill_claim_enabled": False,
            "composite_competence_score_enabled": False,
            "probability_estimation_enabled": False,
            "single_trade_architecture_update_enabled": False,
            "architecture_change_proposal_bypassed": False,
            "portfolio_optimization_enabled": False,
            "automatic_execution_enabled": False,
        }


def _cohort_key(summary: CompetenceCohortSummary) -> tuple[int, str, str]:
    return (
        summary.horizon_trading_days,
        summary.regime_taxonomy_id,
        summary.regime_bucket_id,
    )


CompetenceCohortSummary.cohort_key = property(_cohort_key)  # type: ignore[attr-defined]


def build_competence_context_registration(
    attribution_plan: ProspectiveAttributionPlanSnapshot,
    registration: ProspectiveOpportunityRegistration,
    *,
    context_id: str,
    registered_at: datetime,
    dependency_cluster_id: str,
    regime_taxonomy_id: str,
    regime_bucket_id: str,
    regime_evidence_refs: tuple[str, ...],
    calendar: TradingCalendar,
) -> CompetenceContextRegistration:
    """Freeze grouping labels before the first scored close."""

    guardrails = load_decision_system_v21_guardrails()
    if guardrails.single_trade_outcome_may_change_architecture_invariant:
        raise ValueError("active guardrails unexpectedly allow single-trade architecture changes")
    if attribution_plan.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("competence attribution plan uses another guardrail snapshot")
    if registration.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("competence registration uses another guardrail snapshot")
    if attribution_plan.registration_snapshot_id != registration.snapshot_id:
        raise ValueError("competence attribution plan is bound to another registration")
    if attribution_plan.security_id not in registration.security_ids:
        raise ValueError("competence security is absent from registration universe")
    if attribution_plan.horizon_trading_days != registration.horizon_trading_days:
        raise ValueError("competence attribution horizon differs from registration")
    _require_aware(registered_at, "registered_at")
    if registered_at < attribution_plan.planned_at:
        raise ValueError("competence context cannot predate attribution plan")
    expected_entry = derive_entry_session(registration.registered_at, calendar=calendar)
    if registration.entry_rule is not ScorekeepingEntryRule.NEXT_AVAILABLE_SESSION_CLOSE:
        raise ValueError("unsupported competence entry rule")
    if registration.entry_session != expected_entry:
        raise ValueError("competence registration entry session has drifted")
    if registered_at.astimezone(calendar.timezone) > calendar.session_close(expected_entry):
        raise ValueError("competence context must be frozen by entry-session close")
    return CompetenceContextRegistration(
        context_id=context_id,
        registered_at=registered_at,
        attribution_plan_snapshot_id=attribution_plan.snapshot_id,
        registration_snapshot_id=registration.snapshot_id,
        security_id=attribution_plan.security_id,
        horizon_trading_days=registration.horizon_trading_days,
        dependency_cluster_id=dependency_cluster_id,
        regime_taxonomy_id=regime_taxonomy_id,
        regime_bucket_id=regime_bucket_id,
        regime_evidence_refs=regime_evidence_refs,
        guardrail_evidence_id=guardrails.evidence_id,
    )


def build_competence_observation(
    context: CompetenceContextRegistration,
    attribution_plan: ProspectiveAttributionPlanSnapshot,
    attribution_evaluation: ProspectiveAttributionEvaluationSnapshot,
    ledger_entry: ProspectiveDecisionLedgerEntry,
    *,
    observed_at: datetime,
) -> CompetenceObservationSnapshot:
    """Bind one completed attribution result to its ex-ante learning context."""

    guardrails = load_decision_system_v21_guardrails()
    if context.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("competence context uses another guardrail snapshot")
    if attribution_plan.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("competence attribution plan uses another guardrail snapshot")
    if attribution_evaluation.guardrail_evidence_id != guardrails.evidence_id:
        raise ValueError("competence attribution evaluation uses another guardrail snapshot")
    if context.attribution_plan_snapshot_id != attribution_plan.snapshot_id:
        raise ValueError("competence context is bound to another attribution plan")
    if attribution_evaluation.plan_snapshot_id != attribution_plan.snapshot_id:
        raise ValueError("competence evaluation is bound to another attribution plan")
    if attribution_evaluation.ledger_entry_snapshot_id != ledger_entry.snapshot_id:
        raise ValueError("competence evaluation is bound to another ledger entry")
    if ledger_entry.registration_snapshot_id != context.registration_snapshot_id:
        raise ValueError("competence ledger entry is bound to another registration")
    if context.security_id != attribution_plan.security_id:
        raise ValueError("competence context security differs from attribution plan")
    if attribution_evaluation.security_id != context.security_id:
        raise ValueError("competence evaluation security differs from context")
    if context.security_id not in ledger_entry.security_ids:
        raise ValueError("competence security is absent from ledger universe")
    if context.horizon_trading_days != attribution_plan.horizon_trading_days:
        raise ValueError("competence context horizon differs from attribution plan")
    if attribution_evaluation.horizon_trading_days != context.horizon_trading_days:
        raise ValueError("competence evaluation horizon differs from context")
    if ledger_entry.horizon_trading_days != context.horizon_trading_days:
        raise ValueError("competence ledger horizon differs from context")
    _require_aware(observed_at, "observed_at")
    if observed_at < attribution_evaluation.evaluated_at:
        raise ValueError("competence observation cannot predate attribution evaluation")
    if observed_at < ledger_entry.scored_at:
        raise ValueError("competence observation cannot predate ledger scoring")
    expected_hypotheses = {item.hypothesis_id: item for item in attribution_plan.hypotheses}
    results: list[CompetenceHypothesisResult] = []
    for evaluation in attribution_evaluation.hypothesis_evaluations:
        hypothesis = expected_hypotheses.get(evaluation.hypothesis_id)
        if hypothesis is None:
            raise ValueError("competence evaluation contains an unregistered hypothesis")
        if evaluation.layer is not hypothesis.layer:
            raise ValueError("competence evaluation layer differs from frozen hypothesis")
        if evaluation.domain is not hypothesis.domain:
            raise ValueError("competence evaluation domain differs from frozen hypothesis")
        results.append(
            CompetenceHypothesisResult(
                hypothesis_id=evaluation.hypothesis_id,
                layer=evaluation.layer,
                domain=evaluation.domain,
                status=evaluation.status,
            )
        )
    if set(expected_hypotheses) != {item.hypothesis_id for item in results}:
        raise ValueError("competence evaluation does not cover all frozen hypotheses")
    if attribution_evaluation.selection_diagnostics != ledger_entry.observed_attributions:
        raise ValueError("competence selection diagnostics differ from validated ledger entry")
    return CompetenceObservationSnapshot(
        observed_at=observed_at,
        context_snapshot_id=context.snapshot_id,
        attribution_plan_snapshot_id=attribution_plan.snapshot_id,
        attribution_evaluation_snapshot_id=attribution_evaluation.snapshot_id,
        ledger_entry_snapshot_id=ledger_entry.snapshot_id,
        security_id=context.security_id,
        horizon_trading_days=context.horizon_trading_days,
        dependency_cluster_id=context.dependency_cluster_id,
        regime_taxonomy_id=context.regime_taxonomy_id,
        regime_bucket_id=context.regime_bucket_id,
        hypothesis_results=tuple(results),
        selection_diagnostics=attribution_evaluation.selection_diagnostics,
        guardrail_evidence_id=guardrails.evidence_id,
    )


def build_prospective_competence_ledger(
    observations: tuple[CompetenceObservationSnapshot, ...],
    *,
    built_at: datetime,
) -> ProspectiveCompetenceLedgerSnapshot:
    """Aggregate descriptive recurrence while preserving dependency-cluster counts."""

    guardrails = load_decision_system_v21_guardrails()
    if guardrails.single_trade_outcome_may_change_architecture_invariant:
        raise ValueError("active guardrails unexpectedly allow single-trade architecture changes")
    if not guardrails.architecture_change_proposal_required:
        raise ValueError("active guardrails unexpectedly bypass architecture proposals")
    for observation in observations:
        if observation.guardrail_evidence_id != guardrails.evidence_id:
            raise ValueError("competence observation uses another guardrail snapshot")
    return ProspectiveCompetenceLedgerSnapshot(
        built_at=built_at,
        observations=observations,
        cohort_summaries=_build_cohort_summaries(observations),
        flags=(
            "descriptive_only_no_causal_skill_claim",
            "dependency_clusters_reported_separately_from_raw_observations",
            "single_trade_architecture_learning_quarantined",
        ),
    )


def persist_competence_context(
    snapshot: CompetenceContextRegistration,
    path: Path,
) -> None:
    _persist_snapshot(snapshot.snapshot_id, snapshot.payload_without_id(), path)


def persist_competence_observation(
    snapshot: CompetenceObservationSnapshot,
    path: Path,
) -> None:
    _persist_snapshot(snapshot.snapshot_id, snapshot.payload_without_id(), path)


def persist_competence_ledger(
    snapshot: ProspectiveCompetenceLedgerSnapshot,
    path: Path,
) -> None:
    _persist_snapshot(snapshot.snapshot_id, snapshot.payload_without_id(), path)


def _build_cohort_summaries(
    observations: tuple[CompetenceObservationSnapshot, ...],
) -> tuple[CompetenceCohortSummary, ...]:
    if not observations:
        raise ValueError("competence cohorts require at least one observation")
    groups: dict[tuple[int, str, str], list[CompetenceObservationSnapshot]] = {}
    for observation in observations:
        key = (
            observation.horizon_trading_days,
            observation.regime_taxonomy_id,
            observation.regime_bucket_id,
        )
        groups.setdefault(key, []).append(observation)
    summaries = tuple(
        _summarize_cohort(key, tuple(items))
        for key, items in sorted(groups.items())
    )
    return summaries


def _summarize_cohort(
    key: tuple[int, str, str],
    observations: tuple[CompetenceObservationSnapshot, ...],
) -> CompetenceCohortSummary:
    cluster_counts: dict[str, int] = {}
    dimension_statuses: dict[
        tuple[AttributionLayer, AttributionDomain],
        list[HypothesisEvaluationStatus],
    ] = {}
    for observation in observations:
        cluster_counts[observation.dependency_cluster_id] = (
            cluster_counts.get(observation.dependency_cluster_id, 0) + 1
        )
        for result in observation.hypothesis_results:
            dimension_statuses.setdefault((result.layer, result.domain), []).append(
                result.status
            )
    dimension_summaries = tuple(
        CompetenceDimensionSummary(
            layer=layer,
            domain=domain,
            status_counts=_status_counts(tuple(statuses)),
        )
        for (layer, domain), statuses in sorted(
            dimension_statuses.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        )
    )
    ordered_clusters = tuple(sorted(cluster_counts.items()))
    return CompetenceCohortSummary(
        horizon_trading_days=key[0],
        regime_taxonomy_id=key[1],
        regime_bucket_id=key[2],
        raw_observation_count=len(observations),
        independent_dependency_cluster_count=len(ordered_clusters),
        dependency_cluster_counts=ordered_clusters,
        dimension_summaries=dimension_summaries,
    )


def _status_counts(
    statuses: tuple[HypothesisEvaluationStatus, ...],
) -> CompetenceStatusCounts:
    return CompetenceStatusCounts(
        consistent_count=sum(
            item is HypothesisEvaluationStatus.CONSISTENT for item in statuses
        ),
        inconsistent_count=sum(
            item is HypothesisEvaluationStatus.INCONSISTENT for item in statuses
        ),
        mixed_count=sum(item is HypothesisEvaluationStatus.MIXED for item in statuses),
        insufficient_count=sum(
            item is HypothesisEvaluationStatus.INSUFFICIENT for item in statuses
        ),
    )


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
        raise FileExistsError(f"competence snapshot already exists: {path}") from exc
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


def _validate_unique_ids(values: Iterable[str], field: str) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise ValueError(f"{field} must be unique")
    for value in items:
        _require_text(value, field)


def _sha(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
