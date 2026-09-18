"""Immutable decision memory and authenticated outcome learning for Product R1-E.

This module only links already authenticated upstream snapshots. It cannot
certify a source from an ID string and it emits prospective model proposals;
historical decisions, forecasts, packs, and outcomes remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from alpha_cycle.intelligence.research_model_runtime_v1 import (
    KnowledgePack,
    ModelRevisionProposal,
    propose_pack_revision,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DecisionAction(StrEnum):
    OBSERVE = "observe"
    BUY = "buy"
    HOLD = "hold"
    ADD = "add"
    REDUCE = "reduce"
    EXIT = "exit"


class ErrorDomain(StrEnum):
    DEMAND = "demand"
    SUPPLY = "supply"
    PRICING = "pricing"
    TRANSMISSION = "transmission"
    EARNINGS = "earnings"
    CATALYST_TIMING = "catalyst_timing"
    EXPECTATION_VALUATION = "expectation_valuation"
    MISSING_VARIABLE = "missing_variable"
    MODEL_INSUFFICIENCY = "model_insufficiency"


@dataclass(frozen=True)
class DecisionMemory:
    decision_id: str
    candidate_id: str
    current_snapshot_id: str
    research_package_id: str
    pack_content_id: str | None
    action: DecisionAction
    thesis_state: str
    rationale: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    horizon: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        _sha(self.decision_id, "decision_id")
        _sha(self.candidate_id, "candidate_id")
        _sha(self.current_snapshot_id, "current_snapshot_id")
        _sha(self.research_package_id, "research_package_id")
        if self.pack_content_id is not None:
            _sha(self.pack_content_id, "pack_content_id")
        _text(self.thesis_state, "thesis_state")
        _text(self.horizon, "horizon")
        _aware(self.recorded_at)
        if not self.rationale:
            raise ValueError("decision memory requires rationale")
        if any(not value.strip() for value in (*self.rationale, *self.invalidation_conditions)):
            raise ValueError("decision text cannot be empty")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "decision_id": self.decision_id,
            "candidate_id": self.candidate_id,
            "current_snapshot_id": self.current_snapshot_id,
            "research_package_id": self.research_package_id,
            "pack_content_id": self.pack_content_id,
            "action": self.action.value,
            "thesis_state": self.thesis_state,
            "rationale": list(self.rationale),
            "invalidation_conditions": list(self.invalidation_conditions),
            "horizon": self.horizon,
            "recorded_at": self.recorded_at.astimezone(UTC).isoformat(),
        }


@dataclass(frozen=True)
class AuthenticatedOutcomeLink:
    registration_snapshot_id: str
    outcome_snapshot_id: str
    evaluation_snapshot_id: str
    target_key: str
    source_evidence_ids: tuple[str, ...]
    authenticated: bool
    observed_at: datetime

    def __post_init__(self) -> None:
        for field, value in (
            ("registration_snapshot_id", self.registration_snapshot_id),
            ("outcome_snapshot_id", self.outcome_snapshot_id),
            ("evaluation_snapshot_id", self.evaluation_snapshot_id),
        ):
            _sha(value, field)
        _text(self.target_key, "target_key")
        if not self.source_evidence_ids or any(
            not _SHA256.fullmatch(value) for value in self.source_evidence_ids
        ):
            raise ValueError("authenticated outcome requires SHA-256 source evidence IDs")
        if not self.authenticated:
            raise ValueError("outcome learning requires an authenticated outcome")
        _aware(self.observed_at)

    def payload(self) -> dict[str, object]:
        return {
            "registration_snapshot_id": self.registration_snapshot_id,
            "outcome_snapshot_id": self.outcome_snapshot_id,
            "evaluation_snapshot_id": self.evaluation_snapshot_id,
            "target_key": self.target_key,
            "source_evidence_ids": list(self.source_evidence_ids),
            "authenticated": self.authenticated,
            "observed_at": self.observed_at.astimezone(UTC).isoformat(),
        }


@dataclass(frozen=True)
class ErrorContribution:
    domain: ErrorDomain
    status: str
    explanation: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.status, "error status")
        _text(self.explanation, "error explanation")
        if any(not _SHA256.fullmatch(value) for value in self.evidence_refs):
            raise ValueError("error evidence references must be SHA-256")

    def payload(self) -> dict[str, object]:
        return {
            "domain": self.domain.value,
            "status": self.status,
            "explanation": self.explanation,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class OutcomeLearningRecord:
    record_id: str
    decision: DecisionMemory | None
    outcome: AuthenticatedOutcomeLink
    errors: tuple[ErrorContribution, ...]
    revision_proposal: ModelRevisionProposal | None

    def __post_init__(self) -> None:
        _sha(self.record_id, "record_id")
        if not self.errors:
            raise ValueError("outcome learning requires explicit error decomposition")
        if (
            self.decision is not None
            and self.decision.research_package_id != self.outcome.registration_snapshot_id
        ):
            raise ValueError("decision package must bind the forecast registration snapshot")
        if (
            self.revision_proposal is not None
            and not self.revision_proposal.triggering_evidence_refs
        ):
            raise ValueError("revision proposal requires outcome evidence refs")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "record_id": self.record_id,
            "decision": None if self.decision is None else self.decision.payload(),
            "outcome": self.outcome.payload(),
            "errors": [item.payload() for item in self.errors],
            "revision_proposal": None
            if self.revision_proposal is None
            else self.revision_proposal.payload(),
        }


def build_outcome_learning_record(
    *,
    outcome: AuthenticatedOutcomeLink,
    errors: tuple[ErrorContribution, ...],
    decision: DecisionMemory | None = None,
    revision_parent: KnowledgePack | None = None,
    proposed_version: str | None = None,
) -> OutcomeLearningRecord:
    if revision_parent is None and proposed_version is not None:
        raise ValueError("proposed version requires a revision parent")
    proposal = None
    if revision_parent is not None:
        if not proposed_version or not proposed_version.strip():
            raise ValueError("revision parent requires proposed version")
        proposal = propose_pack_revision(
            revision_parent,
            proposal_id=_digest(
                {"outcome": outcome.payload(), "errors": [item.payload() for item in errors]}
            ),
            proposed_version=proposed_version,
            proposed_change="Revise drivers or transmission after authenticated outcome analysis",
            reason="; ".join(item.explanation for item in errors),
            triggering_evidence_refs=outcome.source_evidence_ids,
            affected_driver_ids=tuple(item.domain.value for item in errors),
            expected_improvement="Improve prospective calibration after review",
            risks=(
                "Observed outcome is one learning sample; causal attribution remains provisional",
            ),
            effective_date=outcome.observed_at.astimezone(UTC).date().isoformat(),
        )
    record_id = _digest(
        {
            "decision": None if decision is None else decision.payload(),
            "outcome": outcome.payload(),
            "errors": [item.payload() for item in errors],
            "proposal": None if proposal is None else proposal.payload(),
        }
    )
    return OutcomeLearningRecord(record_id, decision, outcome, errors, proposal)


def _sha(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 identity")


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
