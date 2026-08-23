from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

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
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_observatory_v2_1 import build_research_inbox
from alpha_cycle.research_preflight_state_v2_1 import (
    CurrentResearchThesisPreflightState,
    build_research_thesis_preflight_state,
)

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id


def _request() -> AnalysisRequestSnapshot:
    return AnalysisRequestSnapshot(
        request_id="observatory-precedence",
        requested_at=NOW,
        evaluation_date=date(2026, 8, 23),
        horizon_trading_days=120,
        security_ids=("000660",),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Exercise operational-state precedence.",
        guardrail_evidence_id=GUARDRAIL,
    )


def _blocked_run(request: AnalysisRequestSnapshot, at: datetime):
    return build_pre_orchestration_blocked_run(
        request,
        run_id=f"package-blocked-{at.minute}",
        started_at=at,
        completed_at=at,
        blockers=(
            ResearchRoundBlocker(
                component="research_package",
                code="payoff_surface_missing_or_incompatible",
                detail="payoff surface missing or incompatible",
                security_id="000660",
            ),
        ),
        flags=("typed_research_package_assembler_blocked",),
    )


def _ready_preflight(request: AnalysisRequestSnapshot, selected_at: datetime):
    state = build_research_thesis_preflight_state(
        request,
        research_cutoff_at=selected_at,
        thesis_snapshot_ids=("a" * 64,),
        blockers=(),
    )
    return CurrentResearchThesisPreflightState(
        selected_at=selected_at,
        state=state,
    )


def test_later_package_blocker_wins_over_older_thesis_ready_pointer() -> None:
    request = _request()
    blocked_at = NOW + timedelta(minutes=2)
    run = _blocked_run(request, blocked_at)
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=blocked_at,
    )
    current = _ready_preflight(request, NOW + timedelta(minutes=1))

    rows = build_research_inbox(
        ledger,
        current_preflights={request.snapshot_id: current},
    )

    assert len(rows) == 1
    assert rows[0].state == "pre_orchestration_blocked"
    assert rows[0].blocker_count == 1
    assert rows[0].latest_run_completed_at == blocked_at


def test_later_thesis_ready_pointer_can_clear_an_older_preflight_blocker() -> None:
    request = _request()
    blocked_at = NOW + timedelta(minutes=1)
    run = _blocked_run(request, blocked_at)
    ledger = build_research_run_ledger(
        (request,),
        (run,),
        built_at=blocked_at,
    )
    current = _ready_preflight(request, NOW + timedelta(minutes=2))

    rows = build_research_inbox(
        ledger,
        current_preflights={request.snapshot_id: current},
    )

    assert len(rows) == 1
    assert rows[0].state == "pre_orchestration_ready"
    assert rows[0].blocker_count == 0
    assert rows[0].latest_run_completed_at == blocked_at
