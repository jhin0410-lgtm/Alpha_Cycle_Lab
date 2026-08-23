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
    ConsensusGapObservation,
    DecisionExpectationGapSnapshot,
    DecisionViewSnapshot,
    persist_decision_expectation_gap,
    persist_decision_view,
)
from alpha_cycle.intelligence.forecast_ledger import ForecasterKind
from alpha_cycle.intelligence.payoff_surface import (
    PayoffScenario,
    PayoffSurfaceSnapshot,
    ScenarioLabel,
    persist_payoff_surface,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.research_run_ledger_v2_1 import ResearchRunKind
from alpha_cycle.intelligence.underwriter_v2_1 import (
    ForecastTournamentAssessment,
    UnderwritingLane,
    UnderwritingReadiness,
    UnderwritingReadinessSnapshot,
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
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


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


def _components(thesis: InvestmentThesisSnapshot, offset: int):
    security_id = thesis.security_id
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
        selection_rule_snapshot_id=C,
        security_id=security_id,
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecast_snapshot_id=D,
        selected_forecast_id=f"a-{security_id}",
        selected_forecaster_kind=ForecasterKind.MODEL,
        selected_model_family="fixture-model",
        selected_forecast_value=20_000_000.0 + offset,
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        tournament_forecast_snapshot_ids=(D, E),
        tournament_dependency_overlap=False,
        guardrail_evidence_id=GUARDRAIL,
    )
    gap = DecisionExpectationGapSnapshot(
        captured_at=NOW + timedelta(seconds=40 + offset),
        evaluation_date=EVAL,
        decision_view_snapshot_id=view.snapshot_id,
        expectation_state_snapshot_id=F,
        price_implied_requirement_snapshot_id=None,
        security_id=security_id,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        consensus_gaps=(
            ConsensusGapObservation(
                provider_id="provider-a",
                source_evidence_id=A,
                observed_at=NOW - timedelta(hours=1),
                decision_value=view.selected_forecast_value,
                consensus_value=18_000_000.0,
                unit=view.unit,
                absolute_gap=view.selected_forecast_value - 18_000_000.0,
                relative_gap=(view.selected_forecast_value - 18_000_000.0)
                / 18_000_000.0,
            ),
        ),
        price_implied_gaps=(),
        flags=("price_implied_comparison_not_supplied",),
        guardrail_evidence_id=GUARDRAIL,
    )
    tournament = ForecastTournamentAssessment(
        comparable=True,
        forecast_snapshot_ids=(D, E),
        forecast_ids=(f"a-{security_id}", f"b-{security_id}"),
        security_id=security_id,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        forecast_origin=view.forecast_origin,
        information_cutoff=view.information_cutoff,
        primary_error_metric="absolute_error",
        distinct_forecaster_count=2,
        dependency_cluster_count=2,
        blockers=(),
        flags=(),
    )
    underwriting = UnderwritingReadinessSnapshot(
        captured_at=NOW + timedelta(seconds=50 + offset),
        evaluation_date=EVAL,
        thesis_snapshot_id=thesis.snapshot_id,
        security_id=security_id,
        lane=UnderwritingLane.DEEP,
        readiness=UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
        guardrail_evidence_id=GUARDRAIL,
        context_snapshot_id=C,
        causal_graph_snapshot_id=None,
        forecast_tournament=tournament,
        expectation_state_snapshot_id=F,
        forward_valuation_snapshot_id=None,
        price_implied_requirement_snapshot_id=None,
        payoff_surface_snapshot_id=payoff.snapshot_id,
        epistemic_defense_snapshot_id=None,
        required_elements_satisfied=("payoff_surface",),
        required_elements_missing=(),
        blockers=(),
        flags=(),
    )
    return payoff, view, gap, underwriting


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
        payoff, view, gap, underwriting = _components(thesis, index)
        if mismatch_first_tournament and index == 0:
            underwriting = replace(
                underwriting,
                forecast_tournament=replace(
                    underwriting.forecast_tournament,
                    target_variable="revenue",
                ),
            )
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
