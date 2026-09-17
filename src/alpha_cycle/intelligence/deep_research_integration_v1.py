"""Evidence-only R1-C deep-research package assembled from an R1-B plan.

The package joins transmission, expectations, catalyst, and technical/flow
evidence while retaining point-in-time lineage.  It intentionally has no
score, recommendation, or authority-promotion field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from alpha_cycle.intelligence.observable_universe import EvidenceMaturity
from alpha_cycle.intelligence.research_model_runtime_v1 import ResearchPlan


class EvidenceState(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    UNRESOLVED = "unresolved"
    MISSING_CRITICAL = "missing_critical"
    STALE = "stale"
    MEASURED_NON_DIRECTIONAL = "measured_non_directional"
    NON_AUTHORITATIVE = "non_authoritative"


@dataclass(frozen=True)
class TransmissionObservation:
    observation_id: str
    driver_id: str
    company_id: str
    metric: str
    observation: str
    state: EvidenceState
    maturity: EvidenceMaturity
    evidence_refs: tuple[str, ...]
    cutoff: str
    caveats: tuple[str, ...] = ()
    horizons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _cutoff(self.cutoff)
        if not isinstance(self.state, EvidenceState) or not isinstance(
            self.maturity, EvidenceMaturity
        ):
            raise ValueError("observation requires typed state and maturity")
        if len(set(self.horizons)) != len(self.horizons) or set(self.horizons) - {
            "3m",
            "6m",
            "12m",
        }:
            raise ValueError("invalid observation horizons")
        for name, value in (
            ("observation_id", self.observation_id),
            ("driver_id", self.driver_id),
            ("company_id", self.company_id),
            ("metric", self.metric),
            ("observation", self.observation),
            ("cutoff", self.cutoff),
        ):
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not self.evidence_refs and self.state is not EvidenceState.MISSING_CRITICAL:
            raise ValueError("non-missing transmission evidence requires source references")
        if any(not ref.strip() for ref in self.evidence_refs):
            raise ValueError("source references must be non-empty")
        if self.maturity is EvidenceMaturity.UNAVAILABLE and self.state in {
            EvidenceState.SUPPORTING,
            EvidenceState.CONTRADICTING,
        }:
            raise ValueError("unavailable evidence cannot support or contradict a thesis")

    def payload(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "driver_id": self.driver_id,
            "company_id": self.company_id,
            "metric": self.metric,
            "observation": self.observation,
            "state": self.state.value,
            "maturity": self.maturity.value,
            "evidence_refs": list(self.evidence_refs),
            "cutoff": self.cutoff,
            "caveats": list(self.caveats),
            "horizons": list(self.horizons),
        }


@dataclass(frozen=True)
class HorizonView:
    horizon: str
    supporting_observation_ids: tuple[str, ...] = ()
    contradicting_observation_ids: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    catalyst_ids: tuple[str, ...] = ()
    status: str = "evidence_incomplete"

    def payload(self) -> dict[str, object]:
        return {
            "horizon": self.horizon,
            "supporting_observation_ids": list(self.supporting_observation_ids),
            "contradicting_observation_ids": list(self.contradicting_observation_ids),
            "unresolved_questions": list(self.unresolved_questions),
            "catalyst_ids": list(self.catalyst_ids),
            "status": self.status,
        }


@dataclass(frozen=True)
class DeepResearchPackage:
    candidate_id: str
    current_snapshot_id: str
    plan_content_id: str | None
    cutoff: str
    observations: tuple[TransmissionObservation, ...]
    expectation_status: str
    expectation_evidence_refs: tuple[str, ...]
    catalyst_ids: tuple[str, ...]
    technical_flow_status: str
    technical_flow_evidence_refs: tuple[str, ...]
    horizons: tuple[HorizonView, ...]
    content_id: str = ""

    def __post_init__(self) -> None:
        cutoff = _cutoff(self.cutoff)
        for status, refs in (
            (self.expectation_status, self.expectation_evidence_refs),
            (self.technical_flow_status, self.technical_flow_evidence_refs),
        ):
            if status not in {"unavailable", "cited_context"}:
                raise ValueError("unvalidated references cannot establish certified status")
            if status == "cited_context" and not refs:
                raise ValueError("cited context requires evidence references")
            if any(not ref.strip() for ref in refs):
                raise ValueError("evidence references must be non-empty")
        if any(_cutoff(item.cutoff) > cutoff for item in self.observations):
            raise ValueError("observation cutoff is after package cutoff")
        if len({item.observation_id for item in self.observations}) != len(self.observations):
            raise ValueError("duplicate transmission observation IDs")
        if len(self.horizons) != 3 or {item.horizon for item in self.horizons} != {
            "3m",
            "6m",
            "12m",
        }:
            raise ValueError("deep research package requires 3m, 6m, and 12m views")
        by_id = {item.observation_id: item for item in self.observations}
        for view in self.horizons:
            for ids, state in (
                (view.supporting_observation_ids, EvidenceState.SUPPORTING),
                (view.contradicting_observation_ids, EvidenceState.CONTRADICTING),
            ):
                if any(
                    ref not in by_id
                    or by_id[ref].state is not state
                    or view.horizon not in by_id[ref].horizons
                    for ref in ids
                ):
                    raise ValueError("horizon references incompatible observation")
        expected = _sha(self.payload_without_id())
        if self.content_id and self.content_id != expected:
            raise ValueError("deep research package content identity mismatch")
        object.__setattr__(self, "content_id", expected)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "candidate_id": self.candidate_id,
            "current_snapshot_id": self.current_snapshot_id,
            "plan_content_id": self.plan_content_id,
            "cutoff": self.cutoff,
            "observations": [item.payload() for item in self.observations],
            "expectation_status": self.expectation_status,
            "expectation_evidence_refs": list(self.expectation_evidence_refs),
            "catalyst_ids": list(self.catalyst_ids),
            "technical_flow_status": self.technical_flow_status,
            "technical_flow_evidence_refs": list(self.technical_flow_evidence_refs),
            "horizons": [item.payload() for item in self.horizons],
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "content_id": self.content_id}


def build_deep_research_package(
    plan: ResearchPlan,
    *,
    cutoff: str,
    observations: tuple[TransmissionObservation, ...] = (),
    expectation_status: str = "unavailable",
    expectation_evidence_refs: tuple[str, ...] = (),
    catalyst_ids: tuple[str, ...] = (),
    technical_flow_status: str = "unavailable",
    technical_flow_evidence_refs: tuple[str, ...] = (),
) -> DeepResearchPackage:
    """Assemble a lineage-preserving package; gaps remain visible, never neutralized."""
    if plan.candidate_lineage is not None:
        if _cutoff(cutoff) != plan.candidate_lineage.evaluated_at:
            raise ValueError("package cutoff must match candidate evaluation cutoff")
    unresolved = tuple(plan.questions) + tuple(gap.question for gap in plan.gaps)
    status = (
        "blocked"
        if plan.blocked
        or any(item.state is EvidenceState.MISSING_CRITICAL for item in observations)
        else "evidence_incomplete"
    )
    views = tuple(
        HorizonView(
            horizon,
            tuple(
                item.observation_id
                for item in observations
                if item.state is EvidenceState.SUPPORTING and horizon in item.horizons
            ),
            tuple(
                item.observation_id
                for item in observations
                if item.state is EvidenceState.CONTRADICTING and horizon in item.horizons
            ),
            unresolved,
            (),  # Undated catalyst IDs do not establish horizon relevance.
            status,
        )
        for horizon in ("3m", "6m", "12m")
    )
    return DeepResearchPackage(
        plan.candidate_id,
        plan.current_snapshot_id,
        plan.content_id,
        cutoff,
        observations,
        expectation_status,
        expectation_evidence_refs,
        catalyst_ids,
        technical_flow_status,
        technical_flow_evidence_refs,
        views,
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _cutoff(value: str) -> datetime:
    """Legacy date-only cutoffs mean UTC midnight, never local end-of-day."""
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), datetime.min.time(), UTC)
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("cutoff must include a timezone")
    return result.astimezone(UTC)
