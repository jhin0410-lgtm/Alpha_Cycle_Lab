"""Generic versioned research models and evidence-aware planning for Product R1-B.

Knowledge packs are declarative research hypotheses, not source authority.  This
module deliberately carries gaps and maturity rather than converting missing
evidence into a score or recommendation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from alpha_cycle.intelligence.observable_universe import (
    EvidenceBlocker,
    EvidenceMaturity,
    PlannerCandidateInput,
)

SCHEMA_VERSION = 1


class PackLifecycle(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SOURCE_BOUND = "source_bound"
    OPERATIONAL = "operational"
    CALIBRATING = "calibrating"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"


class GapKind(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    EXPLORATORY = "exploratory"


class TransmissionKind(StrEnum):
    ACCOUNTING_IDENTITY = "accounting_identity"
    MECHANICAL = "mechanical"
    EMPIRICAL = "empirical"
    HYPOTHESIS = "research_hypothesis"
    QUALITATIVE = "qualitative_judgment"


@dataclass(frozen=True)
class ResearchDriver:
    driver_id: str
    meaning: str
    role: str
    required_maturity: EvidenceMaturity
    gap_kind: GapKind = GapKind.REQUIRED
    source_requirements: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "driver_id": self.driver_id,
            "meaning": self.meaning,
            "role": self.role,
            "required_maturity": self.required_maturity.value,
            "gap_kind": self.gap_kind.value,
            "source_requirements": list(self.source_requirements),
        }


@dataclass(frozen=True)
class TransmissionHypothesis:
    edge_id: str
    source: str
    target: str
    kind: TransmissionKind
    lag: str
    rationale: str
    caveats: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "lag": self.lag,
            "rationale": self.rationale,
            "caveats": list(self.caveats),
        }


@dataclass(frozen=True)
class EvidenceGap:
    gap_id: str
    driver_id: str
    kind: GapKind
    question: str
    required_maturity: EvidenceMaturity
    available_maturity: EvidenceMaturity | None = None
    evidence_refs: tuple[str, ...] = ()
    reason: str = ""

    @property
    def critical(self) -> bool:
        return self.kind is GapKind.REQUIRED and (
            self.available_maturity is None
            or _maturity_rank(self.available_maturity) < _maturity_rank(self.required_maturity)
        )

    def payload(self) -> dict[str, object]:
        return {
            "gap_id": self.gap_id,
            "driver_id": self.driver_id,
            "kind": self.kind.value,
            "question": self.question,
            "required_maturity": self.required_maturity.value,
            "available_maturity": (
                None if self.available_maturity is None else self.available_maturity.value
            ),
            "evidence_refs": list(self.evidence_refs),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class KnowledgePack:
    domain_id: str
    version: str
    lifecycle: PackLifecycle
    value_chain: tuple[str, ...]
    drivers: tuple[ResearchDriver, ...]
    transmissions: tuple[TransmissionHypothesis, ...]
    company_exposures: tuple[str, ...] = ()
    catalysts: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    counter_thesis_questions: tuple[str, ...] = ()
    unresolved_gaps: tuple[EvidenceGap, ...] = ()
    supported_horizons: tuple[str, ...] = ("3m", "6m", "12m")
    parent_version: str | None = None
    revision_rationale: str = ""
    content_id: str = ""

    def __post_init__(self) -> None:
        _text(self.domain_id, "domain_id")
        _text(self.version, "version")
        if not self.value_chain:
            raise ValueError("knowledge pack requires a value chain")
        if len({item.driver_id for item in self.drivers}) != len(self.drivers):
            raise ValueError("knowledge pack driver IDs must be unique")
        if len({item.edge_id for item in self.transmissions}) != len(self.transmissions):
            raise ValueError("knowledge pack transmission IDs must be unique")
        if len({item.gap_id for item in self.unresolved_gaps}) != len(self.unresolved_gaps):
            raise ValueError("knowledge pack gap IDs must be unique")
        if self.lifecycle in {PackLifecycle.OPERATIONAL, PackLifecycle.CALIBRATING}:
            if any(gap.critical for gap in self.unresolved_gaps):
                raise ValueError("operational knowledge pack cannot contain critical gaps")
        expected = _sha(self.payload_without_id())
        if self.content_id and self.content_id != expected:
            raise ValueError("knowledge pack content identity mismatch")
        object.__setattr__(self, "content_id", expected)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "domain_id": self.domain_id,
            "version": self.version,
            "lifecycle": self.lifecycle.value,
            "value_chain": list(self.value_chain),
            "drivers": [item.payload() for item in self.drivers],
            "transmissions": [item.payload() for item in self.transmissions],
            "company_exposures": list(self.company_exposures),
            "catalysts": list(self.catalysts),
            "risks": list(self.risks),
            "counter_thesis_questions": list(self.counter_thesis_questions),
            "unresolved_gaps": [item.payload() for item in self.unresolved_gaps],
            "supported_horizons": list(self.supported_horizons),
            "parent_version": self.parent_version,
            "revision_rationale": self.revision_rationale,
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "content_id": self.content_id}


@dataclass(frozen=True)
class ModelRevisionProposal:
    """An explicit, immutable proposal to revise a knowledge pack.

    Proposals do not mutate or promote a pack.  They preserve the parent
    identity and the evidence-backed rationale needed for later review.
    """

    proposal_id: str
    domain_id: str
    parent_version: str
    parent_content_id: str
    proposed_version: str
    proposed_change: str
    reason: str
    triggering_evidence_refs: tuple[str, ...] = ()
    affected_driver_ids: tuple[str, ...] = ()
    affected_edge_ids: tuple[str, ...] = ()
    expected_improvement: str = ""
    risks: tuple[str, ...] = ()
    effective_date: str | None = None
    status: str = "proposed"
    content_id: str = ""

    def __post_init__(self) -> None:
        for field, value in (
            ("proposal_id", self.proposal_id),
            ("domain_id", self.domain_id),
            ("parent_version", self.parent_version),
            ("parent_content_id", self.parent_content_id),
            ("proposed_version", self.proposed_version),
            ("proposed_change", self.proposed_change),
            ("reason", self.reason),
        ):
            _text(value, field)
        expected = _sha(self.payload_without_id())
        if self.content_id and self.content_id != expected:
            raise ValueError("revision proposal content identity mismatch")
        object.__setattr__(self, "content_id", expected)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "domain_id": self.domain_id,
            "parent_version": self.parent_version,
            "parent_content_id": self.parent_content_id,
            "proposed_version": self.proposed_version,
            "proposed_change": self.proposed_change,
            "reason": self.reason,
            "triggering_evidence_refs": list(self.triggering_evidence_refs),
            "affected_driver_ids": list(self.affected_driver_ids),
            "affected_edge_ids": list(self.affected_edge_ids),
            "expected_improvement": self.expected_improvement,
            "risks": list(self.risks),
            "effective_date": self.effective_date,
            "status": self.status,
        }

    def payload(self) -> dict[str, object]:
        return {**self.payload_without_id(), "content_id": self.content_id}


def propose_pack_revision(
    parent: KnowledgePack,
    *,
    proposal_id: str,
    proposed_version: str,
    proposed_change: str,
    reason: str,
    triggering_evidence_refs: tuple[str, ...] = (),
    affected_driver_ids: tuple[str, ...] = (),
    affected_edge_ids: tuple[str, ...] = (),
    expected_improvement: str = "",
    risks: tuple[str, ...] = (),
    effective_date: str | None = None,
) -> ModelRevisionProposal:
    """Create a revision proposal without changing the parent pack."""
    return ModelRevisionProposal(
        proposal_id=proposal_id,
        domain_id=parent.domain_id,
        parent_version=parent.version,
        parent_content_id=parent.content_id,
        proposed_version=proposed_version,
        proposed_change=proposed_change,
        reason=reason,
        triggering_evidence_refs=triggering_evidence_refs,
        affected_driver_ids=affected_driver_ids,
        affected_edge_ids=affected_edge_ids,
        expected_improvement=expected_improvement,
        risks=risks,
        effective_date=effective_date,
    )


@dataclass(frozen=True)
class ResearchPlan:
    candidate_id: str
    current_snapshot_id: str
    domain_id: str | None
    pack_content_id: str | None
    pack_lifecycle: PackLifecycle | None
    reasons: tuple[str, ...]
    questions: tuple[str, ...]
    required_evidence: tuple[str, ...]
    usable_evidence_refs: tuple[str, ...]
    gaps: tuple[EvidenceGap, ...]
    blockers: tuple[EvidenceBlocker, ...]
    source_tasks: tuple[str, ...]
    counter_thesis_questions: tuple[str, ...]
    horizons: tuple[str, ...]
    status: str

    @property
    def blocked(self) -> bool:
        return bool(self.blockers) or any(gap.critical for gap in self.gaps)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": self.candidate_id,
            "current_snapshot_id": self.current_snapshot_id,
            "domain_id": self.domain_id,
            "pack_content_id": self.pack_content_id,
            "pack_lifecycle": None if self.pack_lifecycle is None else self.pack_lifecycle.value,
            "reasons": list(self.reasons),
            "questions": list(self.questions),
            "required_evidence": list(self.required_evidence),
            "usable_evidence_refs": list(self.usable_evidence_refs),
            "gaps": [gap.payload() for gap in self.gaps],
            "blockers": [blocker.__dict__ for blocker in self.blockers],
            "source_tasks": list(self.source_tasks),
            "counter_thesis_questions": list(self.counter_thesis_questions),
            "horizons": list(self.horizons),
            "status": self.status,
        }


def build_research_plan(
    candidate: PlannerCandidateInput,
    pack: KnowledgePack | None = None,
    *,
    available_evidence: dict[str, tuple[EvidenceMaturity, tuple[str, ...]]] | None = None,
) -> ResearchPlan:
    """Build a fail-closed plan from an exact R1-A handoff and optional pack."""
    available_evidence = available_evidence or {}
    reasons = candidate.measured_reasons
    blockers = list(candidate.blocked_evidence)
    questions: list[str] = []
    required: list[str] = []
    gaps: list[EvidenceGap] = []
    source_tasks: list[str] = []
    counter: list[str] = []
    horizons: tuple[str, ...] = ("3m", "6m", "12m")
    if pack is None:
        questions.append(
            f"What are the material drivers for the {candidate.domain_id or 'unknown'} domain?"
        )
        questions.append(
            "Which evidence sources can establish those drivers at the required maturity?"
        )
        counter.append("What alternate domain explanation could produce this observed change?")
        status = "cold_start_model_required"
    else:
        horizons = pack.supported_horizons
        counter.extend(pack.counter_thesis_questions)
        gaps.extend(pack.unresolved_gaps)
        for driver in pack.drivers:
            if driver.gap_kind is GapKind.EXPLORATORY:
                continue
            required.append(driver.driver_id)
            observed = available_evidence.get(driver.driver_id)
            if observed is None:
                gaps.append(
                    EvidenceGap(
                        f"{pack.domain_id}:{pack.version}:{driver.driver_id}",
                        driver.driver_id,
                        driver.gap_kind,
                        f"Obtain {driver.meaning}",
                        driver.required_maturity,
                        reason="no evidence supplied to planner",
                    )
                )
            else:
                maturity, refs = observed
                if _maturity_rank(maturity) < _maturity_rank(driver.required_maturity):
                    gaps.append(
                        EvidenceGap(
                            f"{pack.domain_id}:{pack.version}:{driver.driver_id}",
                            driver.driver_id,
                            driver.gap_kind,
                            f"Upgrade evidence for {driver.meaning}",
                            driver.required_maturity,
                            maturity,
                            refs,
                            reason="available evidence maturity is insufficient",
                        )
                    )
        source_tasks.extend(
            requirement for driver in pack.drivers for requirement in driver.source_requirements
        )
        questions.extend(pack.counter_thesis_questions)
        status = (
            "blocked_missing_critical_evidence"
            if any(gap.critical for gap in gaps)
            else "ready_for_research"
        )
    usable_refs = set(candidate.evidence_refs)
    if pack is not None:
        for driver in pack.drivers:
            observed = available_evidence.get(driver.driver_id)
            if observed is not None and _maturity_rank(observed[0]) >= _maturity_rank(
                driver.required_maturity
            ):
                usable_refs.update(observed[1])
    return ResearchPlan(
        candidate.candidate_id,
        candidate.current_snapshot_id,
        candidate.domain_id,
        None if pack is None else pack.content_id,
        None if pack is None else pack.lifecycle,
        reasons,
        tuple(questions),
        tuple(required),
        tuple(sorted(usable_refs)),
        tuple(gaps),
        tuple(sorted(set(blockers))),
        tuple(sorted(set(source_tasks))),
        tuple(dict.fromkeys(counter)),
        tuple(horizons),
        status,
    )


def _maturity_rank(value: EvidenceMaturity) -> int:
    return list(EvidenceMaturity).index(value)


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
