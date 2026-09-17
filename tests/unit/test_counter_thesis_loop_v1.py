from __future__ import annotations

from dataclasses import replace

import pytest
from test_research_model_runtime_v1 import candidate, pack

from alpha_cycle.intelligence.counter_thesis_loop_v1 import (
    AlternateHypothesis,
    CounterThesisPackage,
    UnexplainedObservation,
    build_counter_thesis_package,
)
from alpha_cycle.intelligence.observable_universe import EvidenceMaturity
from alpha_cycle.intelligence.research_model_runtime_v1 import build_research_plan


def test_counter_thesis_reopens_only_linked_gaps() -> None:
    plan = build_research_plan(candidate(), pack())
    gap = next(item for item in plan.gaps if item.driver_id == "inventory")
    observation = UnexplainedObservation(
        "obs-1",
        plan.candidate_id,
        "price rose while inventory unknown",
        "2026-09-01",
        reopened_gap_ids=(gap.gap_id,),
    )
    hypothesis = AlternateHypothesis(
        "hyp-1", "obs-1", "mix shift explains the move", tests=("check mix",)
    )
    package = build_counter_thesis_package(
        plan, observations=(observation,), hypotheses=(hypothesis,)
    )
    assert package.reopened_gaps[0].gap_id == gap.gap_id
    assert package.reopened_gaps[0].critical
    assert package.payload()["content_id"] == package.content_id


def test_counter_thesis_rejects_unknown_gap() -> None:
    plan = build_research_plan(candidate(), pack())
    observation = UnexplainedObservation(
        "obs-1", plan.candidate_id, "unknown", "2026-09-01", reopened_gap_ids=("missing",)
    )
    with pytest.raises(ValueError, match="unknown evidence gap"):
        build_counter_thesis_package(plan, observations=(observation,), hypotheses=())


def test_reopening_invalidates_previous_sufficient_maturity() -> None:
    plan = build_research_plan(candidate(), pack())
    gap = replace(
        plan.gaps[0],
        available_maturity=EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY,
        evidence_refs=("old-evidence",),
    )
    assert not gap.critical
    plan = replace(plan, gaps=(gap,))
    observation = UnexplainedObservation(
        "obs", plan.candidate_id, "new contradiction", "2026-09-01", reopened_gap_ids=(gap.gap_id,)
    )
    package = build_counter_thesis_package(plan, observations=(observation,), hypotheses=())
    assert package.reopened_gaps[0].critical
    assert package.reopened_gaps[0].evidence_refs == ("old-evidence",)
    assert not plan.gaps[0].critical


def test_direct_package_constructor_rejects_foreign_candidate() -> None:
    observation = UnexplainedObservation("obs", "foreign", "statement", "2026-09-01")
    with pytest.raises(ValueError, match="candidate mismatch"):
        CounterThesisPackage("candidate", "snapshot", (observation,), (), ())
