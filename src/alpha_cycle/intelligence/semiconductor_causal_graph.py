"""Semiconductor causal-transmission graph for Alpha Cycle Lab Decision System v2.1.

The graph represents economic mechanisms and point-in-time evidence. It is not itself a
forecast model, a decision score, or proof of causality from correlation. Feedback loops are
allowed because real industry systems can contain them, but every material edge remains an
explicit falsifiable claim with regime and timing semantics.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DecisionSystemV21Guardrails,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import EpistemicStatus

CAUSAL_GRAPH_SCHEMA_VERSION = 1
DEFAULT_CAUSAL_POLICY = Path("config/semiconductor_causal_engine.v1.yaml")
EXPECTED_CRITICAL_STATES = (
    "ai_hbm_demand",
    "supply_capacity_yield",
    "memory_price_mix",
    "earnings_revision_trajectory",
    "valuation_positioning",
)


class CriticalStateVariable(StrEnum):
    AI_HBM_DEMAND = "ai_hbm_demand"
    SUPPLY_CAPACITY_YIELD = "supply_capacity_yield"
    MEMORY_PRICE_MIX = "memory_price_mix"
    EARNINGS_REVISION_TRAJECTORY = "earnings_revision_trajectory"
    VALUATION_POSITIONING = "valuation_positioning"


class CausalNodeType(StrEnum):
    CRITICAL_STATE = "critical_state"
    INDUSTRY_DRIVER = "industry_driver"
    COMPANY_DRIVER = "company_driver"
    COMPANY_KPI = "company_kpi"
    ACCOUNTING_METRIC = "accounting_metric"
    EXPECTATION_STATE = "expectation_state"
    VALUATION_STATE = "valuation_state"
    CATALYST = "catalyst"


class CausalEdgeDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TransmissionLag:
    """Expected transmission timing without inventing a precise date."""

    minimum_days: int | None = None
    maximum_days: int | None = None
    condition: str | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.minimum_days, "minimum_days"),
            (self.maximum_days, "maximum_days"),
        ):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{field} must be a non-negative integer when supplied")
        if (
            self.minimum_days is not None
            and self.maximum_days is not None
            and self.maximum_days < self.minimum_days
        ):
            raise ValueError("maximum_days cannot precede minimum_days")
        if self.condition is not None:
            _require_text(self.condition, "lag condition")
        if self.minimum_days is None and self.maximum_days is None and self.condition is None:
            raise ValueError("transmission lag requires a day range or explicit condition")

    def payload(self) -> dict[str, object]:
        return {
            "minimum_days": self.minimum_days,
            "maximum_days": self.maximum_days,
            "condition": self.condition,
        }


@dataclass(frozen=True)
class CausalNode:
    """One variable or state in the semiconductor transmission graph."""

    node_id: str
    label: str
    node_type: CausalNodeType
    description: str
    critical_state_variable: CriticalStateVariable | None = None
    current_state_statement: str | None = None
    current_state_epistemic_status: EpistemicStatus | None = None
    evidence_refs: tuple[str, ...] = ()
    opposing_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.node_id, "node_id")
        _require_text(self.label, "label")
        _require_text(self.description, "description")
        _validate_text_refs(self.evidence_refs, "evidence_refs")
        _validate_text_refs(self.opposing_evidence_refs, "opposing_evidence_refs")
        if self.node_type is CausalNodeType.CRITICAL_STATE:
            if self.critical_state_variable is None:
                raise ValueError("critical-state node requires critical_state_variable")
        elif self.critical_state_variable is not None:
            raise ValueError("only critical-state nodes may declare critical_state_variable")
        if (self.current_state_statement is None) != (
            self.current_state_epistemic_status is None
        ):
            raise ValueError(
                "current state statement and epistemic status must be supplied together"
            )
        if self.current_state_statement is not None:
            _require_text(self.current_state_statement, "current_state_statement")
            if self.current_state_epistemic_status in {
                EpistemicStatus.OBSERVED_FACT,
                EpistemicStatus.ACCOUNTING_IDENTITY,
                EpistemicStatus.EMPIRICALLY_VALIDATED_RELATIONSHIP,
            } and not self.evidence_refs:
                raise ValueError(
                    "observed or validated current-state claim requires evidence_refs"
                )

    def payload(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "node_type": self.node_type.value,
            "description": self.description,
            "critical_state_variable": (
                self.critical_state_variable.value
                if self.critical_state_variable is not None
                else None
            ),
            "current_state_statement": self.current_state_statement,
            "current_state_epistemic_status": (
                self.current_state_epistemic_status.value
                if self.current_state_epistemic_status is not None
                else None
            ),
            "evidence_refs": list(self.evidence_refs),
            "opposing_evidence_refs": list(self.opposing_evidence_refs),
        }


@dataclass(frozen=True)
class CausalEdge:
    """One falsifiable transmission claim between two graph nodes."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    mechanism: str
    epistemic_status: EpistemicStatus
    direction: CausalEdgeDirection
    lag: TransmissionLag
    regime_applicability: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    opposing_evidence_refs: tuple[str, ...]
    falsifier: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.edge_id, "edge_id"),
            (self.source_node_id, "source_node_id"),
            (self.target_node_id, "target_node_id"),
            (self.mechanism, "mechanism"),
            (self.falsifier, "falsifier"),
        ):
            _require_text(value, field)
        if self.source_node_id == self.target_node_id:
            raise ValueError("causal graph self-loops are prohibited")
        _validate_text_refs(self.regime_applicability, "regime_applicability")
        if not self.regime_applicability:
            raise ValueError("causal edge requires regime_applicability")
        _validate_text_refs(self.evidence_refs, "evidence_refs")
        _validate_text_refs(self.opposing_evidence_refs, "opposing_evidence_refs")
        if self.epistemic_status in {
            EpistemicStatus.OBSERVED_FACT,
            EpistemicStatus.ACCOUNTING_IDENTITY,
            EpistemicStatus.EMPIRICALLY_VALIDATED_RELATIONSHIP,
        } and not self.evidence_refs:
            raise ValueError("observed or validated causal edge requires evidence_refs")

    def payload(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "mechanism": self.mechanism,
            "epistemic_status": self.epistemic_status.value,
            "direction": self.direction.value,
            "lag": self.lag.payload(),
            "regime_applicability": list(self.regime_applicability),
            "evidence_refs": list(self.evidence_refs),
            "opposing_evidence_refs": list(self.opposing_evidence_refs),
            "falsifier": self.falsifier,
        }


