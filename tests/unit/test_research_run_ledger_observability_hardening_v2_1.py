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
    bind_orchestrated_run,
    build_pre_orchestration_blocked_run,
    build_research_run_ledger,
    persist_analysis_request,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane

NOW = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 22)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id


def _request(request_id: str, security_id: str) -> AnalysisRequestSnapshot:
    return AnalysisRequestSnapshot(
        request_id=request_id,
        requested_at=NOW,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=(security_id,),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text=f"Research {security_id}.",
        guardrail_evidence_id=GUARDRAIL,
    )


def _cross_sectional_request() -> AnalysisRequestSnapshot:
    return replace(
        _request("request-cross", "000660"),
        security_ids=("000660", "005930"),
    )


def _round(*, captured_at: datetime) -> ResearchRoundSnapshot:
    return ResearchRoundSnapshot(
        round_id="round-chronology",
        mode=ResearchRoundMode.PROSPECTIVE,
        status=ResearchRoundStatus.PROSPECTIVE_READY_FOR_REGISTRATION,
        captured_at=captured_at,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        thesis_snapshot_ids=("a" * 64, "b" * 64),
        underwriting_snapshot_ids=("c" * 64, "d" * 64),
        payoff_surface_snapshot_ids=("1" * 64, "2" * 64),
        decision_view_snapshot_ids=(),
        expectation_gap_snapshot_ids=(),
        opportunity_candidate_snapshot_ids=("3" * 64, "4" * 64),
        opportunity_set_snapshot_id="5" * 64,
        expectation_overlay_snapshot_id=None,
        prospective_registration_snapshot_id=None,
        comparable_security_ids=("000660", "005930"),
        base_pareto_frontier_security_ids=("000660",),
        expectation_pareto_frontier_security_ids=(),
        blockers=(),
        flags=("expectation_overlay_not_requested",),
        guardrail_evidence_id=GUARDRAIL,
    )


def _preflight_run(
    request: AnalysisRequestSnapshot,
    *,
    run_id: str,
    completed_offset: int,
):
    blocker = ResearchRoundBlocker(
        component="thesis",
        code="investment_thesis_snapshot_missing",
        detail="typed thesis is missing",
        security_id=request.security_ids[0],
    )
    return build_pre_orchestration_blocked_run(
        request,
        run_id=run_id,
        started_at=NOW + timedelta(seconds=completed_offset - 1),
        completed_at=NOW + timedelta(seconds=completed_offset),
        blockers=(blocker,),
    )


def test_duplicate_persistence_does_not_delete_existing_artifact(tmp_path) -> None:
    request = _request("request-persist", "000660")
    path = persist_analysis_request(request, output_root=tmp_path)
    original = path.read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        persist_analysis_request(request, output_root=tmp_path)

    assert path.exists()
    assert path.read_text(encoding="utf-8") == original


def test_digest_validation_rejects_signed_or_noncanonical_hex() -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(_request("request-sha", "000660"), guardrail_evidence_id="-" + "0" * 63)
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(_request("request-sha", "000660"), guardrail_evidence_id="A" * 64)


def test_orchestrated_round_cutoff_cannot_follow_run_completion() -> None:
    request = _cross_sectional_request()
    round_snapshot = _round(captured_at=NOW + timedelta(seconds=30))
    with pytest.raises(ValueError, match="cutoff cannot be after run completion"):
        bind_orchestrated_run(
            request,
            round_snapshot,
            run_id="run-future-round",
            started_at=NOW + timedelta(seconds=5),
            completed_at=NOW + timedelta(seconds=20),
        )


def test_ledger_hash_is_independent_of_input_iteration_order() -> None:
    request_a = _request("request-a", "000660")
    request_b = _request("request-b", "042660")
    run_a = _preflight_run(request_a, run_id="run-a", completed_offset=10)
    run_b = _preflight_run(request_b, run_id="run-b", completed_offset=20)
    built_at = NOW + timedelta(minutes=1)

    forward = build_research_run_ledger(
        (request_a, request_b),
        (run_a, run_b),
        built_at=built_at,
    )
    reversed_input = build_research_run_ledger(
        (request_b, request_a),
        (run_b, run_a),
        built_at=built_at,
    )

    assert forward.snapshot_id == reversed_input.snapshot_id
    assert forward.requests == reversed_input.requests
    assert forward.runs == reversed_input.runs
