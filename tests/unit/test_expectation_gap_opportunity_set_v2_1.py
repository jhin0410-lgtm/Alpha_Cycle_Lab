from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_view_v2_1 import (
    ConsensusGapObservation,
    DecisionExpectationGapSnapshot,
)
from alpha_cycle.intelligence.expectation_gap_opportunity_set_v2_1 import (
    EXPECTATION_AUGMENTED_PARETO_DIMENSIONS,
    ExpectationGapComparisonStatistic,
    build_expectation_augmented_opportunity_set,
    build_expectation_gap_comparison_policy,
    build_expectation_gap_opportunity_candidate,
    persist_expectation_augmented_opportunity_set,
    persist_expectation_gap_comparison_policy,
    persist_expectation_gap_opportunity_candidate,
)
from alpha_cycle.intelligence.expectation_state import ExpectationMetric
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OpportunityCandidateSnapshot,
    OpportunityResearchClass,
    build_opportunity_set,
)

_KST = ZoneInfo("Asia/Seoul")
_GUARDRAILS = load_decision_system_v21_guardrails()
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64


def _base_candidate(
    security_id: str,
    *,
    bear: float,
    base_low: float,
    base_high: float,
    bull: float,
    catalyst_days: int,
) -> OpportunityCandidateSnapshot:
    return OpportunityCandidateSnapshot(
        captured_at=datetime(2026, 8, 22, 16, 30, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        security_id=security_id,
        thesis_snapshot_id=_A,
        underwriting_readiness_snapshot_id=_B,
        payoff_surface_snapshot_id=_C,
        horizon_trading_days=120,
        research_class=OpportunityResearchClass.DEEP_READY,
        bear_return_lower=bear,
        base_return_lower=base_low,
        base_return_upper=base_high,
        bull_return_upper=bull,
        nearest_catalyst_id=f"catalyst-{security_id}",
        nearest_catalyst_days=catalyst_days,
        nearest_catalyst_evidence_refs=(f"evidence:{security_id}",),
        comparison_blockers=(),
        flags=(),
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
    )


def _base_set():
    dominant = _base_candidate(
        "000660",
        bear=-0.10,
        base_low=0.05,
        base_high=0.20,
        bull=0.40,
        catalyst_days=20,
    )
    weaker = _base_candidate(
        "005930",
        bear=-0.15,
        base_low=0.02,
        base_high=0.15,
        bull=0.30,
        catalyst_days=30,
    )
    return build_opportunity_set(
        (dominant, weaker),
        captured_at=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        horizon_trading_days=120,
    )


def _policy(*, registered_at: datetime | None = None):
    return build_expectation_gap_comparison_policy(
        policy_id="fy2026-net-income-provider-a",
        registered_at=registered_at
        or datetime(2026, 8, 22, 15, 0, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        consensus_provider_id="provider-a",
        metric=ExpectationMetric.NET_INCOME,
        target_date=date(2026, 12, 31),
        rationale=(
            "Compare the same certified provider, metric, target date, and relative-gap statistic."
        ),
        source_evidence_ids=(_D,),
    )


def _gap(
    security_id: str,
    relative_gap: float | None,
    *,
    provider_id: str = "provider-a",
    target_variable: str = "net_income",
    target_date: date = date(2026, 12, 31),
    captured_at: datetime | None = None,
) -> DecisionExpectationGapSnapshot:
    consensus_value = 100.0
    absolute_gap = 0.0 if relative_gap is None else relative_gap * consensus_value
    observation = ConsensusGapObservation(
        provider_id=provider_id,
        source_evidence_id=_E,
        observed_at=datetime(2026, 8, 22, 16, 45, tzinfo=_KST),
        decision_value=consensus_value + absolute_gap,
        consensus_value=consensus_value,
        unit="KRW_million",
        absolute_gap=absolute_gap,
        relative_gap=relative_gap,
    )
    return DecisionExpectationGapSnapshot(
        captured_at=captured_at
        or datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        decision_view_snapshot_id=_A,
        expectation_state_snapshot_id=_B,
        price_implied_requirement_snapshot_id=None,
        security_id=security_id,
        target_variable=target_variable,
        target_date=target_date,
        unit="KRW_million",
        consensus_gaps=(observation,),
        price_implied_gaps=(),
        flags=(),
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
    )


def _overlay_candidate(
    security_id: str,
    relative_gap: float | None,
    *,
    base=None,
    policy=None,
    provider_id: str = "provider-a",
    target_variable: str = "net_income",
):
    base_set = base or _base_set()
    comparison_policy = policy or _policy()
    opportunity = next(item for item in base_set.candidates if item.security_id == security_id)
    return build_expectation_gap_opportunity_candidate(
        opportunity,
        _gap(
            security_id,
            relative_gap,
            provider_id=provider_id,
            target_variable=target_variable,
        ),
        comparison_policy,
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
    )


def test_policy_is_preregistered_content_addressed_and_non_scoring() -> None:
    policy = _policy()
    assert policy.statistic is ExpectationGapComparisonStatistic.CONSENSUS_RELATIVE_GAP
    assert len(policy.snapshot_id) == 64
    payload = policy.payload_without_id()
    assert payload["provider_selected_after_gap_inspection"] is False
    assert payload["metric_selected_after_gap_inspection"] is False
    assert payload["price_implied_cross_security_comparison_enabled"] is False
    assert payload["weighted_composite_score_enabled"] is False


def test_candidate_extracts_only_policy_provider_relative_gap() -> None:
    base = _base_set()
    policy = _policy()
    opportunity = next(item for item in base.candidates if item.security_id == "000660")
    primary = ConsensusGapObservation(
        provider_id="provider-a",
        source_evidence_id=_D,
        observed_at=datetime(2026, 8, 22, 16, 40, tzinfo=_KST),
        decision_value=115.0,
        consensus_value=100.0,
        unit="KRW_million",
        absolute_gap=15.0,
        relative_gap=0.15,
    )
    other = ConsensusGapObservation(
        provider_id="provider-b",
        source_evidence_id=_E,
        observed_at=datetime(2026, 8, 22, 16, 41, tzinfo=_KST),
        decision_value=115.0,
        consensus_value=110.0,
        unit="KRW_million",
        absolute_gap=5.0,
        relative_gap=5.0 / 110.0,
    )
    gap = replace(_gap("000660", 0.15), consensus_gaps=(primary, other))
    result = build_expectation_gap_opportunity_candidate(
        opportunity,
        gap,
        policy,
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
    )
    assert result.expectation_gap_comparable is True
    assert result.consensus_provider_id == "provider-a"
    assert result.consensus_relative_gap == pytest.approx(0.15)
    assert result.comparison_blockers == ()
    assert result.payload_without_id()["price_implied_gap_used_for_cross_security_ranking"] is False


def test_policy_must_predate_gap_values() -> None:
    base = _base_set()
    opportunity = next(item for item in base.candidates if item.security_id == "000660")
    late_policy = _policy(
        registered_at=datetime(2026, 8, 22, 17, 0, tzinfo=_KST)
    )
    with pytest.raises(ValueError, match="registered before gap values"):
        build_expectation_gap_opportunity_candidate(
            opportunity,
            _gap("000660", 0.10),
            late_policy,
            captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        )


def test_metric_or_provider_mismatch_blocks_ranking_without_inventing_value() -> None:
    base = _base_set()
    policy = _policy()
    metric_blocked = _overlay_candidate(
        "000660",
        0.10,
        base=base,
        policy=policy,
        target_variable="operating_income",
    )
    provider_blocked = _overlay_candidate(
        "005930",
        0.20,
        base=base,
        policy=policy,
        provider_id="provider-b",
    )
    assert metric_blocked.consensus_relative_gap is None
    assert "expectation_metric_not_policy_comparable" in metric_blocked.comparison_blockers
    assert provider_blocked.consensus_relative_gap is None
    assert "policy_consensus_provider_gap_unavailable" in provider_blocked.comparison_blockers


def test_expectation_gap_can_remove_false_unique_leader_without_weighted_score() -> None:
    base = _base_set()
    assert base.unique_pareto_leader_security_id == "000660"
    policy = _policy()
    first = _overlay_candidate("000660", 0.05, base=base, policy=policy)
    second = _overlay_candidate("005930", 0.15, base=base, policy=policy)
    result = build_expectation_augmented_opportunity_set(
        base,
        policy,
        (first, second),
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
    )
    assert result.pareto_dimensions == EXPECTATION_AUGMENTED_PARETO_DIMENSIONS
    assert result.base_pareto_frontier_security_ids == ("000660",)
    assert result.expectation_pareto_frontier_security_ids == ("000660", "005930")
    assert result.unique_expectation_pareto_leader_security_id is None
    assert "expectation_gap_changes_pareto_frontier" in result.flags
    assert "multiple_expectation_augmented_non_dominated_opportunities" in result.flags
    payload = result.payload_without_id()
    assert payload["base_opportunity_set_replaced"] is False
    assert payload["weighted_composite_score_enabled"] is False
    assert payload["capital_allocation_recommendation_enabled"] is False


def test_unique_leader_survives_when_also_better_on_expectation_gap() -> None:
    base = _base_set()
    policy = _policy()
    first = _overlay_candidate("000660", 0.20, base=base, policy=policy)
    second = _overlay_candidate("005930", 0.15, base=base, policy=policy)
    result = build_expectation_augmented_opportunity_set(
        base,
        policy,
        (first, second),
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
    )
    assert result.expectation_pareto_frontier_security_ids == ("000660",)
    assert result.unique_expectation_pareto_leader_security_id == "000660"
    relation = result.dominance_relations[0]
    assert relation.dominator_security_id == "000660"
    assert "consensus_relative_gap" in relation.strictly_better_dimensions


def test_partial_gap_comparability_does_not_declare_unique_leader() -> None:
    base = _base_set()
    policy = _policy()
    first = _overlay_candidate("000660", 0.20, base=base, policy=policy)
    second = _overlay_candidate(
        "005930",
        0.15,
        base=base,
        policy=policy,
        provider_id="provider-b",
    )
    result = build_expectation_augmented_opportunity_set(
        base,
        policy,
        (first, second),
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
    )
    assert result.expectation_comparable_security_ids == ("000660",)
    assert result.expectation_blocked_security_ids == ("005930",)
    assert result.unique_expectation_pareto_leader_security_id is None
    assert "insufficient_expectation_comparable_candidates" in result.flags
    assert "partial_expectation_gap_comparability" in result.flags


def test_overlay_rejects_silent_omission_or_substitution_of_base_candidates() -> None:
    base = _base_set()
    policy = _policy()
    first = _overlay_candidate("000660", 0.20, base=base, policy=policy)
    substituted = replace(
        _overlay_candidate("005930", 0.15, base=base, policy=policy),
        security_id="999999",
    )
    with pytest.raises(ValueError, match="every and only base-comparable security"):
        build_expectation_augmented_opportunity_set(
            base,
            policy,
            (first, substituted),
            captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        )


def test_expectation_overlay_artifacts_persist_immutably(tmp_path) -> None:
    base = _base_set()
    policy = _policy()
    first = _overlay_candidate("000660", 0.20, base=base, policy=policy)
    second = _overlay_candidate("005930", 0.15, base=base, policy=policy)
    overlay = build_expectation_augmented_opportunity_set(
        base,
        policy,
        (first, second),
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
    )
    pointers = (
        (persist_expectation_gap_comparison_policy(policy, output_root=tmp_path), policy.snapshot_id),
        (
            persist_expectation_gap_opportunity_candidate(first, output_root=tmp_path),
            first.snapshot_id,
        ),
        (
            persist_expectation_augmented_opportunity_set(overlay, output_root=tmp_path),
            overlay.snapshot_id,
        ),
    )
    for pointer, expected_id in pointers:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        assert payload["snapshot_id"] == expected_id
        snapshot_dir = tmp_path / payload["object_type"] / Path(payload["snapshot_path"]).name
        manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["immutable"] is True
        assert manifest["weighted_composite_score_enabled"] is False
        assert manifest["target_price_enabled"] is False
        assert manifest["capital_allocation_recommendation_enabled"] is False
        assert manifest["automatic_execution_enabled"] is False
