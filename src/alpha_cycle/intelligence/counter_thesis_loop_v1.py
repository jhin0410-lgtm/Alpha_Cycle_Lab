"""Adversarial counter-thesis and blind-spot registry for R1-D."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from alpha_cycle.intelligence.research_model_runtime_v1 import EvidenceGap, ResearchPlan


class HypothesisState(StrEnum):
    UNTESTED = "untested"
    SUPPORTING = "supporting"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class UnexplainedObservation:
    observation_id: str
    candidate_id: str
    statement: str
    cutoff: str
    evidence_refs: tuple[str, ...] = ()
    reopened_gap_ids: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "candidate_id": self.candidate_id,
            "statement": self.statement,
            "cutoff": self.cutoff,
            "evidence_refs": list(self.evidence_refs),
            "reopened_gap_ids": list(self.reopened_gap_ids),
        }


@dataclass(frozen=True)
class AlternateHypothesis:
    hypothesis_id: str
    observation_id: str
    statement: str
    state: HypothesisState = HypothesisState.UNTESTED
    tests: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "observation_id": self.observation_id,
            "statement": self.statement,
            "state": self.state.value,
            "tests": list(self.tests),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class CounterThesisPackage:
    candidate_id: str
    current_snapshot_id: str
    observations: tuple[UnexplainedObservation, ...]
    hypotheses: tuple[AlternateHypothesis, ...]
    reopened_gaps: tuple[EvidenceGap, ...]
    content_id: str = ""

    def __post_init__(self) -> None:
        if len({item.observation_id for item in self.observations}) != len(self.observations):
            raise ValueError("duplicate unexplained observation IDs")
        if len({item.hypothesis_id for item in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("duplicate alternate hypothesis IDs")
        expected = _sha(self.payload_without_id())
        if self.content_id and self.content_id != expected:
            raise ValueError("counter-thesis content identity mismatch")
        object.__setattr__(self, "content_id", expected)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "candidate_id": self.candidate_id,
            "current_snapshot_id": self.current_snapshot_id,
            "observations": [item.payload() for item in self.observations],
            "hypotheses": [item.payload() for item in self.hypotheses],
            "reopened_gaps": [item.payload() for item in self.reopened_gaps],
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "content_id": self.content_id}


def build_counter_thesis_package(
    plan: ResearchPlan,
    *,
    observations: tuple[UnexplainedObservation, ...],
    hypotheses: tuple[AlternateHypothesis, ...],
) -> CounterThesisPackage:
    """Reopen only explicit plan gaps linked to an unexplained observation."""
    observation_ids = {item.observation_id for item in observations}
    if any(item.candidate_id != plan.candidate_id for item in observations):
        raise ValueError("counter-thesis observation candidate mismatch")
    if any(item.observation_id not in observation_ids for item in hypotheses):
        raise ValueError("hypothesis references unknown observation")
    reopened_ids = {gap_id for item in observations for gap_id in item.reopened_gap_ids}
    known = {gap.gap_id: gap for gap in plan.gaps}
    if reopened_ids - known.keys():
        raise ValueError("counter-thesis references unknown evidence gap")
    return CounterThesisPackage(
        plan.candidate_id,
        plan.current_snapshot_id,
        observations,
        hypotheses,
        tuple(known[gap_id] for gap_id in sorted(reopened_ids)),
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
