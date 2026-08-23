from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request

NOW = datetime(2026, 8, 23, 6, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 23)


def _record(tmp_path, *, request_id: str, offset: int = 0):
    requested_at = NOW + timedelta(seconds=offset)
    return record_analysis_request(
        request_id=request_id,
        requested_at=requested_at,
        recorded_at=requested_at + timedelta(seconds=1),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Compare SK hynix and Samsung Electronics prospectively.",
        artifact_root=tmp_path,
        tags=("semiconductor",),
    )


def test_first_request_creates_pending_ledger_and_observatory_state(tmp_path) -> None:
    receipt = _record(tmp_path, request_id="request-1")

    assert receipt.request_path.exists()
    assert receipt.ledger_path.exists()
    assert not (tmp_path / ".research_request_intake.lock").exists()
    assert receipt.ledger.summary.request_count == 1
    assert receipt.ledger.summary.run_count == 0
    assert receipt.payload()["state"] == "request_pending"
    assert receipt.payload()["research_executed"] is False

    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert tuple(row.security_id for row in state.inbox) == ("000660", "005930")
    assert {row.state for row in state.inbox} == {"request_pending"}


def test_second_request_appends_without_rewriting_prior_history(tmp_path) -> None:
    first = _record(tmp_path, request_id="request-1")
    second = _record(tmp_path, request_id="request-2", offset=10)

    assert first.ledger_path.exists()
    assert second.ledger_path.exists()
    assert first.ledger_path != second.ledger_path
    assert first.ledger.summary.request_count == 1
    assert second.ledger.summary.request_count == 2
    assert tuple(item.request_id for item in second.ledger.requests) == (
        "request-1",
        "request-2",
    )


def test_duplicate_request_id_is_rejected_before_new_persistence(tmp_path) -> None:
    first = _record(tmp_path, request_id="duplicate")
    request_files_before = set((tmp_path / "analysis_request_v2_1").glob("*.json"))
    ledger_files_before = set((tmp_path / "research_run_ledger_v2_1").glob("*.json"))

    with pytest.raises(ValueError, match="request_id already exists"):
        _record(tmp_path, request_id="duplicate", offset=10)

    assert first.request_path.exists()
    assert set((tmp_path / "analysis_request_v2_1").glob("*.json")) == request_files_before
    assert set((tmp_path / "research_run_ledger_v2_1").glob("*.json")) == ledger_files_before


def test_existing_intake_lock_fails_closed_before_history_forks(tmp_path) -> None:
    lock_path = tmp_path / ".research_request_intake.lock"
    lock_path.write_text("stale or active lock\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        _record(tmp_path, request_id="locked")

    assert not (tmp_path / "analysis_request_v2_1").exists()
    assert not (tmp_path / "research_run_ledger_v2_1").exists()
    assert lock_path.exists()


def test_recorded_at_cannot_precede_request(tmp_path) -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        record_analysis_request(
            request_id="bad-time",
            requested_at=NOW,
            recorded_at=NOW - timedelta(seconds=1),
            evaluation_date=EVALUATION_DATE,
            horizon_trading_days=120,
            security_ids=("000660",),
            mode=ResearchRoundMode.PROSPECTIVE,
            requested_lane=UnderwritingLane.DEEP,
            request_text="Analyze SK hynix.",
            artifact_root=tmp_path,
        )


def test_single_security_request_is_supported_for_research_inbox(tmp_path) -> None:
    receipt = record_analysis_request(
        request_id="single-security",
        requested_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=60,
        security_ids=("000660",),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.FAST,
        request_text="Inspect SK hynix research readiness.",
        artifact_root=tmp_path,
    )
    assert receipt.request.security_ids == ("000660",)
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert len(state.inbox) == 1
    assert state.inbox[0].state == "request_pending"


def test_receipt_explicitly_denies_investment_action(tmp_path) -> None:
    receipt = _record(tmp_path, request_id="safe-boundary")
    payload = receipt.payload()
    assert payload["research_executed"] is False
    assert payload["investment_conclusion_created"] is False
    assert payload["automatic_execution_enabled"] is False
