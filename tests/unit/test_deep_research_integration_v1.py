from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_cycle.intelligence.deep_research_integration_v1 import (
    DeepResearchPackage,
    EvidenceState,
    TransmissionObservation,
    build_deep_research_package,
)
from alpha_cycle.intelligence.observable_universe import (
    EvidenceBlocker,
    EvidenceMaturity,
    MemberKind,
    PlannerCandidateInput,
    ResearchModelStatus,
    ResearchPriority,
)
from alpha_cycle.intelligence.research_model_runtime_v1 import (
    KnowledgePack,
    PackLifecycle,
    ResearchDriver,
    TransmissionHypothesis,
    TransmissionKind,
    build_research_plan,
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
        (EvidenceBlocker("inventory", "missing"),),
        ResearchModelStatus.DRAFT,
        86400000000,
    )


def pack() -> KnowledgePack:
    return KnowledgePack(
        "memory_semiconductor",
        "2026.09.1",
        PackLifecycle.SOURCE_BOUND,
        ("demand", "inventory", "price", "company earnings"),
        (
            ResearchDriver(
                "price", "contract pricing", "leading", EvidenceMaturity.STRUCTURED_OBSERVATION
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
            ),
        ),
    )


def test_r1c_package_preserves_lineage_and_three_horizons() -> None:
    plan = build_research_plan(
        candidate(),
        pack(),
        available_evidence={
            "price": (EvidenceMaturity.STRUCTURED_OBSERVATION, ("price-ref",)),
            "inventory": (EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE, ("inventory-ref",)),
        },
    )
    observation = TransmissionObservation(
        "obs-1",
        "price",
        "000660",
        "ASP",
        "price rising",
        EvidenceState.SUPPORTING,
        EvidenceMaturity.STRUCTURED_OBSERVATION,
        ("price-ref",),
        "2026-09-01",
    )
    package = build_deep_research_package(
        plan, cutoff="2026-09-01", observations=(observation,), catalyst_ids=("cat-1",)
    )
    assert package.candidate_id == plan.candidate_id
    assert {view.horizon for view in package.horizons} == {"3m", "6m", "12m"}
    assert package.payload()["content_id"] == package.content_id


def test_transmission_requires_lineage_unless_missing() -> None:
    with pytest.raises(ValueError, match="source references"):
        TransmissionObservation(
            "obs",
            "driver",
            "company",
            "metric",
            "value",
            EvidenceState.SUPPORTING,
            EvidenceMaturity.CITED_CONTEXT,
            (),
            "2026-09-01",
        )


def test_package_rejects_missing_horizon() -> None:
    with pytest.raises(ValueError, match="3m"):
        DeepResearchPackage(
            "a", "b", None, "2026-09-01", (), "unavailable", (), (), "unavailable", (), ()
        )
