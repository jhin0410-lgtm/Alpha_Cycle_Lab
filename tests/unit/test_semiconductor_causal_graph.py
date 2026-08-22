from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from alpha_cycle.intelligence.decision_thesis_v2 import EpistemicStatus
from alpha_cycle.intelligence.semiconductor_causal_graph import (
    CausalEdge,
    CausalEdgeDirection,
    CausalNode,
    CausalNodeType,
    CriticalStateVariable,
    TransmissionLag,
    build_semiconductor_causal_graph,
    load_semiconductor_causal_engine_policy,
    persist_semiconductor_causal_graph,
)

_KST = ZoneInfo("Asia/Seoul")
_SOURCE_SNAPSHOT = "a" * 64


def _critical_node(
    node_id: str,
    state: CriticalStateVariable,
) -> CausalNode:
    return CausalNode(
        node_id=node_id,
        label=state.value,
        node_type=CausalNodeType.CRITICAL_STATE,
        description=f"Decision-level state variable for {state.value}.",
        critical_state_variable=state,
    )


def _nodes() -> tuple[CausalNode, ...]:
    return (
        _critical_node("demand", CriticalStateVariable.AI_HBM_DEMAND),
        _critical_node("supply", CriticalStateVariable.SUPPLY_CAPACITY_YIELD),
        _critical_node("price_mix", CriticalStateVariable.MEMORY_PRICE_MIX),
        _critical_node(
            "revision",
            CriticalStateVariable.EARNINGS_REVISION_TRAJECTORY,
        ),
        _critical_node("valuation", CriticalStateVariable.VALUATION_POSITIONING),
        CausalNode(
            node_id="gross_margin",
            label="gross margin",
            node_type=CausalNodeType.ACCOUNTING_METRIC,
            description="Company gross-margin state used in earnings transmission.",
        ),
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    epistemic_status: EpistemicStatus = EpistemicStatus.ECONOMIC_HYPOTHESIS,
    evidence_refs: tuple[str, ...] = (),
) -> CausalEdge:
    return CausalEdge(
        edge_id=edge_id,
        source_node_id=source,
        target_node_id=target,
        mechanism=f"{source} changes the economic state represented by {target}.",
        epistemic_status=epistemic_status,
        direction=CausalEdgeDirection.CONDITIONAL,
        lag=TransmissionLag(
            minimum_days=0,
            maximum_days=180,
            condition="Transmission is evaluated only while the stated memory regime persists.",
        ),
        regime_applicability=("memory-cycle",),
        evidence_refs=evidence_refs,
        opposing_evidence_refs=(),
        falsifier=f"Observed {target} fails to respond while the {source} state persists.",
    )


def _edges() -> tuple[CausalEdge, ...]:
    return (
        _edge("demand-to-supply", "demand", "supply"),
        _edge("supply-to-price", "supply", "price_mix"),
        _edge("price-to-margin", "price_mix", "gross_margin"),
        _edge("margin-to-revision", "gross_margin", "revision"),
        _edge("revision-to-valuation", "revision", "valuation"),
    )


def _graph(**overrides: object):
    values: dict[str, object] = {
        "graph_id": "semiconductor-foundation",
        "snapshot_version": 1,
        "parent_snapshot_id": None,
        "captured_at": datetime(2026, 8, 22, 19, 0, tzinfo=_KST),
        "evaluation_date": "2026-08-22",
        "security_id": "000660",
        "nodes": _nodes(),
        "edges": _edges(),
        "source_snapshot_ids": (_SOURCE_SNAPSHOT,),
    }
    values.update(overrides)
    return build_semiconductor_causal_graph(**values)  # type: ignore[arg-type]


def test_policy_freezes_five_critical_states_and_source_boundary() -> None:
    policy = load_semiconductor_causal_engine_policy()
    assert policy.critical_state_variable_max == 5
    assert policy.critical_state_variables == (
        "ai_hbm_demand",
        "supply_capacity_yield",
        "memory_price_mix",
        "earnings_revision_trajectory",
        "valuation_positioning",
    )
    assert policy.feedback_cycles_allowed
    assert not policy.dag_claimed
    assert not policy.correlation_alone_may_establish_causality
    assert len(policy.source_policy_evidence_id) == 64


