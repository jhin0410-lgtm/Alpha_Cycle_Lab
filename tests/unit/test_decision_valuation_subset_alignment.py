"""Regression tests for decision universes with partial valuation coverage."""

from __future__ import annotations

import pandas as pd
import pytest

from alpha_cycle import intelligence
from alpha_cycle.intelligence.decision_resilient import (
    align_valuation_metrics_to_decisions,
)


def test_intelligence_export_uses_forward_estimate_calibrated_decision_builder() -> None:
    assert (
        intelligence.build_investment_decision_snapshot.__module__
        == "alpha_cycle.intelligence.decision_forward_estimate_calibrated"
    )


def test_missing_valuation_company_is_padded_explicitly() -> None:
    metrics = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "market_cap_complete": True,
                "market_cap": 1000.0,
                "valuation_score": 3.5,
                "valuation_status": "complete_peer_relative_scored",
            }
        ]
    )

    aligned, missing = align_valuation_metrics_to_decisions(
        metrics,
        {"000660", "005930"},
    )

    assert missing == ("005930",)
    assert set(aligned["ticker"].astype(str)) == {"000660", "005930"}
    samsung = aligned.loc[aligned["ticker"].astype(str).eq("005930")].iloc[0]
    assert samsung["valuation_status"] == "valuation_not_available"
    assert not bool(samsung["market_cap_complete"])
    assert not bool(samsung["share_count_complete"])
    assert pd.isna(samsung["market_cap"])
    assert pd.isna(samsung["valuation_score"])


def test_unrelated_valuation_company_still_fails_closed() -> None:
    metrics = pd.DataFrame(
        [
            {"ticker": "000660", "valuation_status": "complete_unscored"},
            {"ticker": "035420", "valuation_status": "complete_unscored"},
        ]
    )

    with pytest.raises(ValueError, match="outside the decision universe"):
        align_valuation_metrics_to_decisions(
            metrics,
            {"000660", "005930"},
        )
