from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot
from alpha_cycle.intelligence.valuation_latest_equity_resilient import (
    apply_latest_observable_equity_pb,
)


def _snapshot(metrics: pd.DataFrame, history: pd.DataFrame) -> ValuationEvidenceSnapshot:
    return ValuationEvidenceSnapshot(
        captured_at=datetime(2026, 8, 14, 4, tzinfo=UTC),
        evaluation_date=date(2026, 8, 14),
        research_snapshot_id="a" * 64,
        market_snapshot_id="b" * 64,
        history_years=3,
        shares=pd.DataFrame(),
        security_values=pd.DataFrame(),
        financial_history=history,
        valuation_metrics=metrics,
        raw_valuation={},
        warnings=(),
    )


def test_pb_uses_latest_observable_non_derived_equity() -> None:
    metrics = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "market_cap_complete": True,
                "market_cap": 1000.0,
                "pe": 10.0,
                "pb": 10.0,
                "ps": 2.0,
                "fcf_yield": 0.05,
                "valuation_score": None,
                "valuation_status": "insufficient_peer_universe",
            }
        ]
    )
    history = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "business_year": 2025,
                "period_label": "FY",
                "period_order": 5,
                "period_end": "2025-12-31",
                "available_date": "2026-03-17",
                "equity": 100.0,
                "derived": False,
            },
            {
                "ticker": "000660",
                "business_year": 2026,
                "period_label": "Q1",
                "period_order": 1,
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "equity": 200.0,
                "derived": False,
            },
            {
                "ticker": "000660",
                "business_year": 2026,
                "period_label": "Q2",
                "period_order": 2,
                "period_end": "2026-06-30",
                "available_date": "2026-08-20",
                "equity": 400.0,
                "derived": False,
            },
            {
                "ticker": "000660",
                "business_year": 2026,
                "period_label": "Q1_DERIVED",
                "period_order": 9,
                "period_end": "2026-03-31",
                "available_date": "2026-06-01",
                "equity": 300.0,
                "derived": True,
            },
        ]
    )

    result = apply_latest_observable_equity_pb(_snapshot(metrics, history))
    row = result.valuation_metrics.iloc[0]

    assert float(row["pb"]) == pytest.approx(5.0)
    assert float(row["book_equity"]) == pytest.approx(200.0)
    assert row["book_equity_reference_period"] == "Q1"
    assert row["pb_equity_basis"] == "latest_observable_non_derived_equity"
    assert pd.isna(row["valuation_score"])
    assert row["valuation_status"] == "insufficient_peer_universe"


def test_peer_scores_are_recomputed_after_pb_rebase() -> None:
    tickers = [f"{index:06d}" for index in range(1, 6)]
    metrics = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "market_cap_complete": True,
                "market_cap": 1000.0,
                "pe": 10.0,
                "pb": 100.0 - index,
                "ps": 2.0,
                "fcf_yield": 0.05,
                "valuation_score": 1.0,
                "valuation_status": "complete_peer_relative_scored",
            }
            for index, ticker in enumerate(tickers, start=1)
        ]
    )
    history = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "business_year": 2026,
                "period_label": "Q1",
                "period_order": 1,
                "period_end": "2026-03-31",
                "available_date": "2026-05-15",
                "equity": 100.0 * index,
                "derived": False,
            }
            for index, ticker in enumerate(tickers, start=1)
        ]
    )

    result = apply_latest_observable_equity_pb(_snapshot(metrics, history))
    scored = result.valuation_metrics.sort_values("ticker", kind="stable")

    assert scored["valuation_score"].notna().all()
    assert scored["valuation_status"].eq("complete_peer_relative_scored").all()
    assert scored["valuation_peer_count"].eq(5).all()
    assert scored["valuation_peer_minimum"].eq(5).all()
    assert float(scored.iloc[0]["pb"]) == pytest.approx(10.0)
    assert float(scored.iloc[-1]["pb"]) == pytest.approx(2.0)
    assert float(scored.iloc[-1]["valuation_score"]) > float(
        scored.iloc[0]["valuation_score"]
    )
