from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_package_assembler_v2_1 import assemble_and_run_research_package
from alpha_cycle.research_preflight_state_v2_1 import (
    build_research_thesis_preflight_state,
    persist_research_thesis_preflight_state,
    publish_current_research_thesis_preflight_state,
)
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def test_package_assembly_rejects_preflight_selected_after_processing_time(
    tmp_path: Path,
) -> None:
    receipt = record_analysis_request(
        request_id="future-preflight-pointer",
        requested_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        evaluation_date=date(2026, 8, 23),
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Do not consume future operational preflight state.",
        artifact_root=tmp_path,
    )
    state = build_research_thesis_preflight_state(
        receipt.request,
        research_cutoff_at=NOW,
        thesis_snapshot_ids=("a" * 64, "b" * 64),
        blockers=(),
    )
    persist_research_thesis_preflight_state(state, output_root=tmp_path)
    publish_current_research_thesis_preflight_state(
        state,
        selected_at=NOW + timedelta(minutes=10),
        output_root=tmp_path,
    )

    with pytest.raises(ValueError, match="selected_at cannot be after processing time"):
        assemble_and_run_research_package(
            request_id="future-preflight-pointer",
            round_id="round-future-preflight",
            run_id="run-future-preflight",
            processed_at=NOW + timedelta(minutes=5),
            artifact_root=tmp_path,
        )
