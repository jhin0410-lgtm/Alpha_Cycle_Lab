from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DEFAULT_DECISION_SYSTEM_V21_GUARDRAILS,
    EXPECTED_ATTRIBUTION_LAYERS,
    EXPECTED_CORRECTNESS_EXCEPTIONS,
    EXPECTED_DEEP_ELEMENTS,
    EXPECTED_DEEP_STATUSES,
    EXPECTED_FAST_ELEMENTS,
    EXPECTED_FAST_STATUSES,
    EXPECTED_PERFORMANCE_VECTOR,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import load_decision_system_v2_policy


def _payload() -> dict[str, object]:
    payload = yaml.safe_load(
        DEFAULT_DECISION_SYSTEM_V21_GUARDRAILS.read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    return payload


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "guardrails.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _section(payload: dict[str, object], *keys: str) -> dict[str, object]:
    current: object = payload
    for key in keys:
        assert isinstance(current, dict)
        current = current[key]
    assert isinstance(current, dict)
    return current


def test_v21_guardrails_bind_exact_frozen_v2_predecessor() -> None:
    guardrails = load_decision_system_v21_guardrails()
    predecessor = load_decision_system_v2_policy()
    assert guardrails.predecessor_policy_evidence_id == predecessor.evidence_id
    assert not guardrails.predecessor_rewrite_allowed
    assert not guardrails.historical_policy_rewrite_allowed
    assert not guardrails.frozen_skhynix_2026q3_round_changed


def test_v21_guardrails_freeze_epistemic_complexity_and_forecast_contract() -> None:
    guardrails = load_decision_system_v21_guardrails()
    assert guardrails.independent_counter_thesis_required_for_investable
    assert guardrails.counter_thesis_created_without_support_search_required
    assert guardrails.outside_graph_discovery_required_for_investable
    assert guardrails.unresolved_contradictions_must_be_preserved
    assert guardrails.critical_state_variable_max == 5
    assert not guardrails.evidence_node_count_capped
    assert guardrails.forecast_preregistration_required_for_decision_relevant_forecast
    assert guardrails.forecast_registration_and_outcome_snapshots_separate
    assert guardrails.forecast_registration_immutable
    assert guardrails.forecast_dependency_cluster_required
    assert guardrails.forecast_performance_vector_dimensions == EXPECTED_PERFORMANCE_VECTOR
    assert not guardrails.composite_forecast_score_enabled


def test_v21_guardrails_freeze_fast_deep_lane_and_attribution_contract() -> None:
    guardrails = load_decision_system_v21_guardrails()
    assert guardrails.fast_lane_allowed_thesis_statuses == EXPECTED_FAST_STATUSES
    assert guardrails.fast_lane_required_elements == EXPECTED_FAST_ELEMENTS
    assert guardrails.fast_lane_small_exploratory_position_human_review_only
    assert not guardrails.fast_lane_automatic_execution_enabled
    assert guardrails.deep_lane_required_for_thesis_statuses == EXPECTED_DEEP_STATUSES
    assert guardrails.deep_lane_required_elements == EXPECTED_DEEP_ELEMENTS
    assert guardrails.decision_outcome_separate_snapshots_required
    assert not guardrails.mutable_decision_outcome_row_allowed
    assert guardrails.attribution_required_diagnostic_layers == EXPECTED_ATTRIBUTION_LAYERS
    assert not guardrails.causal_claim_from_residual_attribution_allowed
    assert guardrails.architecture_correctness_exception_classes == EXPECTED_CORRECTNESS_EXCEPTIONS
    assert guardrails.forward_valuation_revalidation_required_after_guardrail_merge


@pytest.mark.parametrize(
    ("section_path", "field"),
    [
        (("predecessor",), "rewrite_allowed"),
        (
            ("epistemic_guardrails",),
            "independent_counter_thesis_required_for_investable",
        ),
        (
            ("epistemic_guardrails",),
            "outside_graph_discovery_required_for_investable",
        ),
        (
            ("forecast_governance",),
            "preregistration_required_for_decision_relevant_forecast",
        ),
        (("research_lanes", "fast"), "automatic_execution_enabled"),
        (("decision_outcome",), "separate_snapshots_required"),
        (("architecture_learning",), "historical_policy_rewrite_allowed"),
        (("migration",), "frozen_skhynix_2026q3_round_changed"),
    ],
)
def test_v21_guardrails_reject_quoted_booleans(
    tmp_path: Path,
    section_path: tuple[str, ...],
    field: str,
) -> None:
    payload = _payload()
    policy = _section(payload, "successor_policy")
    target = _section(policy, *section_path)
    target[field] = "false"
    with pytest.raises(ValueError, match=f"{field} must be a YAML boolean"):
        load_decision_system_v21_guardrails(_write(tmp_path, payload))


def test_v21_guardrails_reject_complexity_budget_drift(tmp_path: Path) -> None:
    payload = _payload()
    complexity = _section(payload, "successor_policy", "complexity")
    complexity["critical_state_variable_max"] = 6
    with pytest.raises(ValueError, match="five critical state variables"):
        load_decision_system_v21_guardrails(_write(tmp_path, payload))


def test_v21_guardrails_reject_forecast_performance_composite(tmp_path: Path) -> None:
    payload = _payload()
    forecast = _section(payload, "successor_policy", "forecast_governance")
    forecast["composite_forecast_score_enabled"] = True
    with pytest.raises(ValueError, match="Composite forecast scoring"):
        load_decision_system_v21_guardrails(_write(tmp_path, payload))


def test_v21_guardrails_reject_deep_lane_demotion(tmp_path: Path) -> None:
    payload = _payload()
    deep = _section(payload, "successor_policy", "research_lanes", "deep")
    deep["required_for_thesis_statuses"] = ["underwriting"]
    with pytest.raises(ValueError, match="mandatory for investable_now"):
        load_decision_system_v21_guardrails(_write(tmp_path, payload))


def test_v21_guardrails_reject_predecessor_evidence_drift(tmp_path: Path) -> None:
    payload = _payload()
    predecessor = _section(payload, "successor_policy", "predecessor")
    predecessor["policy_evidence_id"] = "0" * 64
    with pytest.raises(ValueError, match="no longer matches"):
        load_decision_system_v21_guardrails(_write(tmp_path, payload))
