"""Regression test for direct decision CLI routing."""

from __future__ import annotations

from alpha_cycle import decision_cli


def test_direct_decision_cli_uses_evidence_calibrated_builder() -> None:
    assert (
        decision_cli.build_investment_decision_snapshot.__module__
        == "alpha_cycle.intelligence.decision_evidence_calibrated"
    )
