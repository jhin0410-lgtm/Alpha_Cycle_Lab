from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import alpha_cycle.research_package_assembler_v2_1 as assembler
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


class _ComponentIndex:
    def latest_underwriting(self, *args, **kwargs):
        return None

    def latest_payoff(self, *args, **kwargs):
        return None

    def latest_decision_view(self, *args, **kwargs):
        return SimpleNamespace(
            snapshot_id="d" * 64,
            captured_at=NOW + timedelta(minutes=2),
            target_variable="net_income",
            target_date=date(2026, 12, 31),
            unit="KRW_million",
        )

    def latest_expectation_gap(self, *args, **kwargs):
        return SimpleNamespace(
            captured_at=NOW + timedelta(minutes=1),
            target_variable="net_income",
            target_date=date(2026, 12, 31),
            unit="KRW_million",
        )


def test_expectation_gap_cannot_precede_its_decision_view() -> None:
    blockers = []
    package = assembler._assemble_security_package(
        "000660",
        thesis=SimpleNamespace(snapshot_id="a" * 64),
        request=SimpleNamespace(
            evaluation_date=date(2026, 8, 23),
            requested_lane=UnderwritingLane.DEEP,
            horizon_trading_days=120,
        ),
        component_index=_ComponentIndex(),
        guardrail_evidence_id="b" * 64,
        blockers=blockers,
    )

    assert package is None
    assert any(
        blocker.code == "decision_gap_capture_order_mismatch"
        for blocker in blockers
    )