@dataclass(frozen=True)
class SemiconductorCausalEnginePolicy:
    policy_id: str
    policy_version: str
    sector: str
    source_boundary_path: str
    critical_state_variables: tuple[str, ...]
    critical_state_variable_max: int
    evidence_node_count_capped: bool
    self_loops_allowed: bool
    feedback_cycles_allowed: bool
    dag_claimed: bool
    correlation_alone_may_establish_causality: bool
    material_edge_requires_falsifier: bool
    observed_or_validated_edge_requires_evidence: bool
    opposing_evidence_preserved: bool
    regime_applicability_required: bool
    timing_or_lag_required: bool
    graph_is_forecast_model: bool
    graph_is_decision_score: bool
    graph_approves_investability: bool
    automatic_execution_enabled: bool
    frozen_skhynix_2026q3_round_changed: bool
    evidence_id: str
    source_policy_evidence_id: str

    def __post_init__(self) -> None:
        if self.policy_id != "alpha_cycle_semiconductor_causal_engine":
            raise ValueError("unexpected semiconductor causal-engine policy id")
        if self.policy_version != "1.0-foundation":
            raise ValueError("unexpected semiconductor causal-engine policy version")
        if self.sector != "semiconductor":
            raise ValueError("causal-engine policy sector must be semiconductor")
        if self.critical_state_variables != EXPECTED_CRITICAL_STATES:
            raise ValueError("semiconductor critical-state variables have drifted")
        if self.critical_state_variable_max != 5:
            raise ValueError("semiconductor decision complexity cap must remain five")
        if self.evidence_node_count_capped:
            raise ValueError("evidence-node count must remain uncapped")
        if self.self_loops_allowed:
            raise ValueError("causal self-loops must remain prohibited")
        if not self.feedback_cycles_allowed:
            raise ValueError("feedback cycles must remain representable")
        if self.dag_claimed:
            raise ValueError("semiconductor graph must not claim to be a DAG")
        if self.correlation_alone_may_establish_causality:
            raise ValueError("correlation alone cannot establish causal status")
        if not self.material_edge_requires_falsifier:
            raise ValueError("material causal edges require falsifiers")
        if not self.observed_or_validated_edge_requires_evidence:
            raise ValueError("observed or validated edges require evidence")
        if not self.opposing_evidence_preserved:
            raise ValueError("opposing causal evidence must remain preserved")
        if not self.regime_applicability_required:
            raise ValueError("causal edges require regime applicability")
        if not self.timing_or_lag_required:
            raise ValueError("causal edges require timing or lag semantics")
        if self.graph_is_forecast_model or self.graph_is_decision_score:
            raise ValueError("causal graph cannot become forecast model or decision score")
        if self.graph_approves_investability or self.automatic_execution_enabled:
            raise ValueError("causal graph cannot approve or execute an investment")
        if self.frozen_skhynix_2026q3_round_changed:
            raise ValueError("causal-engine foundation cannot alter frozen SK hynix Q3")
        _validate_sha(self.evidence_id, "policy evidence_id")
        _validate_sha(self.source_policy_evidence_id, "source_policy_evidence_id")


