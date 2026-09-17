from __future__ import annotations

from dataclasses import replace
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


def observation() -> TransmissionObservation:
    return TransmissionObservation(
        "obs",
        "price",
        "000660",
        "ASP",
        "rising",
        EvidenceState.SUPPORTING,
        EvidenceMaturity.CITED_CONTEXT,
        ("source",),
        "2026-09-01",
        horizons=("6m",),
    )


def test_package_binds_plan_not_just_pack_and_keeps_horizon_scope() -> None:
    plan = build_research_plan(candidate(), pack())
    package = build_deep_research_package(
        plan, cutoff="2026-09-01", observations=(observation(),), catalyst_ids=("undated",)
    )
    assert package.plan_content_id == plan.content_id
    assert package.plan_content_id != plan.pack_content_id
    assert [v.supporting_observation_ids for v in package.horizons] == [(), ("obs",), ()]
    assert all(not v.catalyst_ids for v in package.horizons)


def test_future_observation_rejected_by_builder_and_direct_construction() -> None:
    plan = build_research_plan(candidate(), pack())
    future = replace(observation(), cutoff="2026-09-02")
    with pytest.raises(ValueError, match="after package"):
        build_deep_research_package(plan, cutoff="2026-09-01", observations=(future,))
    package = build_deep_research_package(plan, cutoff="2026-09-01")
    with pytest.raises(ValueError, match="after package"):
        replace(package, observations=(future,), content_id="")


def test_duplicate_horizon_rejected() -> None:
    package = build_deep_research_package(build_research_plan(candidate()), cutoff="2026-09-01")
    with pytest.raises(ValueError, match="3m"):
        replace(package, horizons=(*package.horizons, package.horizons[0]), content_id="")


def test_new_cutoff_requires_new_candidate() -> None:
    with pytest.raises(ValueError, match="candidate evaluation"):
        build_deep_research_package(build_research_plan(candidate()), cutoff="2026-09-02")


def test_unavailable_evidence_cannot_be_supporting() -> None:
    with pytest.raises(ValueError, match="unavailable evidence"):
        replace(observation(), maturity=EvidenceMaturity.UNAVAILABLE)


@pytest.mark.parametrize("field", ["expectation_status", "technical_flow_status"])
def test_free_text_status_cannot_claim_certified_authority(field: str) -> None:
    package = build_deep_research_package(build_research_plan(candidate()), cutoff="2026-09-01")
    with pytest.raises(ValueError, match="certified status"):
        replace(package, **{field: "certified"}, content_id="")
