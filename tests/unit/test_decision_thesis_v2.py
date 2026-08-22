from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from alpha_cycle.intelligence.decision_thesis_v2 import (
    DEFAULT_DECISION_SYSTEM_V2_POLICY,
    CatalystClock,
    ClaimDirection,
    EpistemicStatus,
    InvestmentThesisSnapshot,
    ThesisClaim,
    ThesisStatus,
    ThesisUncertainty,
    UncertaintyDimension,
    UncertaintyLevel,
    load_decision_system_v2_policy,
)

_KST = ZoneInfo("Asia/Seoul")


def _uncertainty() -> ThesisUncertainty:
    return ThesisUncertainty(
        evidence=UncertaintyDimension(
            UncertaintyLevel.LOW,
            "Primary-source evidence is bound.",
        ),
        model=UncertaintyDimension(
            UncertaintyLevel.HIGH,
            "Forecast history is still shallow.",
        ),
        regime=UncertaintyDimension(
            UncertaintyLevel.HIGH,
            "Current scale may be structurally new.",
        ),
        expectation=UncertaintyDimension(
            UncertaintyLevel.UNKNOWN,
            "Certified point-in-time consensus is not yet available.",
        ),
        catalyst=UncertaintyDimension(
            UncertaintyLevel.MEDIUM,
            "The event is observable but its market impact is uncertain.",
        ),
        valuation=UncertaintyDimension(
            UncertaintyLevel.UNKNOWN,
            "Forward valuation is not yet bound to certified expectations.",
        ),
    )


def _claim() -> ThesisClaim:
    return ThesisClaim(
        claim_id="industry-memory-pricing",
        category="industry_cycle",
        statement="Memory pricing is improving relative to the prior observed state.",
        epistemic_status=EpistemicStatus.OBSERVED_FACT,
        direction=ClaimDirection.POSITIVE,
        evidence_refs=("evidence:memory-pricing:2026-08-22",),
    )


def _expectation_claim() -> ThesisClaim:
    return ThesisClaim(
        claim_id="market-expectation-fy2026",
        category="market_expectation",
        statement="The certified FY2026 expectation is below the thesis base case.",
        epistemic_status=EpistemicStatus.OBSERVED_FACT,
        direction=ClaimDirection.NEUTRAL,
        evidence_refs=("expectation-state:fy2026:2026-08-22",),
    )


def _snapshot(**overrides: object) -> InvestmentThesisSnapshot:
    values: dict[str, object] = {
        "thesis_id": "000660-memory-cycle-v1",
        "snapshot_version": 1,
        "parent_snapshot_id": None,
        "captured_at": datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        "security_id": "000660",
        "horizon_trading_days": 120,
        "variant_view": "Earnings revisions may lag the industry-cycle inflection.",
        "why_now": "Industry evidence changed before the next major earnings catalyst.",
        "claims": (_claim(),),
        "catalysts": (
            CatalystClock(
                catalyst_id="next-quarterly-filing",
                statement="Next official quarterly filing tests earnings transmission.",
                evidence_refs=("evidence:filing-calendar",),
                earliest_date=date(2026, 10, 1),
                latest_date=date(2026, 11, 16),
            ),
        ),
        "forecast_refs": ("forecast:skhynix-q3-gp",),
        "scenario_refs": (),
        "uncertainty": _uncertainty(),
        "kill_conditions": ("Memory pricing rolls over while supply expands.",),
        "first_rejection_risk": "The cycle improvement may already be fully priced.",
        "portfolio_overlap": ("memory-upcycle",),
        "opportunity_set_refs": ("opportunity-set:2026-08-22",),
        "status": ThesisStatus.UNDERWRITING,
    }
    values.update(overrides)
    return InvestmentThesisSnapshot(**values)  # type: ignore[arg-type]


def _investable(**overrides: object) -> InvestmentThesisSnapshot:
    values: dict[str, object] = {
        "status": ThesisStatus.INVESTABLE_NOW,
        "claims": (_claim(), _expectation_claim()),
        "scenario_refs": ("scenario:bull-base-bear:2026-08-22",),
    }
    values.update(overrides)
    return _snapshot(**values)


