from datetime import date

import pandas as pd
import pytest

from alpha_cycle.data.market import validate_ohlcv
from alpha_cycle.data.point_in_time import PointInTimeStore, validate_point_in_time


def test_ohlcv_schema_and_sorting(prices: pd.DataFrame) -> None:
    shuffled = prices.sample(frac=1, random_state=7)
    validated, report = validate_ohlcv(shuffled)
    assert validated[["date", "ticker"]].values.tolist() == sorted(
        validated[["date", "ticker"]].values.tolist()
    )
    assert report.tickers == 2
    assert report.periods_by_ticker["AAA"][2] == 6


def test_missing_column_and_invalid_range(prices: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_ohlcv(prices.drop(columns="volume"))
    broken = prices.copy()
    broken.loc[0, "high"] = 1
    with pytest.raises(ValueError, match="high"):
        validate_ohlcv(broken)


def test_duplicate_detection(prices: pd.DataFrame) -> None:
    duplicate = pd.concat([prices, prices.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate"):
        validate_ohlcv(duplicate)


def test_staleness(prices: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="stale"):
        validate_ohlcv(prices, as_of=date(2025, 1, 1), max_age_days=30)


def test_point_in_time_blocks_future_release() -> None:
    frame = pd.DataFrame(
        [
            {
                "observation_date": "2024-01-01",
                "available_date": "2024-02-01",
                "retrieved_at": "2024-02-02T00:00:00Z",
                "source": "fixture",
                "revision_id": "v1",
                "value": 10,
            }
        ]
    )
    store = PointInTimeStore(frame)
    assert store.as_of(date(2024, 1, 31)).empty
    assert store.as_of(date(2024, 2, 1))["value"].tolist() == [10]
    broken = frame.copy()
    broken["available_date"] = "2023-12-31"
    with pytest.raises(ValueError, match="cannot precede"):
        validate_point_in_time(broken)