def test_policy_boolean_malformed_string_fails_closed(tmp_path: Path) -> None:
    raw = yaml.safe_load(Path("config/semiconductor_causal_engine.v1.yaml").read_text())
    raw["policy"]["graph_policy"]["correlation_alone_may_establish_causality"] = "false"
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a YAML boolean"):
        load_semiconductor_causal_engine_policy(path)


def test_graph_maps_all_five_critical_states_and_preserves_boundaries() -> None:
    graph = _graph()
    assert len(graph.critical_state_variables) == 5
    assert len(graph.policy_evidence_id) == 64
    assert len(graph.source_policy_evidence_id) == 64
    assert len(graph.guardrail_evidence_id) == 64
    payload = graph.payload_without_id()
    assert payload["dag_claimed"] is False
    assert payload["correlation_alone_establishes_causality"] is False
    assert payload["forecast_generation_enabled"] is False
    assert payload["decision_score_enabled"] is False
    assert payload["investability_decision_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_missing_critical_state_mapping_is_rejected() -> None:
    nodes = tuple(node for node in _nodes() if node.node_id != "valuation")
    edges = tuple(edge for edge in _edges() if edge.target_node_id != "valuation")
    with pytest.raises(ValueError, match="every frozen critical state"):
        _graph(nodes=nodes, edges=edges)


def test_edge_cannot_reference_missing_node() -> None:
    broken = replace(_edges()[0], target_node_id="missing")
    with pytest.raises(ValueError, match="target node is missing"):
        _graph(edges=(broken,) + _edges()[1:])


def test_self_loop_is_rejected_but_feedback_cycle_is_allowed() -> None:
    with pytest.raises(ValueError, match="self-loops"):
        _edge("self", "supply", "supply")

    feedback = _edge("price-to-supply", "price_mix", "supply")
    graph = _graph(edges=_edges() + (feedback,))
    assert any(edge.edge_id == "price-to-supply" for edge in graph.edges)


def test_observed_or_validated_edge_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence_refs"):
        _edge(
            "validated",
            "price_mix",
            "gross_margin",
            epistemic_status=EpistemicStatus.EMPIRICALLY_VALIDATED_RELATIONSHIP,
        )
    valid = _edge(
        "validated",
        "price_mix",
        "gross_margin",
        epistemic_status=EpistemicStatus.EMPIRICALLY_VALIDATED_RELATIONSHIP,
        evidence_refs=("evidence:historical-margin-transmission",),
    )
    assert valid.evidence_refs


def test_edge_requires_regime_lag_and_falsifier() -> None:
    base = _edge("base", "price_mix", "gross_margin")
    with pytest.raises(ValueError, match="regime_applicability"):
        replace(base, regime_applicability=())
    with pytest.raises(ValueError, match="non-empty text"):
        replace(base, falsifier="")
    with pytest.raises(ValueError, match="day range or explicit condition"):
        replace(base, lag=TransmissionLag())


def test_current_observed_state_requires_evidence() -> None:
    with pytest.raises(ValueError, match="current-state claim requires evidence_refs"):
        CausalNode(
            node_id="observed-demand",
            label="observed demand",
            node_type=CausalNodeType.INDUSTRY_DRIVER,
            description="Observed demand state.",
            current_state_statement="AI accelerator demand is expanding.",
            current_state_epistemic_status=EpistemicStatus.OBSERVED_FACT,
        )


def test_graph_lineage_is_append_only() -> None:
    first = _graph()
    second = _graph(
        snapshot_version=2,
        parent_snapshot_id=first.snapshot_id,
        captured_at=datetime(2026, 8, 23, 19, 0, tzinfo=_KST),
    )
    assert second.parent_snapshot_id == first.snapshot_id
    assert second.snapshot_id != first.snapshot_id


def test_persistence_is_content_addressed_and_read_only(tmp_path: Path) -> None:
    graph = _graph()
    pointer = persist_semiconductor_causal_graph(graph, output_root=tmp_path)
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    directory = Path(pointer_payload["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == graph.snapshot_id
    assert manifest["critical_state_count"] == 5
    assert manifest["dag_claimed"] is False
    assert manifest["forecast_generation_enabled"] is False
    assert manifest["decision_score_enabled"] is False
    assert manifest["investability_decision_enabled"] is False
    assert manifest["order_api_enabled"] is False
