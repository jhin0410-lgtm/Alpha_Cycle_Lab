from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def test_request_intake_persists_canonical_security_ids(tmp_path: Path) -> None:
    receipt = record_analysis_request(
        request_id="canonical-security-ids",
        requested_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        evaluation_date=date(2026, 8, 23),
        horizon_trading_days=120,
        security_ids=(" 000660 ", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Canonicalize security IDs at the immutable intake boundary.",
        artifact_root=tmp_path,
    )

    assert receipt.request.security_ids == ("000660", "005930")
    assert receipt.ledger.requests[-1].security_ids == ("000660", "005930")


def test_request_intake_rejects_duplicates_after_canonicalization(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="duplicates"):
        record_analysis_request(
            request_id="duplicate-security-ids",
            requested_at=NOW,
            recorded_at=NOW + timedelta(seconds=1),
            evaluation_date=date(2026, 8, 23),
            horizon_trading_days=120,
            security_ids=("000660", " 000660 "),
            mode=ResearchRoundMode.PROSPECTIVE,
            requested_lane=UnderwritingLane.DEEP,
            request_text="Reject duplicate IDs after canonicalization.",
            artifact_root=tmp_path,
        )
