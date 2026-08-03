"""Regression tests for minimum comparable-company valuation coverage."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot
from alpha_cycle.intelligence.valuation_resilient import (
    apply_minimum_peer_universe_guard,
)


def _snapshot(company_count: int) -> ValuationEvidenceSnapshot:
    metrics = pd.DataFrame(
        [
            {
                "ticker": str(index + 1).zfill(6),
                "market_cap_complete": True,
                "pe": 10.0 + index,
                "pb": 1.0 + index / 10.0,
                "ps": 2.0 + index / 10.0,
                "fcf_yield": 0.05 + index / 100.0,
                "valuation_score": 3.0 + index / 10.0,
                "valuation_status": "complete_peer_relative_scored",
            }
            for index in range(company_count)
        ]
    )
    return ValuationEvidenceSnapshot(
        captured_at=datetime(2026, 8, 3, tzinfo=UTC),
        evaluation_date=date(2026, 8, 3),
        research_snapshot_id="a" * 64,
        market_snapshot_id="b" * 64,
        history_years=3,
        shares=pd.DataFrame(),
        security_values=pd.DataFrame(),
        financial_history=pd.DataFrame(),
        valuation_metrics=metrics,
        raw_valuation={},
        warnings=(
            "Valuation scores are peer-relative percentile ranks shrunk toward neutral; "
            "they are not absolute fair-value estimates or target prices.",
        ),
    )


def test_two_company_relative_scores_are_disabled() -> None:
    guarded = apply_minimum_peer_universe_guard(_snapshot(2))

    assert guarded.valuation_metrics["valuation_score"].isna().all()
    assert set(guarded.valuation_metrics["valuation_status"]) == {
        "insufficient_peer_universe"
    }
    assert set(guarded.valuation_metrics["valuation_peer_count"]) == {2}
    assert set(guarded.valuation_metrics["valuation_peer_minimum"]) == {5}
    assert any("contains 2 companies" in warning for warning in guarded.warnings)
    assert not any(
        "Valuation scores are peer-relative percentile ranks" in warning
        for warning in guarded.warnings
    )


def test_five_company_relative_scores_remain_available() -> None:
    guarded = apply_minimum_peer_universe_guard(_snapshot(5))

    assert guarded.valuation_metrics["valuation_score"].notna().all()
    assert set(guarded.valuation_metrics["valuation_status"]) == {
        "complete_peer_relative_scored"
    }
    assert set(guarded.valuation_metrics["valuation_peer_count"]) == {5}
    assert set(guarded.valuation_metrics["valuation_peer_minimum"]) == {5}
