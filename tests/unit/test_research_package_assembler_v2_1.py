from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
from alpha_cycle.intelligence.decision_view_v2_1 import (
    DecisionViewSnapshot,
    build_decision_expectation_gap,
    build_decision_view_selection_rule,
    persist_decision_expectation_gap,
    persist_decision_view,
    persist_decision_view_selection_rule,
)
from alpha_cycle.intelligence.epistemic_defense import (
    EpistemicDefensePackageSnapshot,
    persist_epistemic_defense_package,
)
from alpha_cycle.intelligence.expectation_gap_contract import ExpectationSemantics
from alpha_cycle.intelligence.expectation_state import (
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
    persist_expectation_state,
)
from alpha_cycle.intelligence.forecast_ledger import (
    ForecasterKind,
    ForecastRegistrationMode,
    ForecastRegistrationSnapshot,
    OrdinalAssessment,
    PrimaryErrorMetric,
    persist_forecast_registration,
)
from alpha_cycle.intelligence.forward_valuation import (
    ForwardValuationMetric,
    ForwardValuationObservation,
    ForwardValuationStateSnapshot,
    ForwardValuationStatus,
    persist_forward_valuation_state,
)
from alpha_cycle.intelligence.payoff_surface import (
    PayoffScenario,
    PayoffSurfaceSnapshot,
    ScenarioLabel,
    persist_payoff_surface,
)
from alpha_cycle.intelligence.price_implied_requirement import (
    PriceImpliedRequirementObservation,
    PriceImpliedRequirementSnapshot,
    PriceImpliedRequirementStatus,
    ReferenceFrameKind,
    persist_price_implied_requirement,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.research_run_ledger_v2_1 import ResearchRunKind
from alpha_cycle.intelligence.semiconductor_causal_graph import (
    CausalEdge,
    CausalEdgeDirection,
    CausalNode,
    CausalNodeType,
    CriticalStateVariable,
    TransmissionLag,
    build_semiconductor_causal_graph,
    persist_semiconductor_causal_graph,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    UnderwritingLane,
    build_underwriting_context,
    build_underwriting_readiness,
    persist_underwriting_context,
    persist_underwriting_readiness,
)
from alpha_cycle.investment_thesis_repository_v2_1 import persist_investment_thesis
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_package_assembler_v2_1 import assemble_and_run_research_package
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request
from alpha_cycle.research_request_preflight_v2_1 import preflight_pending_request_theses

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
EVAL = date(2026, 8, 23)
TARGET = date(2026, 12, 31)
ACTIVE_GUARDRAILS = load_decision_system_v21_guardrails()
GUARDRAIL = ACTIVE_GUARDRAILS.evidence_id
A = "a" * 64
B = "b" * 64
C = "c" * 64


def _uncertainty() -> ThesisUncertainty:
    item = UncertaintyDimension(
        level=UncertaintyLevel.MEDIUM,
        rationale="Package-assembler regression fixture.",
    )
    return ThesisUncertainty(
        evidence=item,
        model=item,
        regime=item,
        expectation=item,
        catalyst=item,
        valuation=item,
    )


def _thesis(security_id: str) -> InvestmentThesisSnapshot:
    return InvestmentThesisSnapshot(
        thesis_id=f"assembler-{security_id}",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=NOW + timedelta(seconds=10),
        security_id=security_id,
        horizon_trading_days=120,
        variant_view="Persisted evidence is assembled without an investment conclusion.",
        why_now="Exercise the typed research-package trust boundary.",
        claims=(
            ThesisClaim(
                claim_id="cycle",
                category="industry_cycle",
                statement="Cycle transmission remains a testable hypothesis.",
                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
                direction=ClaimDirection.MIXED,
            ),
        ),
        catalysts=(
            CatalystClock(
                catalyst_id="earnings",
                statement="Future earnings release tests the thesis.",
                evidence_refs=("evidence:calendar",),
                earliest_date=date(2026, 10, 1),
                latest_date=date(2026, 11, 15),
            ),
        ),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=("The proposed transmission fails.",),
        first_rejection_risk="The market may already reflect the hypothesis.",
        portfolio_overlap=("memory-cycle",),
        opportunity_set_refs=("opportunity-set:fixture",),
        status=ThesisStatus.UNDERWRITING,
    )


def _scenario(label: ScenarioLabel, lower: float, upper: float) -> PayoffScenario:
    return PayoffScenario(
        scenario_id=f"{label.value}-case",
        label=label,
        horizon_trading_days=120,
        trigger_conditions=(f"{label.value} trigger",),
        fundamental_assumptions=(f"{label.value} assumptions",),
        catalyst_refs=("catalyst:earnings",),
        source_evidence_ids=(A,),
        return_lower=lower,
        return_upper=upper,
        thesis_break_conditions=("assumptions fail",),
    )


def _registration(
    thesis: InvestmentThesisSnapshot,
    *,
    forecast_id: str,
    model_family: str,
    forecaster_kind: ForecasterKind,
    dependency_cluster_id: str,
    forecast_value: float,
) -> ForecastRegistrationSnapshot:
    return ForecastRegistrationSnapshot(
        forecast_id=forecast_id,
        registered_at=NOW - timedelta(hours=2, minutes=30),
        ledger_recorded_at=NOW - timedelta(hours=2, minutes=20),
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        security_id=thesis.security_id,
        target_variable="net_income",
        target_date=TARGET,
        horizon_label="fixture-forward-target",
        forecast_value=forecast_value,
        unit="KRW_million",
        range_lower=None,
        range_upper=None,
        direction=None,
        direction_reference_value=None,
        direction_flat_tolerance=0.0,
        confidence=OrdinalAssessment.MEDIUM,
        confidence_rationale="Persisted package fixture forecast.",
        forecaster_kind=forecaster_kind,
        model_family=model_family,
        driver_refs=("driver:fixture",),
        regime_tags=("fixture-regime",),
        decision_relevance=OrdinalAssessment.HIGH,
        difficulty=OrdinalAssessment.MEDIUM,
        baseline_refs=(),
        dependency_cluster_id=dependency_cluster_id,
        source_evidence_ids=(A,),
        registration_mode=ForecastRegistrationMode.NATIVE_PROSPECTIVE,
        primary_error_metric=PrimaryErrorMetric.ABSOLUTE_ERROR,
        guardrail_evidence_id=GUARDRAIL,
    )


def _causal_graph(thesis: InvestmentThesisSnapshot, offset: int):
    states = tuple(CriticalStateVariable)
    nodes = tuple(
        CausalNode(
            node_id=f"state-{state.value}",
            label=state.value,
            node_type=CausalNodeType.CRITICAL_STATE,
            description=f"Fixture critical state {state.value}.",
            critical_state_variable=state,
        )
        for state in states
    )
    edge = CausalEdge(
        edge_id="fixture-transmission",
        source_node_id=nodes[0].node_id,
        target_node_id=nodes[1].node_id,
        mechanism="Fixture transmission remains falsifiable.",
        epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
        direction=CausalEdgeDirection.POSITIVE,
        lag=TransmissionLag(minimum_days=1),
        regime_applicability=("fixture-regime",),
        evidence_refs=(),
        opposing_evidence_refs=(),
        falsifier="Observed transmission does not occur.",
    )
    return build_semiconductor_causal_graph(
        graph_id=f"fixture-{thesis.security_id}",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=NOW + timedelta(seconds=21 + offset),
        evaluation_date=EVAL.isoformat(),
        security_id=thesis.security_id,
        nodes=nodes,
        edges=(edge,),
        source_snapshot_ids=(A,),
    )


def _expectations(thesis: InvestmentThesisSnapshot, offset: int) -> ExpectationStateSnapshot:
    semantics = ExpectationSemantics(
        provider_id="provider-a",
        provider_semantics_certified=True,
        target_period_semantics_certified=True,
        metric_semantics_certified=True,
        aggregation_semantics_certified=True,
        observation_timestamp_certified=True,
        provider_vintage_certified=False,
        comparable_prior_snapshot_available=False,
        comparable_snapshot_scope_certified=False,
        revision_calculation_certified=False,
        numeric_evidence_available=True,
        source_scope="fixture-consensus",
    )
    observation = CertifiedExpectationObservation(
        security_id=thesis.security_id,
        metric=ExpectationMetric.NET_INCOME,
        target_period="2026",
        target_period_end=TARGET,
        expectation_kind=ExpectationKind.MARKET_CONSENSUS,
        value=18_000_000.0 + offset,
        unit="KRW_million",
        observed_at=NOW - timedelta(hours=1),
        source_evidence_id=A,
        semantics=semantics,
        market_consensus_certified=True,
        aggregation_method="fixture-median",
        sample_count=3,
    )
    return ExpectationStateSnapshot(
        captured_at=NOW + timedelta(seconds=22 + offset),
        evaluation_date=EVAL,
        observations=(observation,),
        source_snapshot_ids=(A,),
    )


def _forward_valuation(
    thesis: InvestmentThesisSnapshot,
    expectations: ExpectationStateSnapshot,
    offset: int,
) -> ForwardValuationStateSnapshot:
    expectation = expectations.observations[0]
    expectation_krw = float(expectation.value) * 1_000_000.0
    market_cap = expectation_krw * 10.0
    observation = ForwardValuationObservation(
        security_id=thesis.security_id,
        expectation_provider_id=expectation.provider_id,
        expectation_kind=expectation.expectation_kind,
        expectation_metric=expectation.metric,
        target_period=expectation.target_period,
        target_period_end=expectation.target_period_end,
        expectation_observed_at=expectation.observed_at,
        expectation_source_evidence_id=expectation.source_evidence_id,
        expectation_value=float(expectation.value),
        expectation_unit=expectation.unit,
        expectation_value_krw=expectation_krw,
        market_cap_krw=market_cap,
        valuation_metric=ForwardValuationMetric.FORWARD_PE,
        multiple=10.0,
        status=ForwardValuationStatus.AVAILABLE,
    )
    return ForwardValuationStateSnapshot(
        captured_at=NOW + timedelta(seconds=23 + offset),
        evaluation_date=EVAL,
        valuation_evidence_snapshot_id=B,
        expectation_state_snapshot_id=expectations.snapshot_id,
        guardrail_evidence_id=GUARDRAIL,
        observations=(observation,),
    )


def _price_implied(
    thesis: InvestmentThesisSnapshot,
    expectations: ExpectationStateSnapshot,
    offset: int,
) -> PriceImpliedRequirementSnapshot:
    expectation = expectations.observations[0]
    implied_value = float(expectation.value) * 1_000_000.0
    observation = PriceImpliedRequirementObservation(
        security_id=thesis.security_id,
        reference_id="fixture-price-reference",
        reference_kind=ReferenceFrameKind.EXPLICIT_SCENARIO_ASSUMPTION,
        valuation_metric=ForwardValuationMetric.FORWARD_PE,
        implied_metric=ExpectationMetric.NET_INCOME,
        target_period=expectation.target_period,
        target_period_end=expectation.target_period_end,
        reference_multiple=10.0,
        market_cap_krw=implied_value * 10.0,
        implied_value_krw=implied_value,
        status=PriceImpliedRequirementStatus.AVAILABLE,
    )
    return PriceImpliedRequirementSnapshot(
        captured_at=NOW + timedelta(seconds=24 + offset),
        evaluation_date=EVAL,
        security_id=thesis.security_id,
        valuation_evidence_snapshot_id=B,
        reference_frame_snapshot_id=C,
        guardrail_evidence_id=GUARDRAIL,
        observations=(observation,),
    )


def _components(thesis: InvestmentThesisSnapshot, offset: int):
    security_id = thesis.security_id
    selected_registration = _registration(
        thesis,
        forecast_id=f"a-{security_id}",
        model_family="fixture-model",
        forecaster_kind=ForecasterKind.MODEL,
        dependency_cluster_id=f"model-{security_id}",
        forecast_value=20_000_000.0 + offset,
    )
    benchmark_registration = _registration(
        thesis,
        forecast_id=f"b-{security_id}",
        model_family="fixture-benchmark",
        forecaster_kind=ForecasterKind.BENCHMARK,
        dependency_cluster_id=f"benchmark-{security_id}",
        forecast_value=18_000_000.0 + offset,
    )
    registrations = (selected_registration, benchmark_registration)
    selection_rule = build_decision_view_selection_rule(
        rule_id=f"fixture-selection-{security_id}",
        registered_at=NOW - timedelta(hours=4),
        security_id=security_id,
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecaster_kind=selected_registration.forecaster_kind,
        selected_model_family=selected_registration.model_family,
        rationale="Freeze forecaster identity before forecast registration.",
        source_evidence_ids=(A,),
    )
    payoff = PayoffSurfaceSnapshot(
        captured_at=NOW + timedelta(seconds=20 + offset),
        thesis_snapshot_id=thesis.snapshot_id,
        security_id=security_id,
        horizon_trading_days=120,
        scenarios=(
            _scenario(ScenarioLabel.BEAR, -0.30, -0.10),
            _scenario(ScenarioLabel.BASE, 0.10, 0.30),
            _scenario(ScenarioLabel.BULL, 0.35, 0.60),
        ),
        source_snapshot_ids=(B,),
        guardrail_evidence_id=GUARDRAIL,
    )
    view = DecisionViewSnapshot(
        captured_at=NOW + timedelta(seconds=30 + offset),
        evaluation_date=EVAL,
        selection_rule_snapshot_id=selection_rule.snapshot_id,
        security_id=security_id,
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecast_snapshot_id=selected_registration.snapshot_id,
        selected_forecast_id=selected_registration.forecast_id,
        selected_forecaster_kind=selected_registration.forecaster_kind,
        selected_model_family=selected_registration.model_family,
        selected_forecast_value=selected_registration.forecast_value,
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        tournament_forecast_snapshot_ids=tuple(
            sorted(item.snapshot_id for item in registrations)
        ),
        tournament_dependency_overlap=False,
        guardrail_evidence_id=GUARDRAIL,
    )
    context = build_underwriting_context(
        thesis,
        captured_at=NOW + timedelta(seconds=18 + offset),
        evaluation_date=EVAL,
        transmission_evidence_refs=(A,),
        opportunity_set_comparison_refs=(B,),
        portfolio_overlap_evidence_refs=(C,),
    )
    causal_graph = _causal_graph(thesis, offset)
    expectations = _expectations(thesis, offset)
    forward_valuation = _forward_valuation(thesis, expectations, offset)
    price_implied = _price_implied(thesis, expectations, offset)
    epistemic = EpistemicDefensePackageSnapshot(
        captured_at=NOW + timedelta(seconds=25 + offset),
        thesis_snapshot_id=thesis.snapshot_id,
        counter_thesis_snapshot_id=A,
        blind_spot_snapshot_id=B,
        guardrail_evidence_id=GUARDRAIL,
        required_contracts_present=True,
        high_materiality_counter_explanation_count=0,
        high_materiality_unresolved_contradiction_count=0,
        uncovered_high_materiality_blind_spot_count=0,
        blind_spot_promotion_candidate_count=0,
        research_flags=(),
    )
    gap = build_decision_expectation_gap(
        view,
        expectations,
        captured_at=NOW + timedelta(seconds=40 + offset),
        evaluation_date=EVAL,
        price_implied=price_implied,
    )
    underwriting = build_underwriting_readiness(
        thesis,
        context,
        lane=UnderwritingLane.DEEP,
        captured_at=NOW + timedelta(seconds=50 + offset),
        evaluation_date=EVAL,
        forecasts=registrations,
        causal_graph=causal_graph,
        expectations=expectations,
        forward_valuation=forward_valuation,
        price_implied=price_implied,
        payoff_surface=payoff,
        epistemic_defense=epistemic,
    )
    return (
        payoff,
        view,
        gap,
        underwriting,
        registrations,
        selection_rule,
        context,
        causal_graph,
        expectations,
        forward_valuation,
        price_implied,
        epistemic,
    )


def _prepare_ready_request(tmp_path: Path):
    record_analysis_request(
        request_id="typed-package-round",
        requested_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        evaluation_date=EVAL,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Assemble a two-security persisted research package.",
        artifact_root=tmp_path,
    )
    theses = (_thesis("000660"), _thesis("005930"))
    for thesis in theses:
        persist_investment_thesis(thesis, artifact_root=tmp_path)
    preflight = preflight_pending_request_theses(
        request_id="typed-package-round",
        run_id="thesis-ready",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    assert preflight.ready_for_package_assembly is True
    return theses


def _persist_components(
    tmp_path: Path,
    theses: tuple[InvestmentThesisSnapshot, ...],
    *,
    mismatch_first_tournament: bool = False,
) -> None:
    for index, thesis in enumerate(theses):
        (
            payoff,
            view,
            gap,
            underwriting,
            registrations,
            selection_rule,
            context,
            causal_graph,
            expectations,
            forward_valuation,
            price_implied,
            epistemic,
        ) = _components(thesis, index)
        if mismatch_first_tournament and index == 0:
            underwriting = replace(
                underwriting,
                forecast_tournament=replace(
                    underwriting.forecast_tournament,
                    target_variable="revenue",
                ),
            )
        persist_decision_view_selection_rule(selection_rule, output_root=tmp_path)
        for registration in registrations:
            persist_forecast_registration(registration, output_root=tmp_path)
        persist_underwriting_context(context, output_root=tmp_path)
        persist_semiconductor_causal_graph(
            causal_graph,
            output_root=tmp_path / "semiconductor_causal_graph",
        )
        persist_expectation_state(
            expectations,
            output_root=tmp_path / "expectation_state",
        )
        persist_forward_valuation_state(
            forward_valuation,
            output_root=tmp_path / "forward_valuation",
        )
        persist_price_implied_requirement(price_implied, output_root=tmp_path)
        persist_epistemic_defense_package(epistemic, output_root=tmp_path)
        persist_payoff_surface(payoff, output_root=tmp_path / "payoff_surface")
        persist_decision_view(view, output_root=tmp_path)
        persist_decision_expectation_gap(gap, output_root=tmp_path)
        persist_underwriting_readiness(underwriting, output_root=tmp_path)


def test_missing_components_block_without_running_orchestrator(tmp_path: Path) -> None:
    _prepare_ready_request(tmp_path)
    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-missing-components",
        run_id="package-blocked",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.orchestrated is None
    assert receipt.full_package_ready is False
    assert receipt.changed_history is True
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    assert {item.component for item in receipt.blockers} == {
        "underwriter",
        "payoff_surface",
        "decision_view",
        "expectation_gap",
    }
    payload = receipt.payload()
    assert payload["orchestrator_executed"] is False
    assert payload["investment_conclusion_created"] is False
    assert payload["automatic_execution_enabled"] is False


def test_full_persisted_package_delegates_to_existing_orchestrator(tmp_path: Path) -> None:
    theses = _prepare_ready_request(tmp_path)
    _persist_components(tmp_path, theses)

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-full-package",
        run_id="package-orchestrated",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.full_package_ready is True
    assert receipt.orchestrated is not None
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.ORCHESTRATED
    assert len(receipt.packages) == 2
    assert receipt.research_round_path is not None
    assert receipt.research_round_path.exists()
    assert receipt.payload()["automatic_execution_enabled"] is False

    candidate_root = tmp_path / "opportunity_candidate"
    assert (candidate_root / "latest_opportunity_candidate.json").exists()
    for candidate in receipt.orchestrated.opportunity_candidates:
        assert any(
            path.is_dir() and path.name.endswith(candidate.snapshot_id[:12])
            for path in candidate_root.iterdir()
        )
    if receipt.orchestrated.opportunity_set is not None:
        opportunity_set = receipt.orchestrated.opportunity_set
        set_root = tmp_path / "opportunity_set"
        assert (set_root / "latest_opportunity_set.json").exists()
        assert any(
            path.is_dir() and path.name.endswith(opportunity_set.snapshot_id[:12])
            for path in set_root.iterdir()
        )

    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert state.ledger.summary.orchestrated_run_count == 1
    assert {row.state for row in state.inbox} == {receipt.run.round_status.value}


def test_tournament_binding_mismatch_blocks_before_orchestrator(tmp_path: Path) -> None:
    theses = _prepare_ready_request(tmp_path)
    _persist_components(tmp_path, theses, mismatch_first_tournament=True)

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-wrong-tournament",
        run_id="package-wrong-tournament",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.orchestrated is None
    assert receipt.full_package_ready is False
    assert any(
        blocker.code == "underwriting_decision_view_tournament_binding_mismatch"
        and blocker.security_id == "000660"
        for blocker in receipt.blockers
    )
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_invalid_run_id_leaves_no_round_or_opportunity_artifacts(tmp_path: Path) -> None:
    theses = _prepare_ready_request(tmp_path)
    _persist_components(tmp_path, theses)

    with pytest.raises(ValueError, match="run_id"):
        assemble_and_run_research_package(
            request_id="typed-package-round",
            round_id="round-invalid-run-id",
            run_id="",
            processed_at=NOW + timedelta(minutes=2),
            artifact_root=tmp_path,
        )

    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_missing_preflight_selected_thesis_persists_current_package_blocker(
    tmp_path: Path,
) -> None:
    theses = _prepare_ready_request(tmp_path)
    missing = theses[0]
    (tmp_path / "investment_thesis_v2_1" / f"{missing.snapshot_id}.json").unlink()

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-stale-preflight-thesis",
        run_id="package-stale-preflight-thesis",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.orchestrated is None
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    codes = {item.code for item in receipt.blockers}
    assert "investment_thesis_snapshot_missing" in codes
    assert "preflight_thesis_identity_mismatch" in codes
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}
