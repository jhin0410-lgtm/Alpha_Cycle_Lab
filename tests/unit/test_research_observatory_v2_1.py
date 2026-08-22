from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    AnalysisRequestSnapshot,
    build_pre_orchestration_blocked_run,
    build_research_run_ledger,
    persist_research_run_ledger,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_observatory_v2_1 import (
    ObservatoryDataError,
    build_observatory_state,
    load_latest_observatory_state,
    load_research_run_ledger,
)

NOW = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 22)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id


def _request(
    request_id: str,
    security_ids: tuple[str, ...],
    *,
    requested_at: datetime = NOW,
) -> AnalysisRequestSnapshot:
    return AnalysisRequestSnapshot(
        request_id=request_id,
        requested_at=requested_at,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=security_ids,
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text=f"Research {', '.join(security_ids)}.",
        guardrail_evidence_id=GUARDRAIL,
        tags=("observatory-test",),
    )


def _blocked_run(
    request: AnalysisRequestSnapshot,
    *,
    run_id: str,
    offset_seconds: int,
):
    blockers = tuple(
        ResearchRoundBlocker(
            component="thesis",
            code="investment_thesis_snapshot_missing",
            detail="no persisted PIT InvestmentThesisSnapshot exists",
            security_id=security_id,
        )
        for security_id in request.security_ids
    )
    return build_pre_orchestration_blocked_run(
        request,
        run_id=run_id,
        started_at=NOW + timedelta(seconds=offset_seconds),
        completed_at=NOW + timedelta(seconds=offset_seconds + 2),
        blockers=blockers,
        flags=("typed_input_missing",),
    )


def _persist_fixture(
    tmp_path: Path,
    *,
    built_at: datetime = NOW + timedelta(minutes=1),
) -> tuple[Path, AnalysisRequestSnapshot]:
    request = _request("request-1", ("000660", "005930"))
    run = _blocked_run(request, run_id="run-1", offset_seconds=5)
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=built_at,
    )
    return persist_research_run_ledger(ledger, output_root=tmp_path), request


def _content_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_loader_reconstructs_content_addressed_typed_ledger(tmp_path: Path) -> None:
    path, request = _persist_fixture(tmp_path)
    ledger = load_research_run_ledger(path)

    assert ledger.requests == (request,)
    assert ledger.summary.run_count == 1
    assert ledger.summary.blocked_run_count == 1
    assert ledger.snapshot_id == path.stem


def test_loader_rejects_payload_tampering(tmp_path: Path) -> None:
    path, _ = _persist_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["summary"]["blocked_run_count"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ObservatoryDataError, match="snapshot_id"):
        load_research_run_ledger(path)


def test_loader_rejects_forged_hash_when_typed_summary_is_inconsistent(
    tmp_path: Path,
) -> None:
    path, _ = _persist_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["summary"]["blocked_run_count"] = 0
    without_id = dict(payload)
    del without_id["snapshot_id"]
    forged_id = _content_id(without_id)
    payload["snapshot_id"] = forged_id
    forged_path = path.with_name(f"{forged_id}.json")
    forged_path.write_text(json.dumps(payload), encoding="utf-8")
    path.unlink()

    with pytest.raises(ValueError, match="summary must be recomputed"):
        load_research_run_ledger(forged_path)


def test_loader_rejects_filename_identity_drift(tmp_path: Path) -> None:
    path, _ = _persist_fixture(tmp_path)
    renamed = path.with_name(f"{'f' * 64}.json")
    path.rename(renamed)

    with pytest.raises(ObservatoryDataError, match="filename"):
        load_research_run_ledger(renamed)


def test_latest_loader_uses_embedded_built_at_not_filesystem_mtime(tmp_path: Path) -> None:
    old_path, _ = _persist_fixture(tmp_path, built_at=NOW + timedelta(minutes=1))

    request = _request(
        "request-new",
        ("042660",),
        requested_at=NOW + timedelta(minutes=2),
    )
    run = build_pre_orchestration_blocked_run(
        request,
        run_id="run-new",
        started_at=NOW + timedelta(minutes=2, seconds=1),
        completed_at=NOW + timedelta(minutes=2, seconds=2),
        blockers=(
            ResearchRoundBlocker(
                component="thesis",
                code="investment_thesis_snapshot_missing",
                detail="typed thesis missing",
                security_id="042660",
            ),
        ),
    )
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=NOW + timedelta(minutes=3),
    )
    new_path = persist_research_run_ledger(ledger, output_root=tmp_path)
    old_path.touch()

    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert state.source_path == new_path
    assert state.snapshot_id == ledger.snapshot_id


