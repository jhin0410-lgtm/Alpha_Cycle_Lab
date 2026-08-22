from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
    ResearchRoundSnapshot,
    ResearchRoundStatus,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    AnalysisRequestSnapshot,
    ResearchProcessObservabilitySummary,
    ResearchRunKind,
    ResearchRunLedgerSnapshot,
    bind_orchestrated_run,
    build_pre_orchestration_blocked_run,
    build_research_run_ledger,
    latest_run_for_security,
    persist_analysis_request,
    persist_research_run,
    persist_research_run_ledger,
    runs_for_security,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane

NOW = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 22)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def _request(*, request_id: str = "request-1") -> AnalysisRequestSnapshot:
    return AnalysisRequestSnapshot(
        request_id=request_id,
        requested_at=NOW,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Compare SK hynix and Samsung Electronics prospectively.",
        guardrail_evidence_id=GUARDRAIL,
        tags=("semiconductor",),
    )


def _round(
    *,
    status: ResearchRoundStatus = ResearchRoundStatus.PROSPECTIVE_READY_FOR_REGISTRATION,
    blockers: tuple[ResearchRoundBlocker, ...] = (),
    captured_at: datetime | None = None,
) -> ResearchRoundSnapshot:
    registered = status is ResearchRoundStatus.PROSPECTIVE_REGISTERED
    return ResearchRoundSnapshot(
        round_id="round-1",
        mode=ResearchRoundMode.PROSPECTIVE,
        status=status,
        captured_at=captured_at or NOW + timedelta(seconds=5),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        thesis_snapshot_ids=(SHA_A, SHA_B),
        underwriting_snapshot_ids=(SHA_C, SHA_D),
        payoff_surface_snapshot_ids=("1" * 64, "2" * 64),
        decision_view_snapshot_ids=(),
        expectation_gap_snapshot_ids=(),
        opportunity_candidate_snapshot_ids=("3" * 64, "4" * 64),
        opportunity_set_snapshot_id=(None if blockers else "5" * 64),
        expectation_overlay_snapshot_id=None,
        prospective_registration_snapshot_id=("6" * 64 if registered else None),
        comparable_security_ids=(() if blockers else ("000660", "005930")),
        base_pareto_frontier_security_ids=(() if blockers else ("000660",)),
        expectation_pareto_frontier_security_ids=(),
        blockers=blockers,
        flags=("expectation_overlay_not_requested",),
        guardrail_evidence_id=GUARDRAIL,
    )


def _bound_run(
    request: AnalysisRequestSnapshot | None = None,
    round_snapshot: ResearchRoundSnapshot | None = None,
    *,
    run_id: str = "run-1",
    offset_seconds: int = 0,
):
    request = request or _request()
    round_snapshot = round_snapshot or _round()
    return bind_orchestrated_run(
        request,
        round_snapshot,
        run_id=run_id,
        started_at=NOW + timedelta(seconds=10 + offset_seconds),
        completed_at=NOW + timedelta(seconds=20 + offset_seconds),
    )


def test_request_supports_single_security_history_even_before_cross_sectional_round() -> None:
    request = replace(_request(), security_ids=("000660",))
    assert request.security_ids == ("000660",)
    assert request.payload_without_id()["append_only_request"] is True


def test_request_rejects_invalid_horizon() -> None:
    with pytest.raises(ValueError, match="60, 120, or 250"):
        replace(_request(), horizon_trading_days=90)


def test_pre_orchestration_blocker_records_missing_typed_input() -> None:
    request = replace(_request(), security_ids=("000660",))
    blocker = ResearchRoundBlocker(
        component="thesis",
        code="investment_thesis_snapshot_missing",
        detail="no persisted PIT InvestmentThesisSnapshot exists",
        security_id="000660",
    )
    run = build_pre_orchestration_blocked_run(
        request,
        run_id="preflight-1",
        started_at=NOW + timedelta(seconds=1),
        completed_at=NOW + timedelta(seconds=2),
        blockers=(blocker,),
    )
    assert run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    assert run.blocked is True
    assert run.research_round_snapshot_id is None
    assert run.opportunity_set_snapshot_id is None


