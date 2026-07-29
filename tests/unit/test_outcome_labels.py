"""Tests for ex-post decision outcome labels."""

from __future__ import annotations

import pandas as pd
import pytest

from alpha_cycle.intelligence.outcomes import label_decision_outcomes


def test_labels_forward_return_upside_and_drawdown() -> None:
    records = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "evaluation_date": "2026-07-01",
                "reference_price": 100,
                "decision_state": "positive_setup",
                "action_bias": "fundamental_positive_timing_confirmed",
                "composite_score": 4.1,
                "score_coverage": 0.75,
            }
        ]
    )
    candles = pd.DataFrame(
        [
            {
                "symbol": "005930",
                "timestamp": f"2026-07-{day:02d}T00:00:00Z",
                "high": 100 + day + 1,
                "low": 100 + day - 2,
                "close": 100 + day,
            }
            for day in range(1, 8)
        ]
    )
    labels = label_decision_outcomes(records, candles, horizons=(1, 5))
    one_day = labels.loc[labels["horizon_trading_days"] == 1].iloc[0]
    five_day = labels.loc[labels["horizon_trading_days"] == 5].iloc[0]
    assert bool(one_day["resolved"]) is True
    assert one_day["forward_return"] == pytest.approx(0.02)
    assert five_day["forward_return"] == pytest.approx(0.06)
    assert five_day["max_upside"] == pytest.approx(0.07)
    assert five_day["max_drawdown"] == pytest.approx(0.0)


def test_unresolved_horizon_is_preserved_without_fake_return() -> None:
    records = pd.DataFrame(
        [{"ticker": "005930", "evaluation_date": "2026-07-01", "reference_price": 100}]
    )
    candles = pd.DataFrame(
        [
            {
                "symbol": "005930",
                "timestamp": "2026-07-02T00:00:00Z",
                "high": 102,
                "low": 99,
                "close": 101,
            }
        ]
    )
    labels = label_decision_outcomes(records, candles, horizons=(5,))
    assert bool(labels.iloc[0]["resolved"]) is False
    assert pd.isna(labels.iloc[0]["forward_return"])