def test_latest_loader_returns_none_for_empty_artifact_root(tmp_path: Path) -> None:
    assert load_latest_observatory_state(tmp_path) is None


def test_inbox_exposes_pre_orchestration_blocker_without_inventing_decision(
    tmp_path: Path,
) -> None:
    path, _ = _persist_fixture(tmp_path)
    ledger = load_research_run_ledger(path)
    state = build_observatory_state(path, ledger)

    assert tuple(row.security_id for row in state.inbox) == ("000660", "005930")
    assert all(row.state == "pre_orchestration_blocked" for row in state.inbox)
    assert all(row.blocker_count == 2 for row in state.inbox)
    assert all(row.opportunity_set_available is False for row in state.inbox)
    assert all(row.prospective_registered is False for row in state.inbox)
    assert len(state.blockers) == 2


def test_inbox_marks_newer_unexecuted_request_as_pending(tmp_path: Path) -> None:
    old_request = _request("request-old", ("000660",))
    run = _blocked_run(old_request, run_id="run-old", offset_seconds=5)
    new_request = _request(
        "request-new",
        ("000660",),
        requested_at=NOW + timedelta(seconds=20),
    )
    ledger = build_research_run_ledger(
        (old_request, new_request),
        (run,),
        built_at=NOW + timedelta(minutes=1),
    )
    state = build_observatory_state(tmp_path / "not-persisted.json", ledger)

    assert len(state.inbox) == 1
    assert state.inbox[0].state == "request_pending"
    assert state.inbox[0].latest_run_completed_at == run.completed_at


def test_history_and_blockers_are_newest_first() -> None:
    request_a = _request("request-a", ("000660",))
    request_b = _request(
        "request-b",
        ("042660",),
        requested_at=NOW + timedelta(seconds=20),
    )
    run_a = _blocked_run(request_a, run_id="run-a", offset_seconds=5)
    run_b = build_pre_orchestration_blocked_run(
        request_b,
        run_id="run-b",
        started_at=NOW + timedelta(seconds=21),
        completed_at=NOW + timedelta(seconds=22),
        blockers=(
            ResearchRoundBlocker(
                component="thesis",
                code="investment_thesis_snapshot_missing",
                detail="typed thesis missing",
                security_id="042660",
            ),
        ),
    )
    ledger = build_research_run_ledger(
        (request_a, request_b),
        (run_a, run_b),
        built_at=NOW + timedelta(minutes=1),
    )
    state = build_observatory_state("ledger.json", ledger)

    assert tuple(row.run_id for row in state.history) == ("run-b", "run-a")
    assert state.blockers[0].run_id == "run-b"


def test_health_payload_explicitly_preserves_read_only_boundary(tmp_path: Path) -> None:
    path, _ = _persist_fixture(tmp_path)
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    health = state.health_payload()

    assert health["source_path"] == str(path)
    assert health["content_address_verified"] is True
    assert health["read_only_adapter"] is True
    assert health["investment_logic_reimplemented"] is False
    assert health["predictive_skill_inference_enabled"] is False
    assert health["portfolio_optimization_enabled"] is False
    assert health["automatic_execution_enabled"] is False


def test_loader_rejects_stale_child_snapshot_even_if_ledger_hash_is_forged(
    tmp_path: Path,
) -> None:
    path, _ = _persist_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["requests"][0]["request_text"] = "Changed after persistence"
    without_ledger_id = dict(payload)
    del without_ledger_id["snapshot_id"]
    forged_id = _content_id(without_ledger_id)
    payload["snapshot_id"] = forged_id
    forged_path = path.with_name(f"{forged_id}.json")
    forged_path.write_text(json.dumps(payload), encoding="utf-8")
    path.unlink()

    with pytest.raises(ObservatoryDataError, match="analysis request snapshot"):
        load_research_run_ledger(forged_path)