def test_pre_orchestration_blocked_run_requires_explicit_blocker() -> None:
    with pytest.raises(ValueError, match="requires at least one blocker"):
        build_pre_orchestration_blocked_run(
            _request(),
            run_id="bad-preflight",
            started_at=NOW + timedelta(seconds=1),
            completed_at=NOW + timedelta(seconds=2),
            blockers=(),
        )


def test_orchestrated_run_binds_exact_round_identity() -> None:
    request = _request()
    round_snapshot = _round()
    run = _bound_run(request, round_snapshot)
    assert run.research_round_snapshot_id == round_snapshot.snapshot_id
    assert run.round_status is ResearchRoundStatus.PROSPECTIVE_READY_FOR_REGISTRATION
    assert run.opportunity_set_snapshot_id == round_snapshot.opportunity_set_snapshot_id
    assert run.blockers == round_snapshot.blockers


def test_orchestrated_binding_rejects_security_drift() -> None:
    request = replace(_request(), security_ids=("005930", "000660"))
    with pytest.raises(ValueError, match="security mismatch"):
        _bound_run(request=request)


def test_orchestrated_binding_rejects_horizon_drift() -> None:
    request = replace(_request(), horizon_trading_days=60)
    with pytest.raises(ValueError, match="horizon mismatch"):
        _bound_run(request=request)


def test_prospective_round_cannot_predate_request() -> None:
    round_snapshot = _round(captured_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="cannot predate the request"):
        _bound_run(round_snapshot=round_snapshot)


def test_replay_round_may_reconstruct_a_historical_cutoff_after_request() -> None:
    request = replace(
        _request(),
        mode=ResearchRoundMode.REPLAY,
        evaluation_date=date(2026, 7, 1),
    )
    ready = _round(captured_at=NOW - timedelta(days=30))
    replay = replace(
        ready,
        mode=ResearchRoundMode.REPLAY,
        status=ResearchRoundStatus.REPLAY_READY,
        evaluation_date=date(2026, 7, 1),
    )
    run = _bound_run(request, replay)
    assert run.mode is ResearchRoundMode.REPLAY
    assert run.round_status is ResearchRoundStatus.REPLAY_READY


def test_summary_counts_process_observability_without_claiming_skill() -> None:
    request_a = _request(request_id="request-a")
    request_b = replace(
        _request(request_id="request-b"),
        security_ids=("042660",),
        request_text="Inspect Hanwha Ocean research readiness.",
    )
    run_a = _bound_run(request_a, run_id="run-a")
    blocker = ResearchRoundBlocker(
        component="thesis",
        code="investment_thesis_snapshot_missing",
        detail="typed thesis is missing",
        security_id="042660",
    )
    run_b = build_pre_orchestration_blocked_run(
        request_b,
        run_id="run-b",
        started_at=NOW + timedelta(seconds=30),
        completed_at=NOW + timedelta(seconds=35),
        blockers=(blocker,),
    )
    ledger = build_research_run_ledger(
        (request_a, request_b),
        (run_a, run_b),
        built_at=NOW + timedelta(minutes=2),
    )

    summary = ledger.summary
    assert summary.request_count == 2
    assert summary.run_count == 2
    assert summary.orchestrated_run_count == 1
    assert summary.pre_orchestration_blocked_run_count == 1
    assert summary.blocked_run_count == 1
    assert summary.opportunity_set_run_count == 1
    assert summary.unique_security_count == 3
    assert summary.mean_blockers_per_run == 0.5
    assert dict(summary.blocker_code_counts) == {"investment_thesis_snapshot_missing": 1}
    payload = summary.payload()
    assert payload["process_metrics_only"] is True
    assert payload["investment_alpha_claimed"] is False
    assert payload["forecast_calibration_claimed"] is False


