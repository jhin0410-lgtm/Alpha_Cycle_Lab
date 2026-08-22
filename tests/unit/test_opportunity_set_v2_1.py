from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
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
)
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OpportunityResearchClass,
    build_opportunity_candidate,
    build_opportunity_set,
    persist_opportunity_candidate,
    persist_opportunity_set,
)
from alpha_cycle.intelligence.payoff_surface import (
    PayoffScenario,
    ScenarioLabel,
    build_payoff_surface,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingReadiness

_KST = ZoneInfo("Asia/Seoul")
_EVALUATION_DATE = date(2026, 8, 22)
_GUARDRAILS = load_decision_system_v21_guardrails()
_EVIDENCE = "a" * 64


def _uncertainty() -> ThesisUncertainty:
    dimension = UncertaintyDimension(
        UncertaintyLevel.MEDIUM,
        "Uncertainty remains explicit in the cross-sectional comparison.",
    )
    return ThesisUncertainty(
        evidence=dimension,
        model=dimension,
        regime=dimension,
        expectation=dimension,
        catalyst=dimension,
        valuation=dimension,
    )


def _thesis(
    security_id: str,
    *,
    catalyst_days: int | None = 20,
    horizon: int = 120,
) -> InvestmentThesisSnapshot:
    if catalyst_days is None:
        catalysts = (
            CatalystClock(
                catalyst_id=f"{security_id}-conditional",
                statement="Catalyst exists but its earliest date is not yet certified.",
                evidence_refs=("evidence:conditional-catalyst",),
                condition="Specific operating milestone becomes observable.",
            ),
        )
    else:
        catalysts = (
            CatalystClock(
                catalyst_id=f"{security_id}-dated",
                statement="A dated catalyst tests the investment transmission path.",
                evidence_refs=(f"evidence:{security_id}:catalyst",),
                earliest_date=_EVALUATION_DATE + timedelta(days=catalyst_days),
                latest_date=_EVALUATION_DATE + timedelta(days=catalyst_days + 10),
            ),
        )
    return InvestmentThesisSnapshot(
        thesis_id=f"{security_id}-opportunity-thesis",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=datetime(2026, 8, 22, 15, 0, tzinfo=_KST),
        security_id=security_id,
        horizon_trading_days=horizon,
        variant_view="The candidate may offer a better payoff/timing trade-off than peers.",
        why_now="A decision-relevant state changed before a dated catalyst.",
        claims=(
            ThesisClaim(
                claim_id=f"{security_id}-claim",
                category="cross_sectional_opportunity",
                statement="The thesis has explicit evidence and a falsifiable transmission path.",
                epistemic_status=EpistemicStatus.OBSERVED_FACT,
                direction=ClaimDirection.POSITIVE,
                evidence_refs=(f"evidence:{security_id}:claim",),
            ),
        ),
        catalysts=catalysts,
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=("The causal transmission fails before the catalyst window.",),
        first_rejection_risk="The payoff may already be priced into the security.",
        portfolio_overlap=(f"risk-driver:{security_id}",),
        opportunity_set_refs=("opportunity-set:2026-08-22",),
        status=ThesisStatus.UNDERWRITING,
    )


def _payoff(
    thesis: InvestmentThesisSnapshot,
    *,
    bear: float,
    base_lower: float,
    base_upper: float,
    bull: float,
):
    def scenario(
        label: ScenarioLabel,
        lower: float,
        upper: float,
    ) -> PayoffScenario:
        return PayoffScenario(
            scenario_id=f"{thesis.security_id}-{label.value}",
            label=label,
            horizon_trading_days=thesis.horizon_trading_days,
            trigger_conditions=(f"{label.value} trigger becomes observable.",),
            fundamental_assumptions=(f"{label.value} fundamentals remain internally consistent.",),
            catalyst_refs=(thesis.catalysts[0].catalyst_id,),
            source_evidence_ids=(_EVIDENCE,),
            return_lower=lower,
            return_upper=upper,
            thesis_break_conditions=("Observed evidence invalidates this scenario.",),
        )

    return build_payoff_surface(
        thesis,
        captured_at=datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        scenarios=(
            scenario(ScenarioLabel.BEAR, bear, max(bear, bear + 0.05)),
            scenario(ScenarioLabel.BASE, base_lower, base_upper),
            scenario(ScenarioLabel.BULL, min(bull - 0.05, bull), bull),
        ),
        source_snapshot_ids=(_EVIDENCE,),
    )


def _underwriting(
    thesis: InvestmentThesisSnapshot,
    payoff_snapshot_id: str,
    *,
    readiness: UnderwritingReadiness = (
        UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW
    ),
    flags: tuple[str, ...] = (),
):
    return SimpleNamespace(
        captured_at=datetime(2026, 8, 22, 17, 30, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
        thesis_snapshot_id=thesis.snapshot_id,
        security_id=thesis.security_id,
        readiness=readiness,
        flags=flags,
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
        payoff_surface_snapshot_id=payoff_snapshot_id,
        snapshot_id=(thesis.security_id[-1] if thesis.security_id[-1].isalnum() else "b")
        * 64,
    )


def _candidate(
    security_id: str,
    *,
    bear: float,
    base_lower: float,
    base_upper: float,
    bull: float,
    catalyst_days: int | None,
    readiness: UnderwritingReadiness = (
        UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW
    ),
    flags: tuple[str, ...] = (),
):
    thesis = _thesis(security_id, catalyst_days=catalyst_days)
    payoff = _payoff(
        thesis,
        bear=bear,
        base_lower=base_lower,
        base_upper=base_upper,
        bull=bull,
    )
    underwriting = _underwriting(
        thesis,
        payoff.snapshot_id,
        readiness=readiness,
        flags=flags,
    )
    return build_opportunity_candidate(
        thesis,
        underwriting,  # type: ignore[arg-type]
        payoff,
        captured_at=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
    )


def test_candidate_excludes_cost_basis_and_uses_dated_catalyst() -> None:
    candidate = _candidate(
        "000660",
        bear=-0.10,
        base_lower=0.10,
        base_upper=0.20,
        bull=0.40,
        catalyst_days=15,
    )
    assert candidate.research_class is OpportunityResearchClass.DEEP_READY
    assert candidate.capital_allocation_comparable is True
    assert candidate.nearest_catalyst_days == 15
    payload = candidate.payload_without_id()
    assert payload["current_cost_basis_considered"] is False
    assert payload["unrealized_pnl_considered"] is False
    assert payload["composite_score_enabled"] is False
    assert payload["probability_weighted_expected_return_enabled"] is False


def test_strict_pareto_dominance_can_identify_unique_leader() -> None:
    stronger = _candidate(
        "000660",
        bear=-0.10,
        base_lower=0.10,
        base_upper=0.20,
        bull=0.40,
        catalyst_days=10,
    )
    weaker = _candidate(
        "005930",
        bear=-0.20,
        base_lower=0.05,
        base_upper=0.15,
        bull=0.30,
        catalyst_days=20,
    )
    opportunity_set = build_opportunity_set(
        (stronger, weaker),
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
        horizon_trading_days=120,
    )
    assert opportunity_set.pareto_frontier_security_ids == ("000660",)
    assert opportunity_set.unique_pareto_leader_security_id == "000660"
    assert len(opportunity_set.dominance_relations) == 1
    relation = opportunity_set.dominance_relations[0]
    assert relation.dominator_security_id == "000660"
    assert "nearest_catalyst_days" in relation.strictly_better_dimensions


def test_tradeoff_keeps_multiple_non_dominated_candidates() -> None:
    downside_quality = _candidate(
        "000660",
        bear=-0.08,
        base_lower=0.08,
        base_upper=0.18,
        bull=0.32,
        catalyst_days=20,
    )
    upside_speed = _candidate(
        "005930",
        bear=-0.20,
        base_lower=0.05,
        base_upper=0.25,
        bull=0.50,
        catalyst_days=8,
    )
    opportunity_set = build_opportunity_set(
        (downside_quality, upside_speed),
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
        horizon_trading_days=120,
    )
    assert set(opportunity_set.pareto_frontier_security_ids) == {"000660", "005930"}
    assert opportunity_set.unique_pareto_leader_security_id is None
    assert "multiple_non_dominated_opportunities" in opportunity_set.flags


def test_fast_lane_candidate_is_not_promoted_into_capital_allocation_frontier() -> None:
    deep = _candidate(
        "000660",
        bear=-0.15,
        base_lower=0.05,
        base_upper=0.15,
        bull=0.30,
        catalyst_days=20,
    )
    fast = _candidate(
        "005930",
        bear=-0.01,
        base_lower=0.30,
        base_upper=0.50,
        bull=0.80,
        catalyst_days=5,
        readiness=UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW,
    )
    opportunity_set = build_opportunity_set(
        (deep, fast),
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
        horizon_trading_days=120,
    )
    assert opportunity_set.comparable_security_ids == ("000660",)
    assert opportunity_set.fast_lane_research_security_ids == ("005930",)
    assert opportunity_set.pareto_frontier_security_ids == ("000660",)
    assert opportunity_set.unique_pareto_leader_security_id is None
    assert "insufficient_fully_comparable_deep_candidates" in opportunity_set.flags


def test_missing_dated_catalyst_blocks_cross_sectional_comparability() -> None:
    timed = _candidate(
        "000660",
        bear=-0.10,
        base_lower=0.10,
        base_upper=0.20,
        bull=0.40,
        catalyst_days=10,
    )
    conditional = _candidate(
        "005930",
        bear=-0.05,
        base_lower=0.15,
        base_upper=0.30,
        bull=0.50,
        catalyst_days=None,
    )
    assert conditional.capital_allocation_comparable is False
    assert "dated_catalyst_timing_unavailable" in conditional.comparison_blockers
    opportunity_set = build_opportunity_set(
        (timed, conditional),
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
        horizon_trading_days=120,
    )
    assert "partial_cross_sectional_comparability" in opportunity_set.flags
    assert opportunity_set.unique_pareto_leader_security_id is None


def test_deep_epistemic_flags_remain_visible_on_frontier() -> None:
    flagged = _candidate(
        "000660",
        bear=-0.10,
        base_lower=0.10,
        base_upper=0.20,
        bull=0.40,
        catalyst_days=10,
        readiness=UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS,
        flags=("high_materiality_counter_explanation",),
    )
    other = _candidate(
        "005930",
        bear=-0.20,
        base_lower=0.05,
        base_upper=0.15,
        bull=0.30,
        catalyst_days=20,
    )
    opportunity_set = build_opportunity_set(
        (flagged, other),
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
        horizon_trading_days=120,
    )
    assert opportunity_set.pareto_frontier_security_ids == ("000660",)
    assert opportunity_set.epistemically_flagged_security_ids == ("000660",)
    assert "pareto_set_contains_epistemically_flagged_research" in opportunity_set.flags


def test_underwriter_payoff_binding_mismatch_fails_closed() -> None:
    thesis = _thesis("000660", catalyst_days=10)
    payoff = _payoff(
        thesis,
        bear=-0.10,
        base_lower=0.10,
        base_upper=0.20,
        bull=0.40,
    )
    underwriting = _underwriting(thesis, "9" * 64)
    with pytest.raises(ValueError, match="different payoff surface"):
        build_opportunity_candidate(
            thesis,
            underwriting,  # type: ignore[arg-type]
            payoff,
            captured_at=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
            evaluation_date=_EVALUATION_DATE,
        )


def test_opportunity_set_rejects_mixed_horizons() -> None:
    first = _candidate(
        "000660",
        bear=-0.10,
        base_lower=0.10,
        base_upper=0.20,
        bull=0.40,
        catalyst_days=10,
    )
    thesis = _thesis("005930", catalyst_days=20, horizon=250)
    payoff = _payoff(
        thesis,
        bear=-0.20,
        base_lower=0.05,
        base_upper=0.15,
        bull=0.30,
    )
    second = build_opportunity_candidate(
        thesis,
        _underwriting(thesis, payoff.snapshot_id),  # type: ignore[arg-type]
        payoff,
        captured_at=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
    )
    with pytest.raises(ValueError, match="horizon differs"):
        build_opportunity_set(
            (first, second),
            captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
            evaluation_date=_EVALUATION_DATE,
            horizon_trading_days=120,
        )


def test_persistence_is_content_addressed_and_keeps_allocation_disabled(
    tmp_path: Path,
) -> None:
    first = _candidate(
        "000660",
        bear=-0.10,
        base_lower=0.10,
        base_upper=0.20,
        bull=0.40,
        catalyst_days=10,
    )
    second = _candidate(
        "005930",
        bear=-0.20,
        base_lower=0.05,
        base_upper=0.15,
        bull=0.30,
        catalyst_days=20,
    )
    opportunity_set = build_opportunity_set(
        (first, second),
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=_EVALUATION_DATE,
        horizon_trading_days=120,
    )
    candidate_pointer = persist_opportunity_candidate(first, output_root=tmp_path)
    set_pointer = persist_opportunity_set(opportunity_set, output_root=tmp_path)
    assert candidate_pointer.parent.name == "opportunity_candidate"
    assert set_pointer.parent.name == "opportunity_set"
    pointer = json.loads(set_pointer.read_text(encoding="utf-8"))
    directory = Path(pointer["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((directory / "opportunity_set.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == opportunity_set.snapshot_id
    assert manifest["immutable"] is True
    assert manifest["capital_allocation_recommendation_enabled"] is False
    assert manifest["automatic_execution_enabled"] is False
    assert payload["weighted_composite_score_enabled"] is False
    assert payload["optimal_portfolio_weights_enabled"] is False
