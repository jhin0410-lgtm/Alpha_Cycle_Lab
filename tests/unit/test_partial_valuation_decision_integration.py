"""Regression tests for partial valuation coverage in decision integration."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from alpha_cycle.intelligence.decision_scoring import DecisionPolicy
from alpha_cycle.intelligence.valuation import (
    ValuationEvidenceSnapshot,
    apply_valuation_to_scorecards,
)
from alpha_cycle.intelligence.valuation_resilient import (
    apply_unresolved_share_count_guard,
)


def _snapshot_with_missing_samsung_metric() -> ValuationEvidenceSnapshot:
    shares = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "security_name": "기타",
                "security_class": "other",
                "issued_shares": 0,
                "period_end": date(2026, 3, 31),
                "available_date": date(2026, 5, 15),
                "normalization_warning": (
                    "기타: schema value set to zero via "
                    "unresolved_missing_economic_share_count"
                ),
            },
            {
                "ticker": "000660",
                "security_name": "보통주",
                "security_class": "common",
                "issued_shares": 100,
                "period_end": date(2026, 3, 31),
                "available_date": date(2026, 5, 15),
                "normalization_warning": None,
            },
        ]
    )
    security_values = pd.DataFrame(
        [
            {
                **shares.iloc[1].to_dict(),
                "symbol": "000660",
                "mapping_source": "explicit",
                "price": 200.0,
                "price_timestamp": datetime(2026, 8, 1, tzinfo=UTC),
                "security_market_value": 20000.0,
                "priced": True,
            }
        ]
    )
    history = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "business_year": "2025",
                "period_label": "FY",
                "period_end": date(2025, 12, 31),
                "revenue": 300000.0,
                "net_income": 30000.0,
                "equity": 200000.0,
                "free_cash_flow_ytd": 25000.0,
            },
            {
                "ticker": "000660",
                "business_year": "2025",
                "period_label": "FY",
                "period_end": date(2025, 12, 31),
                "revenue": 100000.0,
                "net_income": 10000.0,
                "equity": 50000.0,
                "free_cash_flow_ytd": 8000.0,
            },
        ]
    )
    metrics = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "share_period_end": date(2026, 3, 31),
                "share_available_date": date(2026, 5, 15),
                "priced_security_classes": 1,
                "required_security_classes": 1,
                "market_cap_complete": True,
                "missing_security_names": "[]",
                "market_cap_proxy": 20000.0,
                "market_cap": 20000.0,
                "annual_reference_year": 2025,
                "annual_revenue": 100000.0,
                "annual_net_income": 10000.0,
                "annual_equity": 50000.0,
                "annual_free_cash_flow": 8000.0,
                "pe": 2.0,
                "pb": 0.4,
                "ps": 0.2,
                "fcf_yield": 0.4,
                "earnings_yield": 0.5,
                "valuation_score": None,
                "valuation_status": "complete_unscored",
            }
        ]
    )
    return ValuationEvidenceSnapshot(
        captured_at=datetime(2026, 8, 1, tzinfo=UTC),
        evaluation_date=date(2026, 8, 1),
        research_snapshot_id="a" * 64,
        market_snapshot_id="b" * 64,
        history_years=3,
        shares=shares,
        security_values=security_values,
        financial_history=history,
        valuation_metrics=metrics,
        raw_valuation={},
    )


def test_guard_preserves_explicit_incomplete_metric_row() -> None:
    guarded = apply_unresolved_share_count_guard(
        _snapshot_with_missing_samsung_metric()
    )

    assert set(guarded.valuation_metrics["ticker"].astype(str)) == {
        "000660",
        "005930",
    }
    samsung = guarded.valuation_metrics.loc[
        guarded.valuation_metrics["ticker"].astype(str).eq("005930")
    ].iloc[0]
    assert samsung["valuation_status"] == "incomplete_share_count"
    assert not bool(samsung["market_cap_complete"])
    assert not bool(samsung["share_count_complete"])
    assert pd.isna(samsung["market_cap"])
    assert pd.isna(samsung["valuation_score"])
    assert samsung["annual_reference_year"] == 2025
    assert samsung["annual_revenue"] == 300000.0


def test_decision_scorecards_continue_with_incomplete_valuation() -> None:
    guarded = apply_unresolved_share_count_guard(
        _snapshot_with_missing_samsung_metric()
    )
    scorecards = pd.DataFrame(
        [
            {
                "ticker": ticker,
                "earnings_momentum_score": 4.0,
                "financial_quality_score": 4.0,
                "catalyst_score": 3.0,
                "market_timing_score": 3.0,
                "macro_fit_score": 3.0,
                "valuation_score": None,
                "positive_evidence": "[]",
                "opposing_evidence": "[]",
            }
            for ticker in ("000660", "005930")
        ]
    )

    integrated = apply_valuation_to_scorecards(
        scorecards,
        guarded.valuation_metrics,
        DecisionPolicy(),
    )

    assert set(integrated["ticker"].astype(str)) == {"000660", "005930"}
    samsung = integrated.loc[integrated["ticker"].astype(str).eq("005930")].iloc[0]
    assert samsung["valuation_status"] == "incomplete_share_count"
    assert pd.isna(samsung["valuation_score"])
    assert samsung["decision_state"] != "insufficient_data"
    assert "incomplete_share_count" in str(samsung["opposing_evidence"])
