from __future__ import annotations

import pytest

from alpha_cycle.intelligence.deep_research_integration_v1 import (
    DeepResearchPackage,
    EvidenceState,
    TransmissionObservation,
    build_deep_research_package,
)
from alpha_cycle.intelligence.observable_universe import EvidenceMaturity
from alpha_cycle.intelligence.research_model_runtime_v1 import build_research_plan
from tests.unit.test_research_model_runtime_v1 import candidate, pack


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
