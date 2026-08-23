from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
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
from alpha_cycle.intelligence.underwriter_v2_1 import (
    ForecastTournamentAssessment,
    UnderwritingLane,
    UnderwritingReadiness,
    UnderwritingReadinessSnapshot,
    persist_underwriting_readiness,
)
from alpha_cycle.research_component_repository_v2_1 import (
    ResearchComponentRepositoryError,
    build_research_component_repository_index,
)

NOW = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)
EVAL = date(2026, 8, 23)
TARGET = date(2026, 12, 31)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


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


def _payoff(security_id: str, thesis_id: str, captured_at: datetime) -> PayoffSurfaceSnapshot:
    return PayoffSurfaceSnapshot(
        captured_at=captured_at,
        thesis_snapshot_id=thesis_id,
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


def _view(security_id: str, captured_at: datetime) -> DecisionViewSnapshot:
    return DecisionViewSnapshot(
        captured_at=captured_at,
        evaluation_date=EVAL,
        selection_rule_snapshot_id=C,
        security_id=security_id,
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecast_snapshot_id=D,
        selected_forecast_id=f"forecast-{security_id}",
        selected_forecaster_kind=ForecasterKind.MODEL,
        selected_model_family="fixture-model",
        selected_forecast_value=20_000_000.0,
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        tournament_forecast_snapshot_ids=(D, E),
        tournament_dependency_overlap=False,
        guardrail_evidence_id=GUARDRAIL,
    )


def _gap(view: DecisionViewSnapshot, captured_at: datetime) -> DecisionExpectationGapSnapshot:
    return DecisionExpectationGapSnapshot(
        captured_at=captured_at,
        evaluation_date=EVAL,
        decision_view_snapshot_id=view.snapshot_id,
        expectation_state_snapshot_id=F,
        price_implied_requirement_snapshot_id=None,
        security_id=view.security_id,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        consensus_gaps=(
            ConsensusGapObservation(
                provider_id="provider-a",
                source_evidence_id=A,
                observed_at=NOW - timedelta(hours=1),
                decision_value=20_000_000.0,
                consensus_value=18_000_000.0,
                unit=view.unit,
                absolute_gap=2_000_000.0,
                relative_gap=2_000_000.0 / 18_000_000.0,
            ),
        ),
        price_implied_gaps=(),
        flags=("price_implied_comparison_not_supplied",),
        guardrail_evidence_id=GUARDRAIL,
    )


def _underwriting(
    security_id: str,
    thesis_id: str,
    payoff_id: str,
    captured_at: datetime,
) -> UnderwritingReadinessSnapshot:
    tournament = ForecastTournamentAssessment(
        comparable=True,
        forecast_snapshot_ids=(D, E),
        forecast_ids=(f"a-{security_id}", f"b-{security_id}"),
        security_id=security_id,
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        primary_error_metric="absolute_error",
        distinct_forecaster_count=2,
        dependency_cluster_count=2,
        blockers=(),
        flags=(),
    )
    return UnderwritingReadinessSnapshot(
        captured_at=captured_at,
        evaluation_date=EVAL,
        thesis_snapshot_id=thesis_id,
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
        payoff_surface_snapshot_id=payoff_id,
        epistemic_defense_snapshot_id=None,
        required_elements_satisfied=("payoff_surface",),
        required_elements_missing=(),
        blockers=(),
        flags=(),
    )


def _persist_full_set(tmp_path: Path, *, security_id: str = "000660"):
    thesis_id = "1" * 64
    payoff = _payoff(security_id, thesis_id, NOW + timedelta(minutes=1))
    view = _view(security_id, NOW + timedelta(minutes=2))
    gap = _gap(view, NOW + timedelta(minutes=3))
    underwriting = _underwriting(
        security_id,
        thesis_id,
        payoff.snapshot_id,
        NOW + timedelta(minutes=4),
    )
    persist_payoff_surface(payoff, output_root=tmp_path / "payoff_surface")
    persist_decision_view(view, output_root=tmp_path)
    persist_decision_expectation_gap(gap, output_root=tmp_path)
    persist_underwriting_readiness(underwriting, output_root=tmp_path)
    return thesis_id, payoff, view, gap, underwriting


def test_writer_round_trip_reconstructs_all_package_components(tmp_path: Path) -> None:
    thesis_id, payoff, view, gap, underwriting = _persist_full_set(tmp_path)
    index = build_research_component_repository_index(
        tmp_path,
        as_of=NOW + timedelta(minutes=10),
    )

    assert index.latest_payoff(
        "000660",
        thesis_snapshot_id=thesis_id,
        horizon_trading_days=120,
        guardrail_evidence_id=GUARDRAIL,
    ) == payoff
    assert index.latest_decision_view(
        "000660",
        evaluation_date=EVAL,
        guardrail_evidence_id=GUARDRAIL,
    ) == view
    assert index.latest_expectation_gap(
        "000660",
        decision_view_snapshot_id=view.snapshot_id,
        evaluation_date=EVAL,
        guardrail_evidence_id=GUARDRAIL,
    ) == gap
    assert index.latest_underwriting(
        "000660",
        thesis_snapshot_id=thesis_id,
        evaluation_date=EVAL,
        lane=UnderwritingLane.DEEP,
        guardrail_evidence_id=GUARDRAIL,
    ) == underwriting


def test_future_components_are_validated_but_excluded_from_pit_selection(tmp_path: Path) -> None:
    thesis_id, payoff, view, gap, underwriting = _persist_full_set(tmp_path)
    index = build_research_component_repository_index(
        tmp_path,
        as_of=NOW + timedelta(seconds=30),
    )
    assert index.payoff_by_security == {}
    assert index.decision_view_by_security == {}
    assert index.expectation_gap_by_security == {}
    assert index.underwriting_by_security == {}
    assert payoff.captured_at > index.as_of
    assert view.captured_at > index.as_of
    assert gap.captured_at > index.as_of
    assert underwriting.captured_at > index.as_of
    assert thesis_id


def test_payload_tamper_fails_before_typed_selection(tmp_path: Path) -> None:
    _persist_full_set(tmp_path)
    directory = next(
        path
        for path in (tmp_path / "payoff_surface").iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    payload_path = directory / "payoff_surface.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["unknown_tamper"] = True
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ResearchComponentRepositoryError, match="complete persisted payload"):
        build_research_component_repository_index(
            tmp_path,
            as_of=NOW + timedelta(minutes=10),
        )


def test_manifest_and_pointer_tamper_fail_closed(tmp_path: Path) -> None:
    _persist_full_set(tmp_path)
    manifest_path = next(
        path / "manifest.json"
        for path in (tmp_path / "decision_view").iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target_price_enabled"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ResearchComponentRepositoryError, match="target_price"):
        build_research_component_repository_index(
            tmp_path,
            as_of=NOW + timedelta(minutes=10),
        )

    _, _, view, _, _ = _persist_full_set(tmp_path / "second")
    pointer = tmp_path / "second" / "decision_view" / "latest_decision_view.json"
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    pointer_payload["snapshot_id"] = "9" * 64
    pointer.write_text(json.dumps(pointer_payload), encoding="utf-8")
    assert view.snapshot_id != "9" * 64
    with pytest.raises(ResearchComponentRepositoryError, match="missing snapshot"):
        build_research_component_repository_index(
            tmp_path / "second",
            as_of=NOW + timedelta(minutes=10),
        )
