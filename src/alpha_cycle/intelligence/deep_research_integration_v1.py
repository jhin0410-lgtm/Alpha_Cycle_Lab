"""Evidence-only R1-C deep-research package assembled from an R1-B plan.

The package joins transmission, expectations, catalyst, and technical/flow
evidence while retaining point-in-time lineage.  It intentionally has no
score, recommendation, or authority-promotion field.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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

    def __post_init__(self) -> None:
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
        if len({item.observation_id for item in self.observations}) != len(self.observations):
            raise ValueError("duplicate transmission observation IDs")
        if {item.horizon for item in self.horizons} != {"3m", "6m", "12m"}:
            raise ValueError("deep research package requires 3m, 6m, and 12m views")
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
    supporting = tuple(
        item.observation_id for item in observations if item.state is EvidenceState.SUPPORTING
    )
    contradicting = tuple(
        item.observation_id for item in observations if item.state is EvidenceState.CONTRADICTING
    )
    unresolved = tuple(plan.questions) + tuple(gap.question for gap in plan.gaps)
    status = "blocked" if plan.blocked else "evidence_incomplete"
    views = tuple(
        HorizonView(horizon, supporting, contradicting, unresolved, catalyst_ids, status)
        for horizon in ("3m", "6m", "12m")
    )
    return DeepResearchPackage(
        plan.candidate_id,
        plan.current_snapshot_id,
        plan.pack_content_id,
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
