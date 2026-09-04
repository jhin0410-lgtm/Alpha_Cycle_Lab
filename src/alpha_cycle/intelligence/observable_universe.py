"""Point-in-time observable universe, change detection, and research candidates.

This is a descriptive common layer.  It preserves upstream evidence maturity and
surfaces things to research; it never certifies an upstream value or emits an
investment recommendation, expected return, causal claim, or universal score.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Any, cast

from alpha_cycle.research_ledger_write_lock_v2_1 import (
    exclusive_research_ledger_write_lock,
)

SCHEMA_VERSION = 1
_SNAPSHOT_DIRECTORY = "observable_universe_v1/snapshots"
_MANIFEST_DIRECTORY = "observable_universe_v1/manifests"
_CURRENT_PATH = "observable_universe_v1/current.json"
_IDENTITY_PATH = "observable_universe_v1/universe.json"
_LOCK_WAIT_SECONDS = 30.0


class ObservableUniverseError(ValueError):
    """Raised when an observable-universe contract fails closed."""


class MemberKind(StrEnum):
    SECURITY = "security"
    ASSET = "asset"
    DOMAIN = "domain"


class EvidenceMaturity(StrEnum):
    UNAVAILABLE = "unavailable"
    CITED_CONTEXT = "cited_context"
    STRUCTURED_OBSERVATION = "structured_observation"
    REPLAYABLE_PROVIDER_EVIDENCE = "replayable_provider_evidence"
    INDEPENDENTLY_VALIDATED_AUTHORITY = "independently_validated_authority"


class ChangeState(StrEnum):
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    NEWLY_AVAILABLE = "newly_available"
    NEWLY_MISSING = "newly_missing"
    STALE = "stale"
    INCOMPARABLE = "incomparable"


class ResearchPriority(StrEnum):
    ROUTINE = "routine"
    ELEVATED = "elevated"
    URGENT = "urgent"


class ResearchModelStatus(StrEnum):
    ABSENT = "absent"
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SOURCE_BOUND = "source_bound"
    OPERATIONAL = "operational"
    CALIBRATING = "calibrating"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"


class AttemptStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class UniverseMember:
    member_id: str
    kind: MemberKind
    domain_id: str | None = None
    aliases: tuple[str, ...] = ()
    required_dimensions: tuple[str, ...] = ()
    available_dimensions: tuple[str, ...] = ()
    unavailable_dimensions: tuple[str, ...] = ()
    research_model_status: ResearchModelStatus = ResearchModelStatus.ABSENT

    def __post_init__(self) -> None:
        object.__setattr__(self, "aliases", tuple(sorted(self.aliases, key=_identity)))
        object.__setattr__(self, "required_dimensions", tuple(sorted(self.required_dimensions)))
        object.__setattr__(self, "available_dimensions", tuple(sorted(self.available_dimensions)))
        object.__setattr__(
            self, "unavailable_dimensions", tuple(sorted(self.unavailable_dimensions))
        )
        _text(self.member_id, "member_id")
        _optional_text(self.domain_id, "domain_id")
        _unique_text(self.aliases, "aliases", normalized=True)
        _unique_text(self.required_dimensions, "required_dimensions")
        _unique_text(self.available_dimensions, "available_dimensions")
        _unique_text(self.unavailable_dimensions, "unavailable_dimensions")
        if set(self.available_dimensions) & set(self.unavailable_dimensions):
            raise ObservableUniverseError("a dimension cannot be both available and unavailable")
        declared = set(self.available_dimensions) | set(self.unavailable_dimensions)
        if not set(self.required_dimensions) <= declared:
            raise ObservableUniverseError(
                "every required dimension must be explicitly available or unavailable"
            )
        if self.research_model_status in {
            ResearchModelStatus.OPERATIONAL,
            ResearchModelStatus.CALIBRATING,
        } and set(self.required_dimensions) & set(self.unavailable_dimensions):
            raise ObservableUniverseError(
                "an operational or calibrating model requires every required dimension "
                "to be available"
            )

    def payload(self) -> dict[str, object]:
        return {
            "member_id": self.member_id,
            "kind": self.kind.value,
            "domain_id": self.domain_id,
            "aliases": list(self.aliases),
            "required_dimensions": list(self.required_dimensions),
            "available_dimensions": list(self.available_dimensions),
            "unavailable_dimensions": list(self.unavailable_dimensions),
            "research_model_status": self.research_model_status.value,
        }


@dataclass(frozen=True)
class EvidenceReference:
    reference_id: str
    source: str
    available_at: datetime
    maturity: EvidenceMaturity
    semantic_authority: str

    def __post_init__(self) -> None:
        _text(self.reference_id, "reference_id")
        _text(self.source, "source")
        _aware(self.available_at, "available_at")
        _text(self.semantic_authority, "semantic_authority")
        if self.maturity is EvidenceMaturity.UNAVAILABLE:
            raise ObservableUniverseError("an evidence reference cannot itself be unavailable")

    def payload(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "source": self.source,
            "available_at": _utc(self.available_at).isoformat(),
            "maturity": self.maturity.value,
            "semantic_authority": self.semantic_authority,
        }


ObservationValue = float | int | str | bool | None


@dataclass(frozen=True)
class MeasuredObservation:
    member_id: str
    dimension_id: str
    metric_id: str
    value: ObservationValue
    unit: str
    basis: str
    window: str
    semantics: str
    observed_at: datetime
    available_at: datetime
    maturity: EvidenceMaturity
    evidence: tuple[EvidenceReference, ...] = ()
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.member_id, "member_id"),
            (self.dimension_id, "dimension_id"),
            (self.metric_id, "metric_id"),
            (self.unit, "unit"),
            (self.basis, "basis"),
            (self.window, "window"),
            (self.semantics, "semantics"),
        ):
            _text(value, field)
        _aware(self.observed_at, "observed_at")
        _aware(self.available_at, "available_at")
        if self.available_at < self.observed_at:
            raise ObservableUniverseError("available_at cannot precede observed_at")
        if type(self.value) not in (float, int, str, bool, type(None)):
            raise ObservableUniverseError("observation value must be a JSON scalar or null")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ObservableUniverseError("observation numeric values must be finite")
        if self.maturity is EvidenceMaturity.UNAVAILABLE:
            if self.value is not None or self.evidence:
                raise ObservableUniverseError(
                    "unavailable evidence must keep a null value and no evidence references"
                )
            _text(self.unavailable_reason, "unavailable_reason")
        else:
            if self.value is None or not self.evidence:
                raise ObservableUniverseError(
                    "available observations require a value and exact evidence references"
                )
            if self.unavailable_reason is not None:
                raise ObservableUniverseError(
                    "available observations cannot carry an unavailable reason"
                )
            if any(item.available_at > self.available_at for item in self.evidence):
                raise ObservableUniverseError(
                    "observation available_at cannot precede referenced evidence"
                )
            maturity_rank = {item: rank for rank, item in enumerate(EvidenceMaturity)}
            if any(
                maturity_rank[item.maturity] < maturity_rank[self.maturity]
                for item in self.evidence
            ):
                raise ObservableUniverseError(
                    "observation maturity cannot exceed its upstream evidence maturity"
                )
            if len({item.reference_id for item in self.evidence}) != len(self.evidence):
                raise ObservableUniverseError("evidence references cannot repeat")
            if tuple(item.reference_id for item in self.evidence) != tuple(
                sorted(item.reference_id for item in self.evidence)
            ):
                raise ObservableUniverseError(
                    "evidence references must use canonical reference_id order"
                )

    @property
    def observation_id(self) -> str:
        return _sha(self.payload_without_id())

    @property
    def slot(self) -> tuple[str, str]:
        return self.member_id, self.dimension_id

    def payload_without_id(self) -> dict[str, object]:
        return {
            "member_id": self.member_id,
            "dimension_id": self.dimension_id,
            "metric_id": self.metric_id,
            "value": self.value,
            "unit": self.unit,
            "basis": self.basis,
            "window": self.window,
            "semantics": self.semantics,
            "observed_at": _utc(self.observed_at).isoformat(),
            "available_at": _utc(self.available_at).isoformat(),
            "maturity": self.maturity.value,
            "evidence": [item.payload() for item in self.evidence],
            "unavailable_reason": self.unavailable_reason,
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "observation_id": self.observation_id}


@dataclass(frozen=True)
class ObservableUniverseSnapshot:
    universe_id: str
    version: str
    research_cutoff_at: datetime
    members: tuple[UniverseMember, ...]
    observations: tuple[MeasuredObservation, ...]
    source_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "members",
            tuple(sorted(self.members, key=lambda item: _identity(item.member_id))),
        )
        object.__setattr__(
            self,
            "observations",
            tuple(
                sorted(
                    self.observations,
                    key=lambda item: (_identity(item.member_id), item.dimension_id),
                )
            ),
        )
        object.__setattr__(self, "source_evidence_refs", tuple(sorted(self.source_evidence_refs)))
        _text(self.universe_id, "universe_id")
        _text(self.version, "version")
        _aware(self.research_cutoff_at, "research_cutoff_at")
        if not self.members:
            raise ObservableUniverseError("observable universe requires at least one member")
        _validate_members(self.members)
        _unique_text(self.source_evidence_refs, "source_evidence_refs")
        members_by_id = {item.member_id: item for item in self.members}
        slots: set[tuple[str, str]] = set()
        for observation in self.observations:
            member = members_by_id.get(observation.member_id)
            if member is None:
                raise ObservableUniverseError("observation is outside the defined universe")
            if observation.available_at > self.research_cutoff_at:
                raise ObservableUniverseError("future evidence exceeds the research cutoff")
            expected_dimensions = (
                member.unavailable_dimensions
                if observation.maturity is EvidenceMaturity.UNAVAILABLE
                else member.available_dimensions
            )
            if observation.dimension_id not in expected_dimensions:
                raise ObservableUniverseError(
                    "observation availability conflicts with its member dimension declaration"
                )
            if observation.slot in slots:
                raise ObservableUniverseError(
                    "one universe snapshot cannot contain ambiguous duplicate metric slots"
                )
            slots.add(observation.slot)
        available_slots = {
            item.slot
            for item in self.observations
            if item.maturity is not EvidenceMaturity.UNAVAILABLE
        }
        for member in self.members:
            if any(
                (member.member_id, dimension) not in available_slots
                for dimension in member.available_dimensions
            ):
                raise ObservableUniverseError(
                    "every declared available dimension requires an available observation"
                )
        declared_refs = {
            evidence.reference_id
            for observation in self.observations
            for evidence in observation.evidence
        }
        if not declared_refs <= set(self.source_evidence_refs):
            raise ObservableUniverseError(
                "snapshot source_evidence_refs must include every observation reference"
            )
        canonical_refs: dict[str, dict[str, object]] = {}
        for observation in self.observations:
            for evidence in observation.evidence:
                payload = evidence.payload()
                prior_payload = canonical_refs.setdefault(evidence.reference_id, payload)
                if prior_payload != payload:
                    raise ObservableUniverseError(
                        "one evidence reference_id cannot have conflicting definitions"
                    )

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "universe_id": self.universe_id,
            "version": self.version,
            "research_cutoff_at": _utc(self.research_cutoff_at).isoformat(),
            "members": [item.payload() for item in self.members],
            "observations": [item.payload() for item in self.observations],
            "source_evidence_refs": list(self.source_evidence_refs),
            "descriptive_research_state_only": True,
            "investment_authority": False,
            "decision_score_enabled": False,
            "causal_claim_enabled": False,
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "snapshot_id": self.snapshot_id}


@dataclass(frozen=True)
class ObservationChange:
    current_snapshot_id: str
    member_id: str
    dimension_id: str
    state: ChangeState
    evaluated_at: datetime
    prior_observation_id: str | None
    current_observation_id: str | None
    prior_value: ObservationValue
    current_value: ObservationValue
    delta: float | int | None
    reason: str
    prior_evidence_refs: tuple[str, ...]
    current_evidence_refs: tuple[str, ...]
    causal_claim: bool = False

    def __post_init__(self) -> None:
        _sha_text(self.current_snapshot_id, "current_snapshot_id")
        _text(self.member_id, "member_id")
        _text(self.dimension_id, "dimension_id")
        _aware(self.evaluated_at, "evaluated_at")
        _text(self.reason, "reason")
        _unique_text(self.prior_evidence_refs, "prior_evidence_refs")
        _unique_text(self.current_evidence_refs, "current_evidence_refs")
        if self.causal_claim:
            raise ObservableUniverseError("change detection cannot make a causal claim")

    @property
    def change_id(self) -> str:
        return _sha(self.payload_without_id())

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.prior_evidence_refs) | set(self.current_evidence_refs)))

    def payload_without_id(self) -> dict[str, object]:
        return {
            "current_snapshot_id": self.current_snapshot_id,
            "member_id": self.member_id,
            "dimension_id": self.dimension_id,
            "state": self.state.value,
            "evaluated_at": _utc(self.evaluated_at).isoformat(),
            "prior_observation_id": self.prior_observation_id,
            "current_observation_id": self.current_observation_id,
            "prior_value": self.prior_value,
            "current_value": self.current_value,
            "delta": self.delta,
            "reason": self.reason,
            "prior_evidence_refs": list(self.prior_evidence_refs),
            "current_evidence_refs": list(self.current_evidence_refs),
            "causal_claim": False,
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "change_id": self.change_id}


@dataclass(frozen=True)
class CandidateRule:
    rule_id: str
    dimension_id: str
    states: tuple[ChangeState, ...]
    priority: ResearchPriority
    reason: str
    minimum_absolute_delta: float | None = None

    def __post_init__(self) -> None:
        _text(self.rule_id, "rule_id")
        _text(self.dimension_id, "dimension_id")
        _text(self.reason, "reason")
        if not self.states or len(set(self.states)) != len(self.states):
            raise ObservableUniverseError("candidate rule states must be unique and non-empty")
        if self.minimum_absolute_delta is not None and (
            not math.isfinite(self.minimum_absolute_delta) or self.minimum_absolute_delta < 0
        ):
            raise ObservableUniverseError("minimum_absolute_delta must be finite and non-negative")


@dataclass(frozen=True)
class ResearchCandidate:
    current_snapshot_id: str
    member_id: str
    member_kind: MemberKind
    domain_id: str | None
    evaluated_at: datetime
    priority: ResearchPriority
    measured_reasons: tuple[str, ...]
    triggering_change_ids: tuple[str, ...]
    triggering_evidence_refs: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    blocked_evidence: tuple[str, ...]
    research_model_status: ResearchModelStatus
    candidate_semantics: str = "research_this"
    investment_authority: bool = False

    def __post_init__(self) -> None:
        _sha_text(self.current_snapshot_id, "current_snapshot_id")
        _text(self.member_id, "member_id")
        _optional_text(self.domain_id, "domain_id")
        _aware(self.evaluated_at, "evaluated_at")
        for values, field in (
            (self.measured_reasons, "measured_reasons"),
            (self.triggering_change_ids, "triggering_change_ids"),
            (self.triggering_evidence_refs, "triggering_evidence_refs"),
            (self.missing_dimensions, "missing_dimensions"),
            (self.blocked_evidence, "blocked_evidence"),
        ):
            _unique_text(values, field)
        if not self.measured_reasons or not self.triggering_change_ids:
            raise ObservableUniverseError("candidate requires measured triggering changes")
        if self.candidate_semantics != "research_this" or self.investment_authority:
            raise ObservableUniverseError("candidate must remain non-investment-authoritative")

    @property
    def candidate_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "current_snapshot_id": self.current_snapshot_id,
            "member_id": self.member_id,
            "member_kind": self.member_kind.value,
            "domain_id": self.domain_id,
            "evaluated_at": _utc(self.evaluated_at).isoformat(),
            "priority": self.priority.value,
            "measured_reasons": list(self.measured_reasons),
            "triggering_change_ids": list(self.triggering_change_ids),
            "triggering_evidence_refs": list(self.triggering_evidence_refs),
            "missing_dimensions": list(self.missing_dimensions),
            "blocked_evidence": list(self.blocked_evidence),
            "research_model_status": self.research_model_status.value,
            "candidate_semantics": "research_this",
            "investment_authority": False,
            "decision_score": None,
            "recommendation": None,
            "expected_return": None,
            "causal_claim": None,
        }


@dataclass(frozen=True)
class PlannerCandidateInput:
    candidate_id: str
    current_snapshot_id: str
    member_id: str
    member_kind: MemberKind
    domain_id: str | None
    priority: ResearchPriority
    evaluated_at: datetime
    triggering_change_ids: tuple[str, ...]
    measured_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    blocked_evidence: tuple[str, ...]
    research_model_status: ResearchModelStatus


@dataclass(frozen=True)
class CurrentUniverseState:
    status: AttemptStatus
    attempted_at: datetime
    attempt_id: str
    snapshot: ObservableUniverseSnapshot | None
    failure_code: str | None
    last_successful_cutoff_at: datetime | None
    last_successful_snapshot_id: str | None

    @property
    def ready(self) -> bool:
        return self.status is AttemptStatus.SUCCEEDED and self.snapshot is not None


def compare_universe_snapshots(
    prior: ObservableUniverseSnapshot,
    current: ObservableUniverseSnapshot,
    *,
    stale_after: timedelta | None = None,
) -> tuple[ObservationChange, ...]:
    """Compare semantically paired PIT slots without inferring causality."""

    if prior.universe_id != current.universe_id:
        raise ObservableUniverseError("cannot compare different universe identities")
    if prior.research_cutoff_at >= current.research_cutoff_at:
        raise ObservableUniverseError("current cutoff must be later than prior cutoff")
    if stale_after is not None and stale_after < timedelta(0):
        raise ObservableUniverseError("stale_after cannot be negative")
    prior_evidence = {
        evidence.reference_id: evidence.payload()
        for observation in prior.observations
        for evidence in observation.evidence
    }
    current_evidence = {
        evidence.reference_id: evidence.payload()
        for observation in current.observations
        for evidence in observation.evidence
    }
    if any(
        prior_evidence[reference_id] != current_evidence[reference_id]
        for reference_id in set(prior_evidence) & set(current_evidence)
    ):
        raise ObservableUniverseError(
            "one evidence reference_id cannot change definition across snapshots"
        )
    prior_by_slot = {
        (_identity(item.member_id), item.dimension_id): item for item in prior.observations
    }
    current_by_slot = {
        (_identity(item.member_id), item.dimension_id): item for item in current.observations
    }
    current_members = {_identity(item.member_id): item for item in current.members}
    comparable_slots = []
    for slot in sorted(set(prior_by_slot) | set(current_by_slot)):
        current_member = current_members.get(slot[0])
        current_declared_dimensions = (
            set(current_member.required_dimensions)
            | set(current_member.available_dimensions)
            | set(current_member.unavailable_dimensions)
            if current_member is not None
            else set()
        )
        if (
            slot in prior_by_slot
            and slot not in current_by_slot
            and current_member is not None
            and slot[1] not in current_declared_dimensions
        ):
            continue
        comparable_slots.append(slot)
    changes = [
        _compare_observations(
            prior_by_slot.get(slot),
            current_by_slot.get(slot),
            current_snapshot_id=current.snapshot_id,
            prior_cutoff_at=prior.research_cutoff_at,
            evaluated_at=current.research_cutoff_at,
            stale_after=stale_after,
        )
        for slot in comparable_slots
    ]
    prior_members = {_identity(item.member_id): item for item in prior.members}
    for member in current.members:
        normalized_member_id = _identity(member.member_id)
        prior_member = prior_members.get(normalized_member_id)
        prior_unavailable = (
            set(prior_member.unavailable_dimensions) if prior_member is not None else set()
        )
        for dimension_id in sorted(set(member.unavailable_dimensions) - prior_unavailable):
            slot = (normalized_member_id, dimension_id)
            if slot in prior_by_slot or slot in current_by_slot:
                continue
            changes.append(
                ObservationChange(
                    current_snapshot_id=current.snapshot_id,
                    member_id=member.member_id,
                    dimension_id=dimension_id,
                    state=ChangeState.NEWLY_MISSING,
                    evaluated_at=current.research_cutoff_at,
                    prior_observation_id=None,
                    current_observation_id=None,
                    prior_value=None,
                    current_value=None,
                    delta=None,
                    reason="dimension is newly declared unavailable",
                    prior_evidence_refs=(),
                    current_evidence_refs=(),
                )
            )
    return tuple(sorted(changes, key=lambda item: (item.member_id, item.dimension_id)))


def surface_research_candidates(
    snapshot: ObservableUniverseSnapshot,
    changes: tuple[ObservationChange, ...],
    rules: tuple[CandidateRule, ...],
    *,
    prior_snapshot: ObservableUniverseSnapshot,
    stale_after: timedelta | None = None,
) -> tuple[ResearchCandidate, ...]:
    """Apply explicit deterministic rules; no rule means no forced candidate."""

    if len({item.rule_id for item in rules}) != len(rules):
        raise ObservableUniverseError("candidate rule_id values cannot repeat")
    expected_changes = compare_universe_snapshots(prior_snapshot, snapshot, stale_after=stale_after)
    supplied_by_id = {item.change_id: item for item in changes}
    expected_by_id = {item.change_id: item for item in expected_changes}
    if len(supplied_by_id) != len(changes) or supplied_by_id != expected_by_id:
        raise ObservableUniverseError(
            "candidate changes must exactly match the bound prior/current snapshots"
        )
    member_by_id = {_identity(item.member_id): item for item in snapshot.members}
    current_observations_by_slot = {
        (_identity(item.member_id), item.dimension_id): item for item in snapshot.observations
    }
    hits: dict[str, list[tuple[CandidateRule, ObservationChange]]] = {}
    for change in changes:
        if change.current_snapshot_id != snapshot.snapshot_id:
            raise ObservableUniverseError(
                "candidate change does not bind to the exact current universe snapshot"
            )
        normalized_member_id = _identity(change.member_id)
        member = member_by_id.get(normalized_member_id)
        if member is None:
            # A prior-only member is an explicit reconstitution/removal change.  It
            # remains in the change history but cannot become a current candidate.
            continue
        if change.evaluated_at != snapshot.research_cutoff_at:
            raise ObservableUniverseError(
                "candidate change evaluation does not match the current universe cutoff"
            )
        current_observation = current_observations_by_slot.get(
            (normalized_member_id, change.dimension_id)
        )
        if change.current_observation_id is None:
            if current_observation is not None or change.current_evidence_refs:
                raise ObservableUniverseError(
                    "candidate change current lineage does not match its observation slot"
                )
        elif (
            current_observation is None
            or current_observation.observation_id != change.current_observation_id
        ):
            raise ObservableUniverseError(
                "candidate change does not bind to its current universe observation slot"
            )
        elif change.current_evidence_refs != tuple(
            sorted(item.reference_id for item in current_observation.evidence)
        ):
            raise ObservableUniverseError(
                "candidate change evidence does not bind to its current observation"
            )
        for rule in rules:
            if rule.dimension_id != change.dimension_id or change.state not in rule.states:
                continue
            if rule.minimum_absolute_delta is not None and (
                change.delta is None or abs(change.delta) < rule.minimum_absolute_delta
            ):
                continue
            hits.setdefault(member.member_id, []).append((rule, change))

    candidates: list[ResearchCandidate] = []
    priority_rank = {
        ResearchPriority.ROUTINE: 0,
        ResearchPriority.ELEVATED: 1,
        ResearchPriority.URGENT: 2,
    }
    observations_by_member: dict[str, list[MeasuredObservation]] = {}
    for observation in snapshot.observations:
        observations_by_member.setdefault(observation.member_id, []).append(observation)
    for member_id in sorted(hits):
        member = member_by_id[_identity(member_id)]
        selected = sorted(hits[member_id], key=lambda item: (item[0].rule_id, item[1].change_id))
        missing = tuple(
            sorted(
                set(member.unavailable_dimensions)
                | {
                    item.dimension_id
                    for item in observations_by_member.get(member_id, [])
                    if item.maturity is EvidenceMaturity.UNAVAILABLE
                }
            )
        )
        blocked = tuple(
            sorted(
                {
                    item.unavailable_reason
                    for item in observations_by_member.get(member_id, [])
                    if item.maturity is EvidenceMaturity.UNAVAILABLE
                    and item.unavailable_reason is not None
                }
            )
        )
        candidates.append(
            ResearchCandidate(
                current_snapshot_id=snapshot.snapshot_id,
                member_id=member_id,
                member_kind=member.kind,
                domain_id=member.domain_id,
                evaluated_at=snapshot.research_cutoff_at,
                priority=max(
                    (rule.priority for rule, _ in selected), key=priority_rank.__getitem__
                ),
                measured_reasons=tuple(
                    dict.fromkeys(f"{rule.reason}: {change.reason}" for rule, change in selected)
                ),
                triggering_change_ids=tuple(sorted({change.change_id for _, change in selected})),
                triggering_evidence_refs=tuple(
                    sorted({ref for _, change in selected for ref in change.evidence_refs})
                ),
                missing_dimensions=missing,
                blocked_evidence=blocked,
                research_model_status=member.research_model_status,
            )
        )
    return tuple(candidates)


def planner_input(candidate: ResearchCandidate) -> PlannerCandidateInput:
    return PlannerCandidateInput(
        candidate_id=candidate.candidate_id,
        current_snapshot_id=candidate.current_snapshot_id,
        member_id=candidate.member_id,
        member_kind=candidate.member_kind,
        domain_id=candidate.domain_id,
        priority=candidate.priority,
        evaluated_at=candidate.evaluated_at,
        triggering_change_ids=candidate.triggering_change_ids,
        measured_reasons=candidate.measured_reasons,
        evidence_refs=candidate.triggering_evidence_refs,
        missing_dimensions=candidate.missing_dimensions,
        blocked_evidence=candidate.blocked_evidence,
        research_model_status=candidate.research_model_status,
    )


def persist_successful_universe_attempt(
    snapshot: ObservableUniverseSnapshot,
    *,
    output_root: str | Path,
    attempted_at: datetime,
) -> Path:
    """Persist immutable payload+manifest and atomically select this successful attempt."""

    root = Path(output_root)
    attempted = _utc(attempted_at)
    if attempted < _utc(snapshot.research_cutoff_at):
        raise ObservableUniverseError(
            "successful publication attempt cannot precede the research cutoff"
        )
    snapshot_bytes = _encoded(snapshot.payload())
    snapshot_path = root / _SNAPSHOT_DIRECTORY / f"{snapshot.snapshot_id}.json"
    manifest_without_id = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_bytes_sha256": _digest(snapshot_bytes),
    }
    manifest_id = _sha(manifest_without_id)
    manifest = {**manifest_without_id, "manifest_id": manifest_id}
    pointer_without_id = {
        "schema_version": SCHEMA_VERSION,
        "status": AttemptStatus.SUCCEEDED.value,
        "attempted_at": attempted.isoformat(),
        "attempt_id": _sha(
            {
                "status": AttemptStatus.SUCCEEDED.value,
                "attempted_at": attempted.isoformat(),
                "snapshot_id": snapshot.snapshot_id,
                "manifest_id": manifest_id,
            }
        ),
        "snapshot_id": snapshot.snapshot_id,
        "manifest_id": manifest_id,
        "failure_code": None,
        "last_successful_cutoff_at": _utc(snapshot.research_cutoff_at).isoformat(),
        "last_successful_snapshot_id": snapshot.snapshot_id,
    }
    with _exclusive_universe_write_lock(root):
        _validate_pointer_advance(root, pointer_without_id)
        prior_current = load_current_universe_state(root)
        if (
            prior_current is not None
            and prior_current.last_successful_cutoff_at is not None
            and snapshot.research_cutoff_at < prior_current.last_successful_cutoff_at
        ):
            raise ObservableUniverseError(
                "successful publication cannot regress the current research cutoff"
            )
        _bind_universe_identity(root, snapshot.universe_id)
        _write_immutable(snapshot_path, snapshot_bytes)
        _write_immutable(
            root / _MANIFEST_DIRECTORY / f"{manifest_id}.json",
            _encoded(manifest),
        )
        _publish_pointer(root, pointer_without_id)
        return snapshot_path


def publish_failed_universe_attempt(
    *, output_root: str | Path, attempted_at: datetime, failure_code: str
) -> Path:
    """Publish a failed latest attempt so stale success cannot masquerade as current."""

    _text(failure_code, "failure_code")
    attempted = _utc(attempted_at)
    attempt_id = _sha(
        {
            "status": AttemptStatus.FAILED.value,
            "attempted_at": attempted.isoformat(),
            "failure_code": failure_code,
        }
    )
    root = Path(output_root)
    with _exclusive_universe_write_lock(root):
        prior_current = load_current_universe_state(root)
        pointer_without_id = {
            "schema_version": SCHEMA_VERSION,
            "status": AttemptStatus.FAILED.value,
            "attempted_at": attempted.isoformat(),
            "attempt_id": attempt_id,
            "snapshot_id": None,
            "manifest_id": None,
            "failure_code": failure_code,
            "last_successful_cutoff_at": (
                _utc(prior_current.last_successful_cutoff_at).isoformat()
                if prior_current is not None and prior_current.last_successful_cutoff_at is not None
                else None
            ),
            "last_successful_snapshot_id": (
                prior_current.last_successful_snapshot_id if prior_current is not None else None
            ),
        }
        _publish_pointer(root, pointer_without_id)
        return root / _CURRENT_PATH


def load_current_universe_state(output_root: str | Path) -> CurrentUniverseState | None:
    root = Path(output_root)
    pointer_path = root / _CURRENT_PATH
    if not os.path.lexists(pointer_path):
        return None
    if pointer_path.is_symlink() or not pointer_path.is_file():
        raise ObservableUniverseError("current pointer path must be a regular file")
    pointer = _load_json(pointer_path, "current pointer")
    expected = {
        "schema_version",
        "status",
        "attempted_at",
        "attempt_id",
        "snapshot_id",
        "manifest_id",
        "failure_code",
        "last_successful_cutoff_at",
        "last_successful_snapshot_id",
        "pointer_id",
    }
    _exact(pointer, expected, "current pointer")
    pointer_id = _required_text(pointer, "pointer_id")
    without_id = dict(pointer)
    del without_id["pointer_id"]
    if _sha(without_id) != pointer_id:
        raise ObservableUniverseError("current pointer content identity mismatch")
    if _required_int(pointer, "schema_version") != SCHEMA_VERSION:
        raise ObservableUniverseError("unsupported current pointer schema")
    status = _enum(AttemptStatus, pointer, "status")
    attempted_at = _datetime(_required_text(pointer, "attempted_at"), "attempted_at")
    attempt_id = _required_text(pointer, "attempt_id")
    failure_code = _nullable_text(pointer, "failure_code")
    last_cutoff_text = _nullable_text(pointer, "last_successful_cutoff_at")
    last_snapshot_id = _nullable_text(pointer, "last_successful_snapshot_id")
    if (last_cutoff_text is None) != (last_snapshot_id is None):
        raise ObservableUniverseError(
            "last successful cutoff and snapshot identity must be present together"
        )
    last_cutoff = (
        _datetime(last_cutoff_text, "last_successful_cutoff_at")
        if last_cutoff_text is not None
        else None
    )
    if last_snapshot_id is not None:
        _sha_text(last_snapshot_id, "last_successful_snapshot_id")
    if status is AttemptStatus.FAILED:
        if pointer["snapshot_id"] is not None or pointer["manifest_id"] is not None:
            raise ObservableUniverseError("failed pointer cannot select a snapshot")
        _text(failure_code, "failure_code")
        expected_attempt = _sha(
            {
                "status": status.value,
                "attempted_at": attempted_at.isoformat(),
                "failure_code": failure_code,
            }
        )
        if attempt_id != expected_attempt:
            raise ObservableUniverseError("failed attempt identity mismatch")
        if last_cutoff is not None and last_snapshot_id is not None:
            if attempted_at < last_cutoff:
                raise ObservableUniverseError("failed attempt predates its last successful cutoff")
            last_snapshot = load_universe_snapshot(
                root / _SNAPSHOT_DIRECTORY / f"{last_snapshot_id}.json"
            )
            if last_snapshot.research_cutoff_at != last_cutoff:
                raise ObservableUniverseError(
                    "failed pointer success watermark cutoff does not match its snapshot"
                )
            if _load_universe_identity(root) != last_snapshot.universe_id:
                raise ObservableUniverseError(
                    "failed pointer success watermark has a different universe identity"
                )
        return CurrentUniverseState(
            status,
            attempted_at,
            attempt_id,
            None,
            failure_code,
            last_cutoff,
            last_snapshot_id,
        )

    if failure_code is not None:
        raise ObservableUniverseError("successful pointer cannot contain failure_code")
    snapshot_id = _required_text(pointer, "snapshot_id")
    manifest_id = _required_text(pointer, "manifest_id")
    snapshot_path = root / _SNAPSHOT_DIRECTORY / f"{snapshot_id}.json"
    manifest_path = root / _MANIFEST_DIRECTORY / f"{manifest_id}.json"
    manifest = _load_json(manifest_path, "manifest")
    _exact(
        manifest,
        {"schema_version", "snapshot_id", "snapshot_bytes_sha256", "manifest_id"},
        "manifest",
    )
    manifest_without_id = dict(manifest)
    del manifest_without_id["manifest_id"]
    if _required_int(manifest, "schema_version") != SCHEMA_VERSION:
        raise ObservableUniverseError("unsupported manifest schema")
    if _sha(manifest_without_id) != manifest_id or manifest_path.stem != manifest_id:
        raise ObservableUniverseError("manifest content identity mismatch")
    if manifest.get("snapshot_id") != snapshot_id:
        raise ObservableUniverseError("manifest selects a different snapshot")
    try:
        snapshot_bytes = snapshot_path.read_bytes()
    except OSError as exc:
        raise ObservableUniverseError("cannot read selected snapshot") from exc
    if _digest(snapshot_bytes) != manifest.get("snapshot_bytes_sha256"):
        raise ObservableUniverseError("persisted snapshot bytes do not match manifest")
    snapshot = load_universe_snapshot(snapshot_path)
    if last_cutoff != snapshot.research_cutoff_at or last_snapshot_id != snapshot.snapshot_id:
        raise ObservableUniverseError(
            "successful pointer must preserve its selected snapshot as the high-water mark"
        )
    if _load_universe_identity(root) != snapshot.universe_id:
        raise ObservableUniverseError(
            "selected snapshot does not match the bound universe identity"
        )
    if attempted_at < _utc(snapshot.research_cutoff_at):
        raise ObservableUniverseError(
            "successful current attempt predates the selected snapshot research cutoff"
        )
    expected_attempt = _sha(
        {
            "status": status.value,
            "attempted_at": attempted_at.isoformat(),
            "snapshot_id": snapshot_id,
            "manifest_id": manifest_id,
        }
    )
    if attempt_id != expected_attempt:
        raise ObservableUniverseError("successful attempt identity mismatch")
    return CurrentUniverseState(
        status,
        attempted_at,
        attempt_id,
        snapshot,
        None,
        last_cutoff,
        last_snapshot_id,
    )


def load_universe_snapshot(path: str | Path) -> ObservableUniverseSnapshot:
    source = Path(path)
    payload = _load_json(source, "snapshot")
    declared = _required_text(payload, "snapshot_id")
    without_id = dict(payload)
    del without_id["snapshot_id"]
    if source.stem != declared or _sha(without_id) != declared:
        raise ObservableUniverseError("snapshot content identity mismatch")
    if _required_int(payload, "schema_version") != SCHEMA_VERSION:
        raise ObservableUniverseError("unsupported observable-universe schema")
    _expect_bool(payload, "descriptive_research_state_only", True)
    _expect_bool(payload, "investment_authority", False)
    _expect_bool(payload, "decision_score_enabled", False)
    _expect_bool(payload, "causal_claim_enabled", False)
    members = tuple(_parse_member(item) for item in _required_list(payload, "members"))
    observations = tuple(
        _parse_observation(item) for item in _required_list(payload, "observations")
    )
    value = ObservableUniverseSnapshot(
        universe_id=_required_text(payload, "universe_id"),
        version=_required_text(payload, "version"),
        research_cutoff_at=_datetime(
            _required_text(payload, "research_cutoff_at"), "research_cutoff_at"
        ),
        members=members,
        observations=observations,
        source_evidence_refs=_text_tuple(payload, "source_evidence_refs"),
    )
    if value.snapshot_id != declared:
        raise ObservableUniverseError("typed snapshot reconstruction changed identity")
    return value


def _compare_observations(
    prior: MeasuredObservation | None,
    current: MeasuredObservation | None,
    *,
    current_snapshot_id: str,
    prior_cutoff_at: datetime,
    evaluated_at: datetime,
    stale_after: timedelta | None,
) -> ObservationChange:
    template = current or prior
    assert template is not None
    prior_refs = tuple(sorted(item.reference_id for item in prior.evidence)) if prior else ()
    current_refs = tuple(sorted(item.reference_id for item in current.evidence)) if current else ()

    def make(state: ChangeState, delta: float | int | None, reason: str) -> ObservationChange:
        return ObservationChange(
            current_snapshot_id=current_snapshot_id,
            member_id=template.member_id,
            dimension_id=template.dimension_id,
            state=state,
            evaluated_at=evaluated_at,
            prior_observation_id=prior.observation_id if prior else None,
            current_observation_id=current.observation_id if current else None,
            prior_value=prior.value if prior else None,
            current_value=current.value if current else None,
            delta=delta,
            reason=reason,
            prior_evidence_refs=prior_refs,
            current_evidence_refs=current_refs,
        )

    current_is_stale = (
        current is not None
        and current.maturity is not EvidenceMaturity.UNAVAILABLE
        and stale_after is not None
        and evaluated_at - current.available_at > stale_after
    )
    if (
        current is not None
        and current.maturity is not EvidenceMaturity.UNAVAILABLE
        and current.available_at <= prior_cutoff_at
        and (prior is None or prior.maturity is EvidenceMaturity.UNAVAILABLE)
    ):
        return make(
            ChangeState.INCOMPARABLE,
            None,
            "current evidence was already knowable at the prior research cutoff",
        )
    if prior is None or prior.maturity is EvidenceMaturity.UNAVAILABLE:
        if current is not None and current.maturity is not EvidenceMaturity.UNAVAILABLE:
            if current_is_stale:
                return make(
                    ChangeState.STALE,
                    None,
                    "newly available evidence exceeds the configured staleness window",
                )
            return make(ChangeState.NEWLY_AVAILABLE, None, "evidence became available")
    if current is None or current.maturity is EvidenceMaturity.UNAVAILABLE:
        if prior is not None and prior.maturity is not EvidenceMaturity.UNAVAILABLE:
            return make(
                ChangeState.NEWLY_MISSING,
                None,
                "previously available evidence is now missing",
            )
        if prior is None:
            return make(ChangeState.NEWLY_MISSING, None, "dimension is newly unavailable")
        return make(ChangeState.UNCHANGED, None, "evidence remains explicitly unavailable")
    assert prior is not None and current is not None
    if current.available_at < prior.available_at or current.observed_at < prior.observed_at:
        return make(
            ChangeState.INCOMPARABLE,
            None,
            "current observation chronology regresses the prior observation",
        )
    if current.available_at <= prior_cutoff_at and (
        current.value != prior.value or type(current.value) is not type(prior.value)
    ):
        return make(
            ChangeState.INCOMPARABLE,
            None,
            "current evidence was already knowable at the prior research cutoff",
        )
    differences = [
        name
        for name in ("metric_id", "unit", "basis", "window", "semantics")
        if getattr(prior, name) != getattr(current, name)
    ]
    if differences:
        return make(
            ChangeState.INCOMPARABLE,
            None,
            "comparison identity differs: " + ", ".join(differences),
        )
    if current.maturity is not prior.maturity:
        return make(
            ChangeState.INCOMPARABLE,
            None,
            "current evidence maturity differs from the prior observation",
        )
    prior_authority = tuple(
        sorted(
            (item.source, item.semantic_authority, item.maturity.value) for item in prior.evidence
        )
    )
    current_authority = tuple(
        sorted(
            (item.source, item.semantic_authority, item.maturity.value) for item in current.evidence
        )
    )
    if current_authority != prior_authority:
        return make(
            ChangeState.INCOMPARABLE,
            None,
            "current upstream evidence authority or maturity differs from the prior observation",
        )
    if current_is_stale:
        return make(
            ChangeState.STALE,
            None,
            "current evidence exceeds the configured staleness window",
        )
    if type(prior.value) in (int, float) and type(current.value) in (int, float):
        exact_delta = Fraction(cast(float | int, current.value)) - Fraction(
            cast(float | int, prior.value)
        )
        try:
            delta: float | int = (
                exact_delta.numerator if exact_delta.denominator == 1 else float(exact_delta)
            )
        except OverflowError:
            return make(ChangeState.INCOMPARABLE, None, "numeric delta exceeds finite range")
        if isinstance(delta, float) and not math.isfinite(delta):
            return make(ChangeState.INCOMPARABLE, None, "numeric delta exceeds finite range")
        state = ChangeState.UNCHANGED if exact_delta == 0 else ChangeState.CHANGED
        delta_text = str(delta) if isinstance(delta, int) else f"{delta:g}"
        reason = (
            f"{current.metric_id} changed by {delta_text} {current.unit}"
            if exact_delta
            else f"{current.metric_id} is unchanged"
        )
        return make(state, delta, reason)
    if type(prior.value) is not type(current.value):
        return make(
            ChangeState.INCOMPARABLE,
            None,
            "observation scalar encoding changed between snapshots",
        )
    equal = prior.value == current.value
    return make(
        ChangeState.UNCHANGED if equal else ChangeState.CHANGED,
        None,
        f"{current.metric_id} is {'unchanged' if equal else 'changed'}",
    )


def _validate_members(members: tuple[UniverseMember, ...]) -> None:
    ids: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for member in members:
        normalized_id = _identity(member.member_id)
        if normalized_id in ids:
            raise ObservableUniverseError("duplicate or ambiguous member identity")
        ids[normalized_id] = member.member_id
    for member in members:
        for alias in member.aliases:
            normalized = _identity(alias)
            owner = aliases.get(normalized)
            if owner is not None and owner != member.member_id:
                raise ObservableUniverseError("ambiguous alias maps to multiple members")
            if normalized in ids and ids[normalized] != member.member_id:
                raise ObservableUniverseError("alias collides with another member identity")
            aliases[normalized] = member.member_id


def _parse_member(raw: object) -> UniverseMember:
    value = _object(raw, "member")
    return UniverseMember(
        member_id=_required_text(value, "member_id"),
        kind=_enum(MemberKind, value, "kind"),
        domain_id=_nullable_text(value, "domain_id"),
        aliases=_text_tuple(value, "aliases"),
        required_dimensions=_text_tuple(value, "required_dimensions"),
        available_dimensions=_text_tuple(value, "available_dimensions"),
        unavailable_dimensions=_text_tuple(value, "unavailable_dimensions"),
        research_model_status=_enum(ResearchModelStatus, value, "research_model_status"),
    )


def _parse_observation(raw: object) -> MeasuredObservation:
    value = _object(raw, "observation")
    evidence = tuple(_parse_evidence(item) for item in _required_list(value, "evidence"))
    result = MeasuredObservation(
        member_id=_required_text(value, "member_id"),
        dimension_id=_required_text(value, "dimension_id"),
        metric_id=_required_text(value, "metric_id"),
        value=_observation_value(value.get("value")),
        unit=_required_text(value, "unit"),
        basis=_required_text(value, "basis"),
        window=_required_text(value, "window"),
        semantics=_required_text(value, "semantics"),
        observed_at=_datetime(_required_text(value, "observed_at"), "observed_at"),
        available_at=_datetime(_required_text(value, "available_at"), "available_at"),
        maturity=_enum(EvidenceMaturity, value, "maturity"),
        evidence=evidence,
        unavailable_reason=_nullable_text(value, "unavailable_reason"),
    )
    if result.observation_id != _required_text(value, "observation_id"):
        raise ObservableUniverseError("observation identity mismatch")
    return result


def _parse_evidence(raw: object) -> EvidenceReference:
    value = _object(raw, "evidence")
    return EvidenceReference(
        reference_id=_required_text(value, "reference_id"),
        source=_required_text(value, "source"),
        available_at=_datetime(_required_text(value, "available_at"), "available_at"),
        maturity=_enum(EvidenceMaturity, value, "maturity"),
        semantic_authority=_required_text(value, "semantic_authority"),
    )


@contextmanager
def _exclusive_universe_write_lock(root: Path) -> Iterator[None]:
    """Wait for the repository's trusted cross-process lock, then hold it through commit."""

    _mkdir_durable(root)
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        lock = exclusive_research_ledger_write_lock(root)
        try:
            lock.__enter__()
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ObservableUniverseError(
                    "timed out waiting for observable-universe publication lock"
                ) from exc
            time.sleep(0.01)
            continue
        except RuntimeError as exc:
            # The shared contextmanager's fail-closed acquisition path currently
            # surfaces an O_EXCL collision as contextlib's no-yield RuntimeError.
            if str(exc) != "generator didn't yield":
                raise
            if time.monotonic() >= deadline:
                raise ObservableUniverseError(
                    "timed out waiting for observable-universe publication lock"
                ) from exc
            time.sleep(0.01)
            continue
        try:
            yield
        finally:
            lock.__exit__(None, None, None)
        return