@dataclass(frozen=True)
class SemiconductorCausalGraphSnapshot:
    """Immutable semiconductor causal graph at one point-in-time research state."""

    graph_id: str
    snapshot_version: int
    parent_snapshot_id: str | None
    captured_at: datetime
    evaluation_date: str
    security_id: str | None
    critical_state_variables: tuple[CriticalStateVariable, ...]
    nodes: tuple[CausalNode, ...]
    edges: tuple[CausalEdge, ...]
    source_snapshot_ids: tuple[str, ...]
    policy_evidence_id: str
    source_policy_evidence_id: str
    guardrail_evidence_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.graph_id, "graph_id")
        _require_text(self.evaluation_date, "evaluation_date")
        if self.security_id is not None:
            _require_text(self.security_id, "security_id")
        _require_aware(self.captured_at, "captured_at")
        _validate_lineage(self.snapshot_version, self.parent_snapshot_id)
        for value, field in (
            (self.policy_evidence_id, "policy_evidence_id"),
            (self.source_policy_evidence_id, "source_policy_evidence_id"),
            (self.guardrail_evidence_id, "guardrail_evidence_id"),
        ):
            _validate_sha(value, field)
        _validate_sha_tuple(self.source_snapshot_ids, "source_snapshot_ids")
        _validate_text_refs(self.warnings, "warnings")
        if tuple(item.value for item in self.critical_state_variables) != EXPECTED_CRITICAL_STATES:
            raise ValueError("causal graph must expose the five frozen semiconductor critical states")
        if not self.nodes:
            raise ValueError("semiconductor causal graph requires nodes")
        if not self.edges:
            raise ValueError("semiconductor causal graph requires edges")
        node_ids = tuple(node.node_id for node in self.nodes)
        _validate_unique(node_ids, "node_id")
        _validate_unique(tuple(edge.edge_id for edge in self.edges), "edge_id")
        available_nodes = set(node_ids)
        for edge in self.edges:
            if edge.source_node_id not in available_nodes:
                raise ValueError(f"causal edge source node is missing: {edge.source_node_id}")
            if edge.target_node_id not in available_nodes:
                raise ValueError(f"causal edge target node is missing: {edge.target_node_id}")
        mapped_states = {
            node.critical_state_variable
            for node in self.nodes
            if node.node_type is CausalNodeType.CRITICAL_STATE
        }
        if mapped_states != set(self.critical_state_variables):
            raise ValueError("every frozen critical state must map to a critical-state node")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
            "graph_id": self.graph_id,
            "snapshot_version": self.snapshot_version,
            "parent_snapshot_id": self.parent_snapshot_id,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date,
            "sector": "semiconductor",
            "security_id": self.security_id,
            "critical_state_variables": [
                item.value for item in self.critical_state_variables
            ],
            "nodes": [node.payload() for node in self.nodes],
            "edges": [edge.payload() for edge in self.edges],
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "policy_evidence_id": self.policy_evidence_id,
            "source_policy_evidence_id": self.source_policy_evidence_id,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "warnings": list(self.warnings),
            "dag_claimed": False,
            "correlation_alone_establishes_causality": False,
            "forecast_generation_enabled": False,
            "decision_score_enabled": False,
            "investability_decision_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


