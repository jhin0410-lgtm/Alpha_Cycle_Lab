from __future__ import annotations

import json
from datetime import date, datetime
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
from alpha_cycle.intelligence.expectation_state import ExpectationKind, ExpectationMetric
from alpha_cycle.intelligence.forecast_ledger import (
    ForecastRegistrationMode,
    ForecastRegistrationSnapshot,
    ForecasterKind,
    OrdinalAssessment,
    PrimaryErrorMetric,
)
from alpha_cycle.intelligence.forward_valuation import ForwardValuationStatus
from alpha_cycle.intelligence.price_implied_requirement import PriceImpliedRequirementStatus
from alpha_cycle.intelligence.underwriter_v2_1 import (
    UnderwritingLane,
    UnderwritingReadiness,
    assess_forecast_tournament,
    build_underwriting_context,
    build_underwriting_readiness,
    persist_underwriting_context,
    persist_underwriting_readiness,
)

_KST = ZoneInfo("Asia/Seoul")
_GUARDRAILS = load_decision_system_v21_guardrails()
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64
_E = "e" * 64
_F = "f" * 64


def _uncertainty() -> ThesisUncertainty:
    dimension = UncertaintyDimension(
        UncertaintyLevel.MEDIUM,
        "Material uncertainty remains explicit for human review.",
    )
    return ThesisUncertainty(
        evidence=dimension,
        model=dimension,
        regime=dimension,
        expectation=dimension,
        catalyst=dimension,
        valuation=dimension,
    )


def _thesis() -> InvestmentThesisSnapshot:
    return InvestmentThesisSnapshot(
        thesis_id="000660-memory-underwriting",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=datetime(2026, 8, 22, 15, 0, tzinfo=_KST),
        security_id="000660",
        horizon_trading_days=120,
        variant_view="Forward net income can exceed the currently certified market bar.",
        why_now="Memory/HBM evidence changed ahead of the next earnings catalyst.",
        claims=(
            ThesisClaim(
                claim_id="memory-cycle",
                category="industry_cycle",
                statement="Memory pricing direction and mix are improving.",
                epistemic_status=EpistemicStatus.OBSERVED_FACT,
                direction=ClaimDirection.POSITIVE,
                evidence_refs=("evidence:memory-cycle",),
            ),
        ),
        catalysts=(
            CatalystClock(
                catalyst_id="next-quarter",
                statement="The next quarterly result tests earnings transmission.",
                evidence_refs=("evidence:filing-calendar",),
                earliest_date=date(2026, 10, 1),
                latest_date=date(2026, 11, 16),
            ),
        ),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=("Memory pricing reverses while supply expands.",),
        first_rejection_risk="The earnings inflection may already be priced.",
        portfolio_overlap=("memory-upcycle",),
        opportunity_set_refs=("opportunity-set:semiconductor-2026-08-22",),
        status=ThesisStatus.UNDERWRITING,
    )


def _forecast(
    forecast_id: str,
    *,
    model_family: str,
    cluster: str,
    origin_hour: int = 18,
    target_variable: str = "net_income",
) -> ForecastRegistrationSnapshot:
    return ForecastRegistrationSnapshot(
        forecast_id=forecast_id,
        registered_at=datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        ledger_recorded_at=datetime(2026, 8, 22, 17, 5, tzinfo=_KST),
        forecast_origin=datetime(2026, 8, 22, origin_hour, 0, tzinfo=_KST),
        information_cutoff=datetime(2026, 8, 22, 16, 0, tzinfo=_KST),
        security_id="000660",
        target_variable=target_variable,
        target_date=date(2026, 12, 31),
        horizon_label="FY2026",
        forecast_value=20_000_000.0,
        unit="KRW_million",
        range_lower=None,
        range_upper=None,
        direction=None,
        direction_reference_value=None,
        direction_flat_tolerance=0.0,
        confidence=OrdinalAssessment.MEDIUM,
        confidence_rationale="Prospective estimate with explicit model uncertainty.",
        forecaster_kind=ForecasterKind.MODEL,
        model_family=model_family,
        driver_refs=("driver:memory-cycle",),
        regime_tags=("memory-upcycle",),
        decision_relevance=OrdinalAssessment.HIGH,
        difficulty=OrdinalAssessment.HIGH,
        baseline_refs=(),
        dependency_cluster_id=cluster,
        source_evidence_ids=(_A,),
        registration_mode=ForecastRegistrationMode.NATIVE_PROSPECTIVE,
        primary_error_metric=PrimaryErrorMetric.ABSOLUTE_ERROR,
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
    )


def _context(thesis: InvestmentThesisSnapshot, *, transmission: bool = True):
    return build_underwriting_context(
        thesis,
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        transmission_evidence_refs=(_A,) if transmission else (),
        opportunity_set_comparison_refs=(_B,),
        portfolio_overlap_evidence_refs=(_C,),
    )


