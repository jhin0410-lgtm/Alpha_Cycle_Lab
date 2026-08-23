from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from alpha_cycle.intelligence.decision_thesis_v2 import (
    ClaimDirection,
    EpistemicStatus,
    InvestmentThesisSnapshot,
    ThesisClaim,
    ThesisStatus,
    ThesisUncertainty,
    UncertaintyDimension,
    UncertaintyLevel,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.research_run_ledger_v2_1 import ResearchRunKind
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.investment_thesis_repository_v2_1 import persist_investment_thesis
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request
from alpha_cycle.research_request_preflight_v2_1 import preflight_pending_request_theses

NOW = datetime(2026, 8, 23, 6, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 23)


def _uncertainty() -> ThesisUncertainty:
    dimension = UncertaintyDimension(
        level=UncertaintyLevel.HIGH,
        rationale="Evidence remains incomplete during preflight.",
    )
    return ThesisUncertainty(
        evidence=dimension,
        model=dimension,
        regime=dimension,
        expectation=dimension,
        catalyst=dimension,
        valuation=dimension,
    )


def _thesis(security_id: str, captured_at: datetime) -> InvestmentThesisSnapshot:
    return InvestmentThesisSnapshot(
        thesis_id=f"thesis-{security_id}",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=captured_at,
        security_id=security_id,
        horizon_trading_days=120,
        variant_view="Research priority; no investment conclusion.",
        why_now="Prospective research requested.",
        claims=(
            ThesisClaim(
                claim_id="claim-1",
                category="industry_cycle",
                statement="The transmission remains an economic hypothesis.",
                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
                direction=ClaimDirection.MIXED,
            ),
        ),
        catalysts=(),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=(),
        first_rejection_risk="The proposed mechanism may not transmit to earnings.",
        portfolio_overlap=(),
        opportunity_set_refs=(),
        status=ThesisStatus.RESEARCH_PRIORITY,
    )


def _request(tmp_path) -> None:
    record_analysis_request(
        request_id="live-semiconductor-round",
        requested_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Compare SK hynix and Samsung Electronics prospectively.",
        artifact_root=tmp_path,
        tags=("semiconductor",),
    )


def test_missing_theses_become_explicit_pre_orchestration_blockers(tmp_path) -> None:
    _request(tmp_path)
    receipt = preflight_pending_request_theses(
        request_id="live-semiconductor-round",
        run_id="preflight-1",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    assert receipt.changed_history is True
    assert receipt.changed_current_state is True
    assert receipt.ready_for_package_assembly is False
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    assert tuple(item.security_id for item in receipt.blockers) == ("000660", "005930")
    assert {item.code for item in receipt.blockers} == {
        "investment_thesis_snapshot_missing"
    }

    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert state.ledger.summary.blocked_run_count == 1
    assert len(state.blockers) == 2
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}


def test_identical_missing_thesis_preflight_is_idempotent(tmp_path) -> None:
    _request(tmp_path)
    first = preflight_pending_request_theses(
        request_id="live-semiconductor-round",
        run_id="preflight-1",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    second = preflight_pending_request_theses(
        request_id="live-semiconductor-round",
        run_id="preflight-2",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )
    assert first.changed_history is True
    assert second.changed_history is False
    assert second.changed_current_state is False
    assert second.run == first.run
    assert second.ledger.snapshot_id == first.ledger.snapshot_id
    assert second.preflight_state.snapshot_id == first.preflight_state.snapshot_id


def test_partial_thesis_progress_changes_blocker_history(tmp_path) -> None:
    _request(tmp_path)
    first = preflight_pending_request_theses(
        request_id="live-semiconductor-round",
        run_id="preflight-1",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    persist_investment_thesis(
        _thesis("000660", NOW + timedelta(minutes=1, seconds=10)),
        artifact_root=tmp_path,
    )
    second = preflight_pending_request_theses(
        request_id="live-semiconductor-round",
        run_id="preflight-2",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )
    assert first.changed_history is True
    assert second.changed_history is True
    assert second.changed_current_state is True
    assert tuple(item.security_id for item in second.blockers) == ("005930",)
    assert tuple(item.security_id for item in second.thesis_snapshots) == ("000660",)
    assert second.ledger.summary.run_count == 2


def test_complete_typed_theses_publish_ready_state_without_changing_ledger_schema(
    tmp_path,
) -> None:
    _request(tmp_path)
    for security_id in ("000660", "005930"):
        persist_investment_thesis(
            _thesis(security_id, NOW + timedelta(seconds=10)),
            artifact_root=tmp_path,
        )
    receipt = preflight_pending_request_theses(
        request_id="live-semiconductor-round",
        run_id="preflight-ready",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    assert receipt.ready_for_package_assembly is True
    assert receipt.changed_history is False
    assert receipt.changed_current_state is True
    assert receipt.run is None
    assert receipt.ledger.summary.run_count == 0
    assert tuple(item.security_id for item in receipt.thesis_snapshots) == (
        "000660",
        "005930",
    )
    payload = receipt.payload()
    assert payload["ledger_schema_changed"] is False
    assert payload["orchestrator_executed"] is False
    assert payload["investment_conclusion_created"] is False
    assert payload["automatic_execution_enabled"] is False

    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert state.ledger.summary.run_count == 0
    assert {row.state for row in state.inbox} == {"pre_orchestration_ready"}
    assert {row.blocker_count for row in state.inbox} == {0}


def test_future_thesis_does_not_satisfy_preflight(tmp_path) -> None:
    _request(tmp_path)
    persist_investment_thesis(
        _thesis("000660", NOW + timedelta(days=1)),
        artifact_root=tmp_path,
    )
    receipt = preflight_pending_request_theses(
        request_id="live-semiconductor-round",
        run_id="preflight-future",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    assert {item.security_id for item in receipt.blockers} == {"000660", "005930"}