def load_semiconductor_causal_engine_policy(
    path: str | Path = DEFAULT_CAUSAL_POLICY,
) -> SemiconductorCausalEnginePolicy:
    source = Path(path)
    root = _load_yaml_object(source, "semiconductor causal-engine policy")
    if root.get("schema_version") != 1:
        raise ValueError("unexpected semiconductor causal-engine schema_version")
    policy = _mapping(root.get("policy"), "policy")
    graph = _mapping(policy.get("graph_policy"), "graph_policy")
    governance = _mapping(policy.get("governance"), "governance")
    critical = _text_tuple(policy.get("critical_state_variables"), "critical_state_variables")
    source_boundary_path = _text(policy.get("source_boundary_path"), "source_boundary_path")
    source_policy = _load_yaml_object(Path(source_boundary_path), "semiconductor source policy")
    evidence_id = _sha(root)
    source_policy_evidence_id = _sha(source_policy)
    return SemiconductorCausalEnginePolicy(
        policy_id=_text(policy.get("policy_id"), "policy_id"),
        policy_version=_text(policy.get("policy_version"), "policy_version"),
        sector=_text(policy.get("sector"), "sector"),
        source_boundary_path=source_boundary_path,
        critical_state_variables=critical,
        critical_state_variable_max=_positive_int(
            graph.get("critical_state_variable_max"),
            "critical_state_variable_max",
        ),
        evidence_node_count_capped=_strict_bool(
            graph.get("evidence_node_count_capped"),
            "evidence_node_count_capped",
        ),
        self_loops_allowed=_strict_bool(graph.get("self_loops_allowed"), "self_loops_allowed"),
        feedback_cycles_allowed=_strict_bool(
            graph.get("feedback_cycles_allowed"),
            "feedback_cycles_allowed",
        ),
        dag_claimed=_strict_bool(graph.get("dag_claimed"), "dag_claimed"),
        correlation_alone_may_establish_causality=_strict_bool(
            graph.get("correlation_alone_may_establish_causality"),
            "correlation_alone_may_establish_causality",
        ),
        material_edge_requires_falsifier=_strict_bool(
            graph.get("material_edge_requires_falsifier"),
            "material_edge_requires_falsifier",
        ),
        observed_or_validated_edge_requires_evidence=_strict_bool(
            graph.get("observed_or_validated_edge_requires_evidence"),
            "observed_or_validated_edge_requires_evidence",
        ),
        opposing_evidence_preserved=_strict_bool(
            graph.get("opposing_evidence_preserved"),
            "opposing_evidence_preserved",
        ),
        regime_applicability_required=_strict_bool(
            graph.get("regime_applicability_required"),
            "regime_applicability_required",
        ),
        timing_or_lag_required=_strict_bool(
            graph.get("timing_or_lag_required"),
            "timing_or_lag_required",
        ),
        graph_is_forecast_model=_strict_bool(
            governance.get("graph_is_forecast_model"),
            "graph_is_forecast_model",
        ),
        graph_is_decision_score=_strict_bool(
            governance.get("graph_is_decision_score"),
            "graph_is_decision_score",
        ),
        graph_approves_investability=_strict_bool(
            governance.get("graph_approves_investability"),
            "graph_approves_investability",
        ),
        automatic_execution_enabled=_strict_bool(
            governance.get("automatic_execution_enabled"),
            "automatic_execution_enabled",
        ),
        frozen_skhynix_2026q3_round_changed=_strict_bool(
            governance.get("frozen_skhynix_2026q3_round_changed"),
            "frozen_skhynix_2026q3_round_changed",
        ),
        evidence_id=evidence_id,
        source_policy_evidence_id=source_policy_evidence_id,
    )


