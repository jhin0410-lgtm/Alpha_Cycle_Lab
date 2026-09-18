from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from test_observable_universe import T0, T1, T2, observation, snapshot

from alpha_cycle.intelligence.deep_research_integration_v1 import build_deep_research_package
from alpha_cycle.intelligence.observable_universe import (
    CandidateRule,
    ChangeState,
    EvidenceMaturity,
    PlannerCandidateInput,
    ResearchPriority,
    compare_universe_snapshots,
    persist_successful_universe_attempt,
    planner_input,
    publish_failed_universe_attempt,
    surface_research_candidates,
)
from alpha_cycle.intelligence.persisted_research_plan_v1 import (
    DriverObservationBinding,
    build_persisted_research_plan,
)
from alpha_cycle.intelligence.research_model_runtime_v1 import (
    KnowledgePack,
    PackLifecycle,
    ResearchDriver,
)


def setup_store(root: Path, *, stale: bool = False) -> PlannerCandidateInput:
    prior = snapshot(1.0)
    obs = observation(3.0, at=T0 if stale else T1)
    current = snapshot(cutoff=T1, obs=(obs,), version="2")
    persist_successful_universe_attempt(prior, output_root=root, attempted_at=T0)
    persist_successful_universe_attempt(current, output_root=root, attempted_at=T1)
    changes = compare_universe_snapshots(prior, current)
    rule = CandidateRule(
        "change",
        "market_return",
        (ChangeState.CHANGED, ChangeState.INCOMPARABLE, ChangeState.STALE),
        ResearchPriority.ELEVATED,
        "research measured change",
    )
    return planner_input(
        surface_research_candidates(current, changes, (rule,), prior_snapshot=prior)[0]
    )


def model() -> KnowledgePack:
    return KnowledgePack(
        "memory_semiconductor",
        "1",
        PackLifecycle.DRAFT,
        ("market_state",),
        (
            ResearchDriver(
                "market_state",
                "measured market state",
                "coincident",
                EvidenceMaturity.STRUCTURED_OBSERVATION,
            ),
        ),
        (),
    )


def binding() -> DriverObservationBinding:
    return DriverObservationBinding(
        "market_state",
        "000660",
        "market_return",
        "return",
        "percent",
        "adjusted_close",
        "20d",
        "trailing_market_return",
        timedelta(hours=12),
    )


def test_replayed_observation_supplies_maturity_and_source_refs(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path)
    result = build_persisted_research_plan(
        candidate, model(), universe_store=tmp_path, bindings=(binding(),)
    )
    assert result.resolutions[0].status == "usable"
    assert result.resolutions[0].maturity is EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE
    assert result.resolutions[0].observation_id is not None
    assert not result.plan.gaps
    assert result.plan.blocked  # Existing missing consensus remains a blocker.
    again = build_persisted_research_plan(
        candidate, model(), universe_store=tmp_path, bindings=(binding(),)
    )
    assert again.content_id == result.content_id


@pytest.mark.parametrize("field", ["metric_id", "unit", "basis", "window", "semantics"])
def test_semantic_mismatch_cannot_close_driver_gap(tmp_path: Path, field: str) -> None:
    candidate = setup_store(tmp_path)
    incompatible = replace(binding(), **{field: "different"})
    result = build_persisted_research_plan(
        candidate, model(), universe_store=tmp_path, bindings=(incompatible,)
    )
    assert result.resolutions[0].status == "semantic_mismatch"
    assert result.plan.gaps[0].critical
    assert not result.plan.usable_evidence_refs


def test_stale_source_does_not_gain_freshness_from_snapshot(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path, stale=True)
    result = build_persisted_research_plan(
        candidate, model(), universe_store=tmp_path, bindings=(binding(),)
    )
    assert result.resolutions[0].status == "stale"
    assert result.plan.gaps[0].critical
    assert not result.plan.usable_evidence_refs
    assert result.plan.candidate_lineage is not None
    assert result.plan.candidate_lineage.evidence_refs


def test_failed_new_attempt_cannot_reuse_last_success_as_current(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path)
    publish_failed_universe_attempt(
        output_root=tmp_path, attempted_at=T2, failure_code="source_failed"
    )
    with pytest.raises(ValueError, match="not ready"):
        build_persisted_research_plan(
            candidate, model(), universe_store=tmp_path, bindings=(binding(),)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_snapshot_id", "f" * 64),
        ("evaluated_at", T2),
        ("member_id", "foreign"),
        ("required_dimensions", ()),
        ("missing_dimensions", ()),
    ],
)
def test_foreign_or_stale_candidate_rejected(tmp_path: Path, field: str, value: object) -> None:
    candidate = replace(setup_store(tmp_path), **{field: value})
    with pytest.raises(ValueError, match="candidate"):
        build_persisted_research_plan(
            candidate, model(), universe_store=tmp_path, bindings=(binding(),)
        )


def test_insufficient_maturity_stays_visible(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path)
    pack = model()
    pack = replace(
        pack,
        drivers=(
            replace(
                pack.drivers[0],
                required_maturity=EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY,
            ),
        ),
        content_id="",
    )
    result = build_persisted_research_plan(
        candidate, pack, universe_store=tmp_path, bindings=(binding(),)
    )
    assert result.resolutions[0].status == "insufficient_maturity"
    assert not result.plan.usable_evidence_refs
    assert result.plan.gaps[0].critical
    assert result.plan.gaps[0].available_maturity is EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE


def test_missing_slot_and_duplicate_bindings(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path)
    result = build_persisted_research_plan(
        candidate,
        model(),
        universe_store=tmp_path,
        bindings=(replace(binding(), dimension_id="not_observed"),),
    )
    assert result.resolutions[0].status == "missing"
    assert result.plan.gaps[0].critical
    with pytest.raises(ValueError, match="duplicate"):
        build_persisted_research_plan(
            candidate, model(), universe_store=tmp_path, bindings=(binding(), binding())
        )


def test_empty_store_fails_closed(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path)
    with pytest.raises(ValueError, match="not ready"):
        build_persisted_research_plan(
            candidate, model(), universe_store=tmp_path / "empty", bindings=(binding(),)
        )


def test_binding_policy_identity_survives_downstream_package(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path)
    first = build_persisted_research_plan(
        candidate, model(), universe_store=tmp_path, bindings=(binding(),)
    )
    second = build_persisted_research_plan(
        candidate,
        model(),
        universe_store=tmp_path,
        bindings=(replace(binding(), maximum_age=timedelta(days=3)),),
    )
    assert first.plan.content_id == second.plan.content_id
    assert first.content_id != second.content_id
    package = build_deep_research_package(first, cutoff=T1.isoformat())
    assert package.plan_content_id == first.content_id


def test_age_boundary_is_inclusive(tmp_path: Path) -> None:
    candidate = setup_store(tmp_path, stale=True)
    result = build_persisted_research_plan(
        candidate,
        model(),
        universe_store=tmp_path,
        bindings=(replace(binding(), maximum_age=timedelta(days=1)),),
    )
    assert result.resolutions[0].status == "usable"