def _policy_payload() -> dict[str, object]:
    payload = yaml.safe_load(DEFAULT_DECISION_SYSTEM_V2_POLICY.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_policy(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_policy_freezes_all_governance_and_migration_invariants() -> None:
    policy = load_decision_system_v2_policy()
    assert policy.primary_horizons == (60, 120, 250)
    assert policy.supporting_horizons == (1, 5, 20)
    assert not policy.exact_calendar_equivalence_claimed
    assert policy.point_in_time_required
    assert policy.revision_lineage_required_when_source_can_revise
    assert policy.protected_outcome_rule_must_be_frozen_before_scoring
    assert not policy.post_outcome_thesis_rewrite_allowed
    assert policy.successor_model_requires_new_research_round
    assert not policy.uncertified_provider_semantics_may_be_promoted_to_consensus
    assert not policy.missing_evidence_may_be_replaced_with_neutral_score
    assert policy.provenance_effort_must_be_proportional_to_economic_importance
    assert policy.explicit_portfolio_overlap_required_for_investable_thesis
    assert policy.opportunity_cost_comparison_required_for_investable_thesis
    assert not policy.existing_decision_scorecard_removed
    assert policy.existing_scorecard_role == "backward_compatibility_and_diagnostic"
    assert not policy.v2_thesis_integrated_into_existing_decision_snapshot
    assert not policy.skhynix_2026q3_frozen_research_round_changed
    assert not policy.automatic_order_execution_enabled
    assert not policy.unconstrained_kelly_sizing_enabled
    assert not policy.mathematically_optimal_weight_claim_enabled
    assert len(policy.evidence_id) == 64


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("horizons", "exact_calendar_equivalence_claimed"),
        ("portfolio_policy", "automatic_order_execution_enabled"),
        ("portfolio_policy", "explicit_portfolio_overlap_required_for_investable_thesis"),
        ("research_governance", "point_in_time_required"),
        ("research_governance", "revision_lineage_required_when_source_can_revise"),
        ("research_governance", "protected_outcome_rule_must_be_frozen_before_scoring"),
        ("research_governance", "uncertified_provider_semantics_may_be_promoted_to_consensus"),
        ("research_governance", "missing_evidence_may_be_replaced_with_neutral_score"),
        ("migration", "existing_decision_scorecard_removed"),
        ("migration", "v2_thesis_integrated_into_existing_decision_snapshot"),
        ("migration", "skhynix_2026q3_frozen_research_round_changed"),
    ],
)
def test_policy_rejects_quoted_boolean_values(
    tmp_path: Path,
    section: str,
    field: str,
) -> None:
    payload = _policy_payload()
    policy = payload["policy"]
    assert isinstance(policy, dict)
    target = policy[section]
    assert isinstance(target, dict)
    target[field] = "false"
    with pytest.raises(ValueError, match=f"{field} must be a YAML boolean"):
        load_decision_system_v2_policy(_write_policy(tmp_path, payload))