def _expectations():
    observation = SimpleNamespace(
        security_id="000660",
        expectation_kind=ExpectationKind.MARKET_CONSENSUS,
        market_consensus_certified=True,
        metric=ExpectationMetric.NET_INCOME,
        target_period_end=date(2026, 12, 31),
        unit="KRW_million",
    )
    return SimpleNamespace(
        evaluation_date=date(2026, 8, 22),
        captured_at=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
        observations=(observation,),
        snapshot_id=_D,
    )


def _forward_valuation(expectation_snapshot_id: str = _D):
    observation = SimpleNamespace(
        security_id="000660",
        status=ForwardValuationStatus.AVAILABLE,
    )
    return SimpleNamespace(
        evaluation_date=date(2026, 8, 22),
        captured_at=datetime(2026, 8, 22, 18, 5, tzinfo=_KST),
        expectation_state_snapshot_id=expectation_snapshot_id,
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
        observations=(observation,),
        snapshot_id=_E,
    )


def _price_implied():
    observation = SimpleNamespace(
        security_id="000660",
        status=PriceImpliedRequirementStatus.AVAILABLE,
    )
    return SimpleNamespace(
        evaluation_date=date(2026, 8, 22),
        captured_at=datetime(2026, 8, 22, 18, 6, tzinfo=_KST),
        security_id="000660",
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
        observations=(observation,),
        snapshot_id=_F,
    )


def _causal_graph():
    return SimpleNamespace(
        evaluation_date="2026-08-22",
        captured_at=datetime(2026, 8, 22, 18, 2, tzinfo=_KST),
        security_id="000660",
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
        snapshot_id="1" * 64,
    )


def _payoff(thesis: InvestmentThesisSnapshot):
    return SimpleNamespace(
        captured_at=datetime(2026, 8, 22, 18, 7, tzinfo=_KST),
        thesis_snapshot_id=thesis.snapshot_id,
        security_id=thesis.security_id,
        horizon_trading_days=thesis.horizon_trading_days,
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
        snapshot_id="2" * 64,
    )


def _epistemic(thesis: InvestmentThesisSnapshot, *, flagged: bool = False):
    return SimpleNamespace(
        captured_at=datetime(2026, 8, 22, 18, 8, tzinfo=_KST),
        thesis_snapshot_id=thesis.snapshot_id,
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
        snapshot_id="3" * 64,
        research_flags=("counter_evidence_material",) if flagged else (),
        high_materiality_counter_explanation_count=1 if flagged else 0,
        high_materiality_unresolved_contradiction_count=0,
        uncovered_high_materiality_blind_spot_count=0,
        blind_spot_promotion_candidate_count=0,
    )


def test_forecast_tournament_requires_true_comparability() -> None:
    first = _forecast("model-a", model_family="model-a", cluster="cluster-a")
    second = _forecast("model-b", model_family="model-b", cluster="cluster-b")
    assessment = assess_forecast_tournament(
        (first, second),
        thesis_security_id="000660",
        evaluation_date=date(2026, 8, 22),
    )
    assert assessment.comparable is True
    assert assessment.distinct_forecaster_count == 2
    assert assessment.blockers == ()

    mismatched = _forecast(
        "model-c",
        model_family="model-c",
        cluster="cluster-c",
        origin_hour=19,
    )
    rejected = assess_forecast_tournament(
        (first, mismatched),
        thesis_security_id="000660",
        evaluation_date=date(2026, 8, 22),
    )
    assert rejected.comparable is False
    assert "forecast_origin_mismatch" in rejected.blockers


def test_forecast_tournament_surfaces_dependency_overlap_without_false_independence() -> None:
    first = _forecast("model-a", model_family="model-a", cluster="shared")
    second = _forecast("model-b", model_family="model-b", cluster="shared")
    assessment = assess_forecast_tournament(
        (first, second),
        thesis_security_id="000660",
        evaluation_date=date(2026, 8, 22),
    )
    assert assessment.comparable is True
    assert "forecast_dependency_overlap" in assessment.flags


def test_fast_lane_can_use_minimal_transmission_evidence_without_full_graph() -> None:
    thesis = _thesis()
    result = build_underwriting_readiness(
        thesis,
        _context(thesis),
        lane=UnderwritingLane.FAST,
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        price_implied=_price_implied(),  # type: ignore[arg-type]
        epistemic_defense=_epistemic(thesis),  # type: ignore[arg-type]
    )
    assert result.readiness is UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW
    assert result.required_elements_missing == ()
    assert result.payload_without_id()["automatic_execution_enabled"] is False


def test_fast_lane_blocks_when_counter_thesis_and_transmission_are_missing() -> None:
    thesis = _thesis()
    result = build_underwriting_readiness(
        thesis,
        _context(thesis, transmission=False),
        lane=UnderwritingLane.FAST,
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        price_implied=_price_implied(),  # type: ignore[arg-type]
    )
    assert result.readiness is UnderwritingReadiness.FAST_LANE_BLOCKED
    assert "transmission" in result.required_elements_missing
    assert "counter_thesis" in result.required_elements_missing


