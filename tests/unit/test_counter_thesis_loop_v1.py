from __future__ import annotations

import pytest
from test_research_model_runtime_v1 import candidate, pack

from alpha_cycle.intelligence.counter_thesis_loop_v1 import (
    AlternateHypothesis,
    UnexplainedObservation,
    build_counter_thesis_package,
)
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
    assert package.reopened_gaps == (gap,)
    assert package.payload()["content_id"] == package.content_id


def test_counter_thesis_rejects_unknown_gap() -> None:
    plan = build_research_plan(candidate(), pack())
    observation = UnexplainedObservation(
        "obs-1", plan.candidate_id, "unknown", "2026-09-01", reopened_gap_ids=("missing",)
    )
    with pytest.raises(ValueError, match="unknown evidence gap"):
        build_counter_thesis_package(plan, observations=(observation,), hypotheses=())
