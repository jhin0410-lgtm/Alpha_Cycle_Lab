from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
    build_observatory_state,
    load_latest_observatory_state,
)

NOW = datetime(2026, 8, 23, 0, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 22)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id


def _request(request_id: str, requested_at: datetime) -> AnalysisRequestSnapshot:
    return AnalysisRequestSnapshot(
        request_id=request_id,
        requested_at=requested_at,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=("000660",),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text=f"Research request {request_id}.",
        guardrail_evidence_id=GUARDRAIL,
        tags=("observatory-review-regression",),
    )


def _blocked_run(
    request: AnalysisRequestSnapshot,
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
):
    return build_pre_orchestration_blocked_run(
        request,
        run_id=run_id,
        started_at=started_at,
        completed_at=completed_at,
        blockers=(
            ResearchRoundBlocker(
                component="thesis",
                code="investment_thesis_snapshot_missing",
                detail="typed thesis missing",
                security_id="000660",
            ),
        ),
    )


def test_delayed_old_request_run_cannot_satisfy_newer_request() -> None:
    old_request = _request("request-old", NOW)
    new_request = _request("request-new", NOW + timedelta(seconds=10))
    delayed_old_run = _blocked_run(
        old_request,
        run_id="run-old-delayed",
        started_at=NOW + timedelta(seconds=20),
        completed_at=NOW + timedelta(seconds=22),
    )
    ledger = build_research_run_ledger(
        (old_request, new_request),
        (delayed_old_run,),
        built_at=NOW + timedelta(minutes=1),
    )

    row = build_observatory_state("not-persisted.json", ledger).inbox[0]

    assert row.security_id == "000660"
    assert row.latest_request_at == new_request.requested_at
    assert row.latest_run_completed_at == delayed_old_run.completed_at
    assert row.state == "request_pending"
    assert row.blocker_count == 0
    assert row.opportunity_set_available is False
    assert row.expectation_overlay_available is False
    assert row.prospective_registered is False


def test_latest_loader_does_not_materialize_older_corrupt_ledger_body(
    tmp_path: Path,
) -> None:
    old_directory = tmp_path / "research_run_ledger_v2_1"
    old_directory.mkdir(parents=True)
    old_path = old_directory / f"{'a' * 64}.json"
    old_path.write_text(
        "{\n"
        f'  "built_at": "{(NOW + timedelta(minutes=1)).isoformat()}",\n'
        '  "this_body_is_intentionally": [not valid json\n',
        encoding="utf-8",
    )

    request = _request("request-new", NOW + timedelta(minutes=2))
    run = _blocked_run(
        request,
        run_id="run-new",
        started_at=NOW + timedelta(minutes=2, seconds=1),
        completed_at=NOW + timedelta(minutes=2, seconds=2),
    )
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=NOW + timedelta(minutes=3),
    )
    latest_path = persist_research_run_ledger(ledger, output_root=tmp_path)

    state = load_latest_observatory_state(tmp_path)

    assert state is not None
    assert state.source_path == latest_path
    assert state.snapshot_id == ledger.snapshot_id
