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


def test_ready_preflight_cannot_hide_older_outstanding_package_blocker() -> None:
    request = AnalysisRequestSnapshot(
        request_id="outstanding-package-blocker",
        requested_at=NOW,
        evaluation_date=date(2026, 8, 23),
        horizon_trading_days=120,
        security_ids=("000660",),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Retain downstream package blockers across thesis preflight transitions.",
        guardrail_evidence_id=GUARDRAIL,
    )
    package_at = NOW + timedelta(minutes=1)
    package_run = build_pre_orchestration_blocked_run(
        request,
        run_id="package-blocked",
        started_at=package_at,
        completed_at=package_at,
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
    thesis_at = NOW + timedelta(minutes=2)
    thesis_run = build_pre_orchestration_blocked_run(
        request,
        run_id="thesis-blocked",
        started_at=thesis_at,
        completed_at=thesis_at,
        blockers=(
            ResearchRoundBlocker(
                component="investment_thesis",
                code="thesis_missing",
                detail="thesis missing",
                security_id="000660",
            ),
        ),
        flags=("typed_thesis_preflight_blocked",),
    )
    ledger = build_research_run_ledger(
        (request,),
        (package_run, thesis_run),
        built_at=thesis_at,
    )
    ready_at = NOW + timedelta(minutes=3)
    ready = CurrentResearchThesisPreflightState(
        selected_at=ready_at,
        state=build_research_thesis_preflight_state(
            request,
            research_cutoff_at=ready_at,
            thesis_snapshot_ids=("a" * 64,),
            blockers=(),
        ),
    )

    rows = build_research_inbox(
        ledger,
        current_preflights={request.snapshot_id: ready},
    )

    assert len(rows) == 1
    assert rows[0].state == "pre_orchestration_blocked"
    assert rows[0].blocker_count == 1
    assert rows[0].latest_run_completed_at == package_at
