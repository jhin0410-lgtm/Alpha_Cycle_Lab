"""Fail-closed successor guardrails for Alpha Cycle Lab Decision System v2.1.

This module does not rewrite the frozen v2 architecture. It binds a successor policy that
adds epistemic defense, forecast-governance, research-lane, attribution, and architecture-
learning requirements before deeper v2 integration proceeds.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.intelligence.decision_thesis_v2 import load_decision_system_v2_policy

DEFAULT_DECISION_SYSTEM_V21_GUARDRAILS = Path(
    "config/decision_system_v2_1_guardrails.v1.yaml"
)

EXPECTED_POLICY_ID = "alpha_cycle_decision_system_v2_1_guardrails"
EXPECTED_POLICY_VERSION = "2.1-epistemic-guardrail-freeze"
EXPECTED_STATUS = "successor_guardrails_frozen_before_forward_valuation_merge"
EXPECTED_PREDECESSOR_POLICY_ID = "alpha_cycle_decision_system_v2"
EXPECTED_PREDECESSOR_POLICY_VERSION = "1.0-architecture-freeze"
EXPECTED_PERFORMANCE_VECTOR = (
    "accuracy",
    "calibration",
    "decision_relevance",
    "information_gain",
    "difficulty",
)
EXPECTED_FAST_STATUSES = ("research_priority", "underwriting")
EXPECTED_FAST_ELEMENTS = (
    "why_now",
    "catalyst",
    "transmission",
    "expectation_or_priced_in_assessment",
    "top_downside",
    "counter_thesis",
    "kill_condition",
    "position_uncertainty",
)
EXPECTED_DEEP_STATUSES = ("investable_now",)
EXPECTED_DEEP_ELEMENTS = (
    "full_causal_graph",
    "forecast_tournament",
    "certified_expectation",
    "valuation",
    "payoff_surface",
    "counter_thesis",
    "outside_graph_scan",
    "opportunity_set_comparison",
    "portfolio_overlap",
)
EXPECTED_ATTRIBUTION_LAYERS = (
    "market",
    "sector_theme",
    "factor_regime",
    "security_specific",
)
EXPECTED_CORRECTNESS_EXCEPTIONS = (
    "look_ahead_bug",
    "provenance_violation",
    "accounting_error",
    "security_or_safety_defect",
)


@dataclass(frozen=True)
class DecisionSystemV21Guardrails:
    """Successor policy contract frozen before further v2 integration."""

    policy_id: str
    policy_version: str
    status: str
    predecessor_policy_path: str
    predecessor_policy_id: str
    predecessor_policy_version: str
    predecessor_policy_evidence_id: str
    predecessor_rewrite_allowed: bool
    independent_counter_thesis_required_for_investable: bool
    counter_thesis_created_without_support_search_required: bool
    outside_graph_discovery_required_for_investable: bool
    unresolved_contradictions_must_be_preserved: bool
    critical_state_variable_max: int
    evidence_node_count_capped: bool
    forecast_preregistration_required_for_decision_relevant_forecast: bool
    forecast_registration_and_outcome_snapshots_separate: bool
    forecast_registration_immutable: bool
    forecast_dependency_cluster_required: bool
    forecast_performance_vector_dimensions: tuple[str, ...]
    composite_forecast_score_enabled: bool
    fast_lane_allowed_thesis_statuses: tuple[str, ...]
    fast_lane_small_exploratory_position_human_review_only: bool
    fast_lane_automatic_execution_enabled: bool
    fast_lane_required_elements: tuple[str, ...]
    deep_lane_required_for_thesis_statuses: tuple[str, ...]
    deep_lane_required_elements: tuple[str, ...]
    decision_outcome_separate_snapshots_required: bool
    mutable_decision_outcome_row_allowed: bool
    attribution_required_diagnostic_layers: tuple[str, ...]
    causal_claim_from_residual_attribution_allowed: bool
    architecture_change_proposal_required: bool
    single_trade_outcome_may_change_architecture_invariant: bool
    architecture_correctness_exception_classes: tuple[str, ...]
    historical_policy_rewrite_allowed: bool
    forward_valuation_revalidation_required_after_guardrail_merge: bool
    frozen_skhynix_2026q3_round_changed: bool
    evidence_id: str

    def __post_init__(self) -> None:
        if self.policy_id != EXPECTED_POLICY_ID:
            raise ValueError("Unexpected Decision System v2.1 policy id")
        if self.policy_version != EXPECTED_POLICY_VERSION:
            raise ValueError("Unexpected Decision System v2.1 policy version")
        if self.status != EXPECTED_STATUS:
            raise ValueError("Unexpected Decision System v2.1 policy status")
        if self.predecessor_policy_id != EXPECTED_PREDECESSOR_POLICY_ID:
            raise ValueError("Unexpected predecessor policy id")
        if self.predecessor_policy_version != EXPECTED_PREDECESSOR_POLICY_VERSION:
            raise ValueError("Unexpected predecessor policy version")
        _validate_sha(
            self.predecessor_policy_evidence_id,
            "predecessor_policy_evidence_id",
        )
        if self.predecessor_rewrite_allowed:
            raise ValueError("The frozen v2 predecessor policy cannot be rewritten")
        if not self.independent_counter_thesis_required_for_investable:
            raise ValueError("Investable theses require an independent counter-thesis")
        if not self.counter_thesis_created_without_support_search_required:
            raise ValueError("Counter-thesis construction must be independent of support search")
        if not self.outside_graph_discovery_required_for_investable:
            raise ValueError("Investable theses require outside-graph discovery")
        if not self.unresolved_contradictions_must_be_preserved:
            raise ValueError("Unresolved contradictions must remain visible")
        if self.critical_state_variable_max != 5:
            raise ValueError("Decision complexity is capped at five critical state variables")
        if self.evidence_node_count_capped:
            raise ValueError(
                "Evidence-node count must not be capped by the decision complexity budget"
            )
        if not self.forecast_preregistration_required_for_decision_relevant_forecast:
            raise ValueError("Decision-relevant forecasts require preregistration")
        if not self.forecast_registration_and_outcome_snapshots_separate:
            raise ValueError("Forecast registration and outcome snapshots must remain separate")
        if not self.forecast_registration_immutable:
            raise ValueError("Forecast registration must remain immutable")
        if not self.forecast_dependency_cluster_required:
            raise ValueError("Forecasts must declare a dependency cluster")
        if self.forecast_performance_vector_dimensions != EXPECTED_PERFORMANCE_VECTOR:
            raise ValueError("Forecast performance must remain a non-composite diagnostic vector")
        if self.composite_forecast_score_enabled:
            raise ValueError("Composite forecast scoring is prohibited before calibration")
        if self.fast_lane_allowed_thesis_statuses != EXPECTED_FAST_STATUSES:
            raise ValueError("Unexpected fast-lane thesis statuses")
        if not self.fast_lane_small_exploratory_position_human_review_only:
            raise ValueError("Fast-lane exploratory exposure must remain human-review-only")
        if self.fast_lane_automatic_execution_enabled:
            raise ValueError("Fast lane cannot enable automatic execution")
        if self.fast_lane_required_elements != EXPECTED_FAST_ELEMENTS:
            raise ValueError("Unexpected fast-lane minimum evidence contract")
        if self.deep_lane_required_for_thesis_statuses != EXPECTED_DEEP_STATUSES:
            raise ValueError("Deep lane must remain mandatory for investable_now")
        if self.deep_lane_required_elements != EXPECTED_DEEP_ELEMENTS:
            raise ValueError("Unexpected deep-lane minimum evidence contract")
        if not self.decision_outcome_separate_snapshots_required:
            raise ValueError("Decision and outcome snapshots must remain separate")
        if self.mutable_decision_outcome_row_allowed:
            raise ValueError("Mutable decision/outcome rows are prohibited")
        if self.attribution_required_diagnostic_layers != EXPECTED_ATTRIBUTION_LAYERS:
            raise ValueError("Unexpected attribution decomposition")
        if self.causal_claim_from_residual_attribution_allowed:
            raise ValueError("Diagnostic residual attribution cannot be promoted to causal proof")
        if not self.architecture_change_proposal_required:
            raise ValueError("Architecture changes require explicit proposals")
        if self.single_trade_outcome_may_change_architecture_invariant:
            raise ValueError("A single trade outcome cannot change architecture invariants")
        if self.architecture_correctness_exception_classes != EXPECTED_CORRECTNESS_EXCEPTIONS:
            raise ValueError("Unexpected architecture correctness exceptions")
        if self.historical_policy_rewrite_allowed:
            raise ValueError("Historical policy rewriting is prohibited")
        if not self.forward_valuation_revalidation_required_after_guardrail_merge:
            raise ValueError("Forward valuation must be revalidated after the guardrail merge")
        if self.frozen_skhynix_2026q3_round_changed:
            raise ValueError("v2.1 cannot alter the frozen SK hynix 2026Q3 research round")
        _validate_sha(self.evidence_id, "guardrail evidence_id")


def load_decision_system_v21_guardrails(
    path: str | Path = DEFAULT_DECISION_SYSTEM_V21_GUARDRAILS,
) -> DecisionSystemV21Guardrails:
    """Load the successor guardrail policy and bind it to the frozen v2 predecessor."""

    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Decision System v2.1 guardrail policy must be a YAML object")
    root = cast(dict[str, object], payload)
    if root.get("schema_version") != 1:
        raise ValueError("Unexpected Decision System v2.1 guardrail schema_version")
    raw_policy = root.get("successor_policy")
    if not isinstance(raw_policy, dict):
        raise ValueError("Decision System v2.1 policy must contain successor_policy")
    policy = _mapping(raw_policy, "successor_policy")

    predecessor = _mapping(policy.get("predecessor"), "predecessor")
    epistemic = _mapping(policy.get("epistemic_guardrails"), "epistemic_guardrails")
    complexity = _mapping(policy.get("complexity"), "complexity")
    forecast = _mapping(policy.get("forecast_governance"), "forecast_governance")
    lanes = _mapping(policy.get("research_lanes"), "research_lanes")
    fast = _mapping(lanes.get("fast"), "research_lanes.fast")
    deep = _mapping(lanes.get("deep"), "research_lanes.deep")
    decision_outcome = _mapping(policy.get("decision_outcome"), "decision_outcome")
    attribution = _mapping(policy.get("attribution"), "attribution")
    learning = _mapping(policy.get("architecture_learning"), "architecture_learning")
    migration = _mapping(policy.get("migration"), "migration")

    predecessor_path = _text_field(predecessor, "policy_path")
    predecessor_policy = load_decision_system_v2_policy(predecessor_path)
    pinned_predecessor_evidence_id = _text_field(predecessor, "policy_evidence_id")
    _validate_sha(pinned_predecessor_evidence_id, "predecessor.policy_evidence_id")
    if predecessor_policy.evidence_id != pinned_predecessor_evidence_id:
        raise ValueError("Frozen predecessor policy evidence id no longer matches v2.1 pin")

    result = DecisionSystemV21Guardrails(
        policy_id=_text_field(policy, "policy_id"),
        policy_version=_text_field(policy, "policy_version"),
        status=_text_field(policy, "status"),
        predecessor_policy_path=predecessor_path,
        predecessor_policy_id=_text_field(predecessor, "policy_id"),
        predecessor_policy_version=_text_field(predecessor, "policy_version"),
        predecessor_policy_evidence_id=pinned_predecessor_evidence_id,
        predecessor_rewrite_allowed=_bool_field(predecessor, "rewrite_allowed"),
        independent_counter_thesis_required_for_investable=_bool_field(
            epistemic,
            "independent_counter_thesis_required_for_investable",
        ),
        counter_thesis_created_without_support_search_required=_bool_field(
            epistemic,
            "counter_thesis_created_without_support_search_required",
        ),
        outside_graph_discovery_required_for_investable=_bool_field(
            epistemic,
            "outside_graph_discovery_required_for_investable",
        ),
        unresolved_contradictions_must_be_preserved=_bool_field(
            epistemic,
            "unresolved_contradictions_must_be_preserved",
        ),
        critical_state_variable_max=_positive_int_field(
            complexity,
            "critical_state_variable_max",
        ),
        evidence_node_count_capped=_bool_field(complexity, "evidence_node_count_capped"),
        forecast_preregistration_required_for_decision_relevant_forecast=_bool_field(
            forecast,
            "preregistration_required_for_decision_relevant_forecast",
        ),
        forecast_registration_and_outcome_snapshots_separate=_bool_field(
            forecast,
            "registration_and_outcome_snapshots_separate",
        ),
        forecast_registration_immutable=_bool_field(
            forecast,
            "registration_immutable",
        ),
        forecast_dependency_cluster_required=_bool_field(
            forecast,
            "dependency_cluster_required",
        ),
        forecast_performance_vector_dimensions=_string_tuple(
            forecast.get("performance_vector_dimensions"),
            "forecast_governance.performance_vector_dimensions",
        ),
        composite_forecast_score_enabled=_bool_field(
            forecast,
            "composite_forecast_score_enabled",
        ),
        fast_lane_allowed_thesis_statuses=_string_tuple(
            fast.get("allowed_thesis_statuses"),
            "research_lanes.fast.allowed_thesis_statuses",
        ),
        fast_lane_small_exploratory_position_human_review_only=_bool_field(
            fast,
            "small_exploratory_position_human_review_only",
        ),
        fast_lane_automatic_execution_enabled=_bool_field(
            fast,
            "automatic_execution_enabled",
        ),
        fast_lane_required_elements=_string_tuple(
            fast.get("required_elements"),
            "research_lanes.fast.required_elements",
        ),
        deep_lane_required_for_thesis_statuses=_string_tuple(
            deep.get("required_for_thesis_statuses"),
            "research_lanes.deep.required_for_thesis_statuses",
        ),
        deep_lane_required_elements=_string_tuple(
            deep.get("required_elements"),
            "research_lanes.deep.required_elements",
        ),
        decision_outcome_separate_snapshots_required=_bool_field(
            decision_outcome,
            "separate_snapshots_required",
        ),
        mutable_decision_outcome_row_allowed=_bool_field(
            decision_outcome,
            "mutable_combined_row_allowed",
        ),
        attribution_required_diagnostic_layers=_string_tuple(
            attribution.get("required_diagnostic_layers"),
            "attribution.required_diagnostic_layers",
        ),
        causal_claim_from_residual_attribution_allowed=_bool_field(
            attribution,
            "causal_claim_from_residual_attribution_allowed",
        ),
        architecture_change_proposal_required=_bool_field(
            learning,
            "change_proposal_required",
        ),
        single_trade_outcome_may_change_architecture_invariant=_bool_field(
            learning,
            "single_trade_outcome_may_change_architecture_invariant",
        ),
        architecture_correctness_exception_classes=_string_tuple(
            learning.get("correctness_exception_classes"),
            "architecture_learning.correctness_exception_classes",
        ),
        historical_policy_rewrite_allowed=_bool_field(
            learning,
            "historical_policy_rewrite_allowed",
        ),
        forward_valuation_revalidation_required_after_guardrail_merge=_bool_field(
            migration,
            "forward_valuation_revalidation_required_after_guardrail_merge",
        ),
        frozen_skhynix_2026q3_round_changed=_bool_field(
            migration,
            "frozen_skhynix_2026q3_round_changed",
        ),
        evidence_id=_sha(root),
    )
    if predecessor_policy.policy_id != result.predecessor_policy_id:
        raise ValueError("Loaded predecessor policy id differs from successor declaration")
    if predecessor_policy.policy_version != result.predecessor_policy_version:
        raise ValueError("Loaded predecessor policy version differs from successor declaration")
    return result


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _text_field(mapping: dict[str, object], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _bool_field(mapping: dict[str, object], field: str) -> bool:
    value = mapping.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a YAML boolean")
    return value


def _positive_int_field(mapping: dict[str, object], field: str) -> int:
    value = mapping.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise ValueError(f"{field} cannot contain blank values")
    if len(set(result)) != len(result):
        raise ValueError(f"{field} cannot contain duplicates")
    return result


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