def test_deep_lane_ready_binds_full_research_package_without_trade_decision() -> None:
    thesis = _thesis()
    first = _forecast("model-a", model_family="model-a", cluster="cluster-a")
    second = _forecast("model-b", model_family="model-b", cluster="cluster-b")
    result = build_underwriting_readiness(
        thesis,
        _context(thesis),
        lane=UnderwritingLane.DEEP,
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        forecasts=(first, second),
        causal_graph=_causal_graph(),  # type: ignore[arg-type]
        expectations=_expectations(),  # type: ignore[arg-type]
        forward_valuation=_forward_valuation(),  # type: ignore[arg-type]
        price_implied=_price_implied(),  # type: ignore[arg-type]
        payoff_surface=_payoff(thesis),  # type: ignore[arg-type]
        epistemic_defense=_epistemic(thesis),  # type: ignore[arg-type]
    )
    assert result.readiness is UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW
    assert result.required_elements_missing == ()
    payload = result.payload_without_id()
    assert payload["investability_decision_enabled"] is False
    assert payload["automatic_thesis_transition_enabled"] is False
    assert payload["target_price_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_deep_lane_requires_consensus_comparable_to_forecast_target() -> None:
    thesis = _thesis()
    first = _forecast("model-a", model_family="model-a", cluster="cluster-a")
    second = _forecast("model-b", model_family="model-b", cluster="cluster-b")
    expectations = _expectations()
    expectations.observations[0].metric = ExpectationMetric.REVENUE
    result = build_underwriting_readiness(
        thesis,
        _context(thesis),
        lane=UnderwritingLane.DEEP,
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        forecasts=(first, second),
        causal_graph=_causal_graph(),  # type: ignore[arg-type]
        expectations=expectations,  # type: ignore[arg-type]
        forward_valuation=_forward_valuation(),  # type: ignore[arg-type]
        price_implied=_price_implied(),  # type: ignore[arg-type]
        payoff_surface=_payoff(thesis),  # type: ignore[arg-type]
        epistemic_defense=_epistemic(thesis),  # type: ignore[arg-type]
    )
    assert result.readiness is UnderwritingReadiness.DEEP_LANE_BLOCKED
    assert "certified_expectation" in result.required_elements_missing


def test_deep_lane_preserves_epistemic_flags_instead_of_silently_approving() -> None:
    thesis = _thesis()
    first = _forecast("model-a", model_family="model-a", cluster="cluster-a")
    second = _forecast("model-b", model_family="model-b", cluster="cluster-b")
    result = build_underwriting_readiness(
        thesis,
        _context(thesis),
        lane=UnderwritingLane.DEEP,
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        forecasts=(first, second),
        causal_graph=_causal_graph(),  # type: ignore[arg-type]
        expectations=_expectations(),  # type: ignore[arg-type]
        forward_valuation=_forward_valuation(),  # type: ignore[arg-type]
        price_implied=_price_implied(),  # type: ignore[arg-type]
        payoff_surface=_payoff(thesis),  # type: ignore[arg-type]
        epistemic_defense=_epistemic(thesis, flagged=True),  # type: ignore[arg-type]
    )
    assert result.readiness is UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS
    assert "high_materiality_counter_explanation" in result.flags


def test_forward_valuation_must_bind_the_same_expectation_snapshot() -> None:
    thesis = _thesis()
    with pytest.raises(ValueError, match="different expectation state"):
        build_underwriting_readiness(
            thesis,
            _context(thesis),
            lane=UnderwritingLane.DEEP,
            captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
            evaluation_date=date(2026, 8, 22),
            expectations=_expectations(),  # type: ignore[arg-type]
            forward_valuation=_forward_valuation("9" * 64),  # type: ignore[arg-type]
        )


def test_persistence_keeps_context_and_readiness_content_addressed(tmp_path: Path) -> None:
    thesis = _thesis()
    context = _context(thesis)
    result = build_underwriting_readiness(
        thesis,
        context,
        lane=UnderwritingLane.FAST,
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        price_implied=_price_implied(),  # type: ignore[arg-type]
        epistemic_defense=_epistemic(thesis),  # type: ignore[arg-type]
    )
    context_pointer = persist_underwriting_context(context, output_root=tmp_path)
    result_pointer = persist_underwriting_readiness(result, output_root=tmp_path)
    assert context_pointer.parent.name == "underwriting_context"
    assert result_pointer.parent.name == "underwriting_readiness"
    pointer = json.loads(result_pointer.read_text(encoding="utf-8"))
    directory = Path(pointer["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == result.snapshot_id
    assert manifest["immutable"] is True
    assert manifest["investability_decision_enabled"] is False
    assert manifest["automatic_execution_enabled"] is False
