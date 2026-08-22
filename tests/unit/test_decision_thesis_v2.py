from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.decision_thesis_v2 import (
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
        evidence=UncertaintyDimension(UncertaintyLevel.LOW, "Primary-source evidence is bound."),
        model=UncertaintyDimension(UncertaintyLevel.HIGH, "Forecast history is still shallow."),
        regime=UncertaintyDimension(UncertaintyLevel.HIGH, "Current scale may be structurally new."),
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


def test_policy_freezes_horizons_and_preserves_skhynix_round() -> None:
    policy = load_decision_system_v2_policy()
    assert policy.primary_horizons == (60, 120, 250)
    assert policy.supporting_horizons == (1, 5, 20)
    assert policy.point_in_time_required
    assert not policy.post_outcome_thesis_rewrite_allowed
    assert policy.successor_model_requires_new_research_round
    assert not policy.skhynix_2026q3_frozen_research_round_changed
    assert not policy.automatic_order_execution_enabled
    assert not policy.unconstrained_kelly_sizing_enabled
    assert not policy.mathematically_optimal_weight_claim_enabled
    assert len(policy.evidence_id) == 64


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


def test_investable_thesis_requires_kill_overlap_and_opportunity_cost_context() -> None:
    with pytest.raises(ValueError, match="kill condition"):
        _snapshot(status=ThesisStatus.INVESTABLE_NOW, kill_conditions=())
    with pytest.raises(ValueError, match="opportunity-set comparison"):
        _snapshot(status=ThesisStatus.INVESTABLE_NOW, opportunity_set_refs=())
    with pytest.raises(ValueError, match="portfolio-overlap assessment"):
        _snapshot(status=ThesisStatus.INVESTABLE_NOW, portfolio_overlap=())
    ready = _snapshot(status=ThesisStatus.INVESTABLE_NOW)
    assert ready.status is ThesisStatus.INVESTABLE_NOW