def test_ledger_rejects_orphan_run() -> None:
    run = _bound_run()
    with pytest.raises(ValueError, match="bind to a request"):
        ResearchRunLedgerSnapshot(
            built_at=NOW + timedelta(minutes=1),
            requests=(),
            runs=(run,),
            summary=ResearchProcessObservabilitySummary(
                request_count=0,
                run_count=1,
                orchestrated_run_count=1,
                pre_orchestration_blocked_run_count=0,
                blocked_run_count=0,
                prospective_run_count=1,
                replay_run_count=0,
                prospective_registered_run_count=0,
                opportunity_set_run_count=1,
                expectation_overlay_run_count=0,
                unique_security_count=2,
                mean_blockers_per_run=0.0,
                median_blockers_per_run=0.0,
                mean_duration_seconds=10.0,
                median_duration_seconds=10.0,
                status_counts=(("prospective_ready_for_registration", 1),),
                blocker_component_counts=(),
                blocker_code_counts=(),
            ),
        )


def test_ledger_rejects_duplicate_round_snapshot_to_avoid_double_counting() -> None:
    request_a = _request(request_id="request-a")
    request_b = _request(request_id="request-b")
    round_snapshot = _round()
    run_a = _bound_run(request_a, round_snapshot, run_id="run-a")
    run_b = _bound_run(
        request_b,
        round_snapshot,
        run_id="run-b",
        offset_seconds=30,
    )
    with pytest.raises(ValueError, match="cannot be counted twice"):
        build_research_run_ledger(
            (request_a, request_b),
            (run_a, run_b),
            built_at=NOW + timedelta(minutes=2),
        )


def test_ledger_rejects_fabricated_summary() -> None:
    request = _request()
    run = _bound_run(request)
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=NOW + timedelta(minutes=1),
    )
    bad = replace(ledger.summary, blocked_run_count=1)
    with pytest.raises(ValueError, match="summary must be recomputed"):
        ResearchRunLedgerSnapshot(
            built_at=ledger.built_at,
            requests=ledger.requests,
            runs=ledger.runs,
            summary=bad,
        )


def test_security_history_and_latest_run_are_deterministic() -> None:
    request_a = _request(request_id="request-a")
    request_b = _request(request_id="request-b")
    round_a = _round()
    round_b = replace(
        _round(),
        round_id="round-2",
        captured_at=NOW + timedelta(seconds=35),
    )
    run_a = _bound_run(request_a, round_a, run_id="run-a")
    run_b = _bound_run(
        request_b,
        round_b,
        run_id="run-b",
        offset_seconds=30,
    )
    ledger = build_research_run_ledger(
        (request_a, request_b),
        (run_b, run_a),
        built_at=NOW + timedelta(minutes=2),
    )
    history = runs_for_security(ledger, "000660")
    assert tuple(item.run_id for item in history) == ("run-a", "run-b")
    assert latest_run_for_security(ledger, "000660") == run_b
    assert latest_run_for_security(ledger, "999999") is None


def test_payload_explicitly_disables_decision_retraining_and_execution() -> None:
    request = _request()
    run = _bound_run(request)
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=NOW + timedelta(minutes=1),
    )
    payload = ledger.payload_without_id()
    assert payload["descriptive_observability_only"] is True
    assert payload["predictive_skill_inference_enabled"] is False
    assert payload["decision_quality_score_enabled"] is False
    assert payload["portfolio_optimization_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_content_addressed_persistence_is_immutable(tmp_path) -> None:
    request = _request()
    run = _bound_run(request)
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=NOW + timedelta(minutes=1),
    )
    request_path = persist_analysis_request(request, output_root=tmp_path)
    run_path = persist_research_run(run, output_root=tmp_path)
    ledger_path = persist_research_run_ledger(ledger, output_root=tmp_path)
    assert request.snapshot_id in request_path.name
    assert run.snapshot_id in run_path.name
    assert ledger.snapshot_id in ledger_path.name
    with pytest.raises(FileExistsError):
        persist_analysis_request(request, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        persist_research_run(run, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        persist_research_run_ledger(ledger, output_root=tmp_path)