def _publish_pointer(root: Path, without_id: dict[str, object]) -> None:
    path = root / _CURRENT_PATH
    _validate_pointer_advance(root, without_id)
    pointer = {**without_id, "pointer_id": _sha(without_id)}
    _atomic_replace(path, _encoded(pointer))


def _validate_pointer_advance(root: Path, without_id: dict[str, object]) -> None:
    if not os.path.lexists(root / _CURRENT_PATH):
        return
    prior = load_current_universe_state(root)
    assert prior is not None
    next_at = _datetime(cast(str, without_id["attempted_at"]), "attempted_at")
    if next_at < prior.attempted_at:
        raise ObservableUniverseError("current attempt time cannot move backward")
    if next_at == prior.attempted_at and prior.attempt_id != without_id["attempt_id"]:
        raise ObservableUniverseError("one attempt time cannot identify different attempts")


def _bind_universe_identity(root: Path, universe_id: str) -> None:
    path = root / _IDENTITY_PATH
    if path.exists():
        if _load_universe_identity(root) != universe_id:
            raise ObservableUniverseError(
                "observable-universe store cannot switch universe identity"
            )
        return
    without_id = {"schema_version": SCHEMA_VERSION, "universe_id": universe_id}
    _write_immutable(path, _encoded({**without_id, "identity_id": _sha(without_id)}))


