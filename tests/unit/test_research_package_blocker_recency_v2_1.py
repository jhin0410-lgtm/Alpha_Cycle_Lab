from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import alpha_cycle.research_package_assembler_v2_1 as assembler
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def test_same_blocker_is_republished_after_newer_preflight_state(tmp_path: Path) -> None:
    receipt = record_analysis_request(
        request_id="blocker-recency",
        requested_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        evaluation_date=date(2026, 8, 23),
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Preserve operational blocker recency while deduplicating history.",
        artifact_root=tmp_path,
    )
    blockers = (
        ResearchRoundBlocker(
            component="research_package",
            code="payoff_surface_missing_or_incompatible",
            detail="payoff surface missing or incompatible",
            security_id="000660",
        ),
    )

    first_ledger, _, _, first_changed = assembler._record_package_blockers(
        request=receipt.request,
        run_id="blocker-first",
        processed_at=NOW + timedelta(minutes=1),
        preflight_selected_at=NOW + timedelta(seconds=30),
        blockers=blockers,
        ledger=receipt.ledger,
        root=tmp_path,
    )
    assert first_changed is True
    assert len(first_ledger.runs) == 1

    second_ledger, _, _, second_changed = assembler._record_package_blockers(
        request=receipt.request,
        run_id="blocker-after-new-preflight",
        processed_at=NOW + timedelta(minutes=3),
        preflight_selected_at=NOW + timedelta(minutes=2),
        blockers=blockers,
        ledger=first_ledger,
        root=tmp_path,
    )
    assert second_changed is True
    assert len(second_ledger.runs) == 2
    assert second_ledger.runs[-1].completed_at == NOW + timedelta(minutes=3)

    third_ledger, run_path, ledger_path, third_changed = (
        assembler._record_package_blockers(
            request=receipt.request,
            run_id="blocker-idempotent",
            processed_at=NOW + timedelta(minutes=4),
            preflight_selected_at=NOW + timedelta(minutes=2),
            blockers=blockers,
            ledger=second_ledger,
            root=tmp_path,
        )
    )
    assert third_changed is False
    assert third_ledger == second_ledger
    assert run_path is None
    assert ledger_path is None
