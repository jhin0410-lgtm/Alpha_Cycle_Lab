from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_cycle.intelligence.observable_universe import (
    EvidenceBlocker,
    EvidenceMaturity,
    MemberKind,
    PlannerCandidateInput,
    ResearchModelStatus,
    ResearchPriority,
)
from alpha_cycle.intelligence.research_model_runtime_v1 import (
    EvidenceGap,
    GapKind,
    KnowledgePack,
    ModelRevisionProposal,
    PackLifecycle,
    ResearchDriver,
    TransmissionHypothesis,
    TransmissionKind,
    build_research_plan,
    propose_pack_revision,
)


def candidate() -> PlannerCandidateInput:
    return PlannerCandidateInput(
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "000660",
        MemberKind.SECURITY,
        "memory_semiconductor",
        ResearchPriority.ELEVATED,
        datetime(2026, 9, 1, tzinfo=UTC),
        ("d" * 64,),
        ("e" * 64,),
        ("market changed",),
        ("market-ref",),
        ("price", "inventory"),
        ("inventory",),
        (EvidenceBlocker("inventory", "missing critical inventory source"),),
        ResearchModelStatus.DRAFT,
        86400000000,
    )


def pack(lifecycle: PackLifecycle = PackLifecycle.SOURCE_BOUND) -> KnowledgePack:
    return KnowledgePack(
        "memory_semiconductor",
        "2026.09.1",
        lifecycle,
        ("demand", "inventory", "price", "company earnings"),
        (
            ResearchDriver(
                "price",
                "contract pricing",
                "leading",
                EvidenceMaturity.STRUCTURED_OBSERVATION,
                source_requirements=("industry price source",),
            ),
            ResearchDriver(
                "inventory",
                "channel inventory",
                "coincident",
                EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE,
            ),
        ),
        (
            TransmissionHypothesis(
                "edge-1",
                "price",
                "company earnings",
                TransmissionKind.HYPOTHESIS,
                "1-2 quarters",
                "pricing changes transmit through ASP",
                ("mix may differ",),
            ),
        ),
        counter_thesis_questions=("Could utilization explain the move without pricing?",),
    )


def test_pack_is_content_addressed_and_declarative() -> None:
    first = pack()
    second = pack()
    assert first.content_id == second.content_id
    assert first.payload()["content_id"] == first.content_id
    assert first.content_id != pack(PackLifecycle.REVIEWED).content_id


def test_operational_pack_cannot_hide_critical_gap() -> None:
    gap = EvidenceGap(
        "g",
        "inventory",
        GapKind.REQUIRED,
        "obtain inventory",
        EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE,
    )
    with pytest.raises(ValueError, match="critical gaps"):
        KnowledgePack(
            "cold",
            "1",
            PackLifecycle.OPERATIONAL,
            ("demand",),
            (
                ResearchDriver(
                    "inventory",
                    "inventory",
                    "leading",
                    EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE,
                ),
            ),
            (),
            unresolved_gaps=(gap,),
        )


def test_planner_preserves_candidate_lineage_and_blocks_missing_material_driver() -> None:
    plan = build_research_plan(candidate(), pack())
    assert plan.candidate_id == "a" * 64
    assert plan.current_snapshot_id == "c" * 64
    assert plan.pack_content_id == pack().content_id
    assert plan.blocked
    assert plan.status == "blocked_missing_critical_evidence"
    assert {gap.driver_id for gap in plan.gaps} == {"price", "inventory"}
    assert plan.blockers[0].dimension_id == "inventory"


def test_planner_accepts_only_sufficient_maturity_and_keeps_refs() -> None:
    available: dict[str, tuple[EvidenceMaturity, tuple[str, ...]]] = {
        "price": (EvidenceMaturity.STRUCTURED_OBSERVATION, ("price-ref",)),
        "inventory": (EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE, ("inventory-ref",)),
    }
    plan = build_research_plan(candidate(), pack(), available_evidence=available)
    assert not any(gap.critical for gap in plan.gaps)
    assert plan.status == "ready_for_research"
    assert plan.usable_evidence_refs == ("inventory-ref", "market-ref", "price-ref")
    assert plan.source_tasks == ("industry price source",)


def test_cold_start_is_explicit_and_does_not_invent_evidence() -> None:
    plan = build_research_plan(candidate())
    assert plan.status == "cold_start_model_required"
    assert plan.pack_content_id is None
    assert plan.usable_evidence_refs == ("market-ref",)
    assert plan.gaps == ()
    assert "material drivers" in plan.questions[0]
    assert plan.blocked


def test_revision_proposal_preserves_parent_and_is_content_addressed() -> None:
    proposal = propose_pack_revision(
        pack(),
        proposal_id="proposal-1",
        proposed_version="2026.09.2",
        proposed_change="Add utilization driver",
        reason="Observed unexplained utilization divergence",
        triggering_evidence_refs=("utilization-ref",),
        affected_driver_ids=("inventory",),
        expected_improvement="Reduce unexplained residuals",
        risks=("May overfit one cycle",),
    )
    assert isinstance(proposal, ModelRevisionProposal)
    assert proposal.parent_content_id == pack().content_id
    assert proposal.payload()["content_id"] == proposal.content_id