def _load_universe_identity(root: Path) -> str:
    value = _load_json(root / _IDENTITY_PATH, "universe identity")
    _exact(value, {"schema_version", "universe_id", "identity_id"}, "universe identity")
    if _required_int(value, "schema_version") != SCHEMA_VERSION:
        raise ObservableUniverseError("unsupported universe identity schema")
    identity_id = _required_text(value, "identity_id")
    without_id = dict(value)
    del without_id["identity_id"]
    if _sha(without_id) != identity_id:
        raise ObservableUniverseError("universe identity content mismatch")
    return _required_text(value, "universe_id")


def _write_immutable(path: Path, content: bytes) -> None:
    _mkdir_durable(path.parent)
    if path.is_symlink():
        raise ObservableUniverseError("immutable artifact path cannot be a symlink")
    if path.exists():
        if not path.is_file():
            raise ObservableUniverseError("immutable artifact path must be a regular file")
        if path.read_bytes() != content:
            raise ObservableUniverseError(
                "content-addressed artifact conflicts with existing bytes"
            )
        _fsync_directory(path.parent)
        return
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            _fsync_directory(path.parent)
        except FileExistsError as exc:
            if path.read_bytes() != content:
                raise ObservableUniverseError("concurrent immutable publication conflict") from exc
            _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_replace(path: Path, content: bytes) -> None:
    _mkdir_durable(path.parent)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_durable(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise ObservableUniverseError("publication directory path is not a directory")
        return
    _mkdir_durable(path.parent)
    try:
        path.mkdir()
    except FileExistsError:
        if path.is_symlink() or not path.is_dir():
            raise ObservableUniverseError("publication directory path is not a directory") from None
    else:
        _fsync_directory(path.parent)


def _load_json(path: Path, field: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObservableUniverseError(f"cannot read {field}") from exc
    return _object(raw, field)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ObservableUniverseError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ObservableUniverseError(f"{field} must be a JSON object")
    return cast(dict[str, Any], value)


def _required_list(value: dict[str, Any], field: str) -> list[object]:
    result = value.get(field)
    if not isinstance(result, list):
        raise ObservableUniverseError(f"{field} must be an array")
    return cast(list[object], result)


def _text_tuple(value: dict[str, Any], field: str) -> tuple[str, ...]:
    return tuple(_required_text({field: item}, field) for item in _required_list(value, field))


def _required_text(value: dict[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise ObservableUniverseError(f"{field} must be non-empty text")
    return result


def _nullable_text(value: dict[str, Any], field: str) -> str | None:
    result = value.get(field)
    if result is None:
        return None
    if not isinstance(result, str) or not result.strip():
        raise ObservableUniverseError(f"{field} must be null or non-empty text")
    return result


def _required_int(value: dict[str, Any], field: str) -> int:
    result = value.get(field)
    if type(result) is not int:
        raise ObservableUniverseError(f"{field} must be an integer")
    return result


def _expect_bool(value: dict[str, Any], field: str, expected: bool) -> None:
    if type(value.get(field)) is not bool or value[field] is not expected:
        raise ObservableUniverseError(f"{field} changed its canonical safety value")


def _exact(value: dict[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ObservableUniverseError(f"{label} fields differ from canonical schema")


def _datetime(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ObservableUniverseError(f"{field} must be an ISO datetime") from exc
    _aware(result, field)
    return result


def _enum[EnumT: StrEnum](enum_type: type[EnumT], value: dict[str, Any], field: str) -> EnumT:
    raw = _required_text(value, field)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise ObservableUniverseError(f"unsupported {field}: {raw}") from exc


def _observation_value(value: object) -> ObservationValue:
    if value is None or type(value) in (float, int, str, bool):
        return cast(ObservationValue, value)
    raise ObservableUniverseError("observation value must be a JSON scalar or null")


def _text(value: str | None, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ObservableUniverseError(f"{field} must be non-empty text")


def _sha_text(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ObservableUniverseError(f"{field} must be a lowercase SHA-256")


def _optional_text(value: str | None, field: str) -> None:
    if value is not None:
        _text(value, field)


def _unique_text(values: tuple[str, ...], field: str, *, normalized: bool = False) -> None:
    for value in values:
        _text(value, field)
    comparable = tuple(_identity(item) if normalized else item for item in values)
    if len(set(comparable)) != len(comparable):
        raise ObservableUniverseError(f"{field} cannot contain duplicates")


def _aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ObservableUniverseError(f"{field} must be timezone-aware")


def _utc(value: datetime) -> datetime:
    _aware(value, "datetime")
    return value.astimezone(UTC)


def _identity(value: str) -> str:
    return value.strip().casefold()


def _encoded(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


__all__ = [
    "AttemptStatus",
    "CandidateRule",
    "ChangeState",
    "CurrentUniverseState",
    "EvidenceMaturity",
    "EvidenceReference",
    "MeasuredObservation",
    "MemberKind",
    "ObservableUniverseError",
    "ObservableUniverseSnapshot",
    "ObservationChange",
    "PlannerCandidateInput",
    "ResearchCandidate",
    "ResearchModelStatus",
    "ResearchPriority",
    "UniverseMember",
    "compare_universe_snapshots",
    "load_current_universe_state",
    "load_universe_snapshot",
    "persist_successful_universe_attempt",
    "planner_input",
    "publish_failed_universe_attempt",
    "surface_research_candidates",
]