def build_semiconductor_causal_graph(
    *,
    graph_id: str,
    snapshot_version: int,
    parent_snapshot_id: str | None,
    captured_at: datetime,
    evaluation_date: str,
    security_id: str | None,
    nodes: tuple[CausalNode, ...],
    edges: tuple[CausalEdge, ...],
    source_snapshot_ids: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    policy: SemiconductorCausalEnginePolicy | None = None,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> SemiconductorCausalGraphSnapshot:
    active_policy = policy or load_semiconductor_causal_engine_policy()
    active_guardrails = guardrails or load_decision_system_v21_guardrails()
    if active_policy.critical_state_variable_max != active_guardrails.critical_state_variable_max:
        raise ValueError("causal-engine and Decision System v2.1 complexity caps disagree")
    critical_states = tuple(CriticalStateVariable(value) for value in EXPECTED_CRITICAL_STATES)
    return SemiconductorCausalGraphSnapshot(
        graph_id=graph_id,
        snapshot_version=snapshot_version,
        parent_snapshot_id=parent_snapshot_id,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        security_id=security_id,
        critical_state_variables=critical_states,
        nodes=nodes,
        edges=edges,
        source_snapshot_ids=source_snapshot_ids,
        policy_evidence_id=active_policy.evidence_id,
        source_policy_evidence_id=active_policy.source_policy_evidence_id,
        guardrail_evidence_id=active_guardrails.evidence_id,
        warnings=warnings,
    )


def persist_semiconductor_causal_graph(
    snapshot: SemiconductorCausalGraphSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    pointer = root / "latest_semiconductor_causal_graph.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot.snapshot_id:
            raise ValueError("existing causal-graph directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            payload = snapshot.payload_without_id()
            manifest = {
                "schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "evaluation_date": snapshot.evaluation_date,
                "sector": "semiconductor",
                "security_id": snapshot.security_id,
                "node_count": len(snapshot.nodes),
                "edge_count": len(snapshot.edges),
                "critical_state_count": len(snapshot.critical_state_variables),
                "policy_evidence_id": snapshot.policy_evidence_id,
                "source_policy_evidence_id": snapshot.source_policy_evidence_id,
                "guardrail_evidence_id": snapshot.guardrail_evidence_id,
                "dag_claimed": False,
                "forecast_generation_enabled": False,
                "decision_score_enabled": False,
                "investability_decision_enabled": False,
                "order_api_enabled": False,
                "files": ["causal_graph.json"],
            }
            (temporary / "causal_graph.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.rename(directory)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
    pointer.write_text(
        json.dumps(
            {
                "schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_path": str(directory),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pointer


def _validate_lineage(snapshot_version: int, parent_snapshot_id: str | None) -> None:
    if snapshot_version <= 0:
        raise ValueError("snapshot_version must be positive")
    if snapshot_version == 1 and parent_snapshot_id is not None:
        raise ValueError("first causal-graph snapshot cannot have a parent")
    if snapshot_version > 1:
        if parent_snapshot_id is None:
            raise ValueError("later causal-graph snapshots require parent_snapshot_id")
        _validate_sha(parent_snapshot_id, "parent_snapshot_id")


def _strict_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a YAML boolean")
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _text_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    result = tuple(_text(item, field) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} cannot contain duplicates")
    return result


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _load_yaml_object(path: Path, label: str) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a YAML object")
    return {str(key): item for key, item in cast(dict[object, object], payload).items()}


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _validate_text_refs(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_unique(values: tuple[str, ...], field: str) -> None:
    _validate_text_refs(values, field)


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    for digest in values:
        _validate_sha(digest, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): item for key, item in cast(dict[object, object], payload).items()}


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CausalEdge",
    "CausalEdgeDirection",
    "CausalNode",
    "CausalNodeType",
    "CriticalStateVariable",
    "SemiconductorCausalEnginePolicy",
    "SemiconductorCausalGraphSnapshot",
    "TransmissionLag",
    "build_semiconductor_causal_graph",
    "load_semiconductor_causal_engine_policy",
    "persist_semiconductor_causal_graph",
]
