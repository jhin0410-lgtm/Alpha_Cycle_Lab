"""Deterministic test data; it is not representative investment data."""

from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def prices() -> pd.DataFrame:
    """Two tickers over six synthetic business dates."""
    rows = []
    for day in range(1, 7):
        for ticker, base, step in (("AAA", 100, 2), ("BBB", 80, -1)):
            close = base + step * day
            rows.append(
                {
                    "date": f"2024-01-{day:02d}",
                    "ticker": ticker,
                    "open": close - 1,
                    "high": close + 2,
                    "low": close - 2,
                    "close": close,
                    "volume": 1_000_000,
                    "trading_value": 1_000_000_000,
                }
            )
    return pd.DataFrame(rows)