@pytest.mark.parametrize(
    ("section", "field", "invalid_value"),
    [
        ("horizons", "exact_calendar_equivalence_claimed", True),
        ("portfolio_policy", "automatic_order_execution_enabled", True),
        ("portfolio_policy", "unconstrained_kelly_sizing_enabled", True),
        ("portfolio_policy", "mathematically_optimal_weight_claim_enabled", True),
        (
            "portfolio_policy",
            "explicit_portfolio_overlap_required_for_investable_thesis",
            False,
        ),
        (
            "portfolio_policy",
            "opportunity_cost_comparison_required_for_investable_thesis",
            False,
        ),
        ("research_governance", "point_in_time_required", False),
        ("research_governance", "revision_lineage_required_when_source_can_revise", False),
        (
            "research_governance",
            "protected_outcome_rule_must_be_frozen_before_scoring",
            False,
        ),
        ("research_governance", "post_outcome_thesis_rewrite_allowed", True),
        ("research_governance", "successor_model_requires_new_research_round", False),
        (
            "research_governance",
            "uncertified_provider_semantics_may_be_promoted_to_consensus",
            True,
        ),
        (
            "research_governance",
            "missing_evidence_may_be_replaced_with_neutral_score",
            True,
        ),
        (
            "research_governance",
            "provenance_effort_must_be_proportional_to_economic_importance",
            False,
        ),
        ("migration", "existing_decision_scorecard_removed", True),
        ("migration", "v2_thesis_integrated_into_existing_decision_snapshot", True),
        ("migration", "skhynix_2026q3_frozen_research_round_changed", True),
    ],
)
def test_policy_fails_closed_when_frozen_boolean_invariant_drifts(
    tmp_path: Path,
    section: str,
    field: str,
    invalid_value: bool,
) -> None:
    payload = _policy_payload()
    policy = payload["policy"]
    assert isinstance(policy, dict)
    target = policy[section]
    assert isinstance(target, dict)
    target[field] = invalid_value
    with pytest.raises(ValueError):
        load_decision_system_v2_policy(_write_policy(tmp_path, payload))


def test_observed_fact_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires at least one evidence reference"):
        replace(_claim(), evidence_refs=())


def test_hypothesis_can_exist_without_certified_evidence_but_remains_labeled() -> None:
    claim = ThesisClaim(
        claim_id="hypothesis",
        category="company_transmission",
        statement="Improving mix may expand margin.",
        epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
        direction=ClaimDirection.POSITIVE,
    )
    assert claim.evidence_refs == ()
    assert claim.epistemic_status is EpistemicStatus.ECONOMIC_HYPOTHESIS


def test_catalyst_requires_date_window_or_condition() -> None:
    with pytest.raises(ValueError, match="date window or an explicit condition"):
        CatalystClock(
            catalyst_id="undated-story",
            statement="Narrative catalyst without timing evidence.",
            evidence_refs=("evidence:story",),
        )


def test_snapshot_is_content_addressed_and_immutable_by_version() -> None:
    first = _snapshot()
    assert first.snapshot_id == _snapshot().snapshot_id
    second = _snapshot(
        snapshot_version=2,
        parent_snapshot_id=first.snapshot_id,
        captured_at=datetime(2026, 8, 29, 17, 0, tzinfo=_KST),
        why_now="New evidence changed the thesis state.",
    )
    assert second.parent_snapshot_id == first.snapshot_id
    assert second.snapshot_id != first.snapshot_id


def test_later_snapshot_requires_content_addressed_parent() -> None:
    with pytest.raises(ValueError, match="require parent_snapshot_id"):
        _snapshot(snapshot_version=2)
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _snapshot(snapshot_version=2, parent_snapshot_id="not-a-sha")


def test_primary_thesis_horizon_is_limited_to_three_six_twelve_month_policy() -> None:
    with pytest.raises(ValueError, match="60, 120, or 250"):
        _snapshot(horizon_trading_days=20)


def test_investable_thesis_requires_existing_core_decision_context() -> None:
    with pytest.raises(ValueError, match="kill condition"):
        _investable(kill_conditions=())
    with pytest.raises(ValueError, match="opportunity-set comparison"):
        _investable(opportunity_set_refs=())
    with pytest.raises(ValueError, match="portfolio-overlap assessment"):
        _investable(portfolio_overlap=())


def test_investable_thesis_requires_catalyst_payoff_and_expectation() -> None:
    with pytest.raises(ValueError, match="catalyst clock"):
        _investable(catalysts=())
    with pytest.raises(ValueError, match="payoff scenario"):
        _investable(scenario_refs=())
    with pytest.raises(ValueError, match="market-expectation claim"):
        _investable(claims=(_claim(),))
    with pytest.raises(ValueError, match="requires at least one evidence reference"):
        _investable(claims=(_claim(), replace(_expectation_claim(), evidence_refs=())))


def test_investable_thesis_passes_when_all_frozen_requirements_are_present() -> None:
    ready = _investable()
    assert ready.status is ThesisStatus.INVESTABLE_NOW
