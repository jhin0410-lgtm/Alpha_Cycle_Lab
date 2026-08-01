"""Regression tests for market snapshots containing auxiliary equity classes."""

from __future__ import annotations

import pandas as pd
import pytest

from alpha_cycle.intelligence.decision import _filter_market_inputs


def _candles() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": symbol, "timestamp": "2026-08-01", "close": 100, "volume": 10}
            for symbol in ("005930", "005935", "000660", "069500")
        ]
    )


def _technical() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"symbol": symbol, "rsi_14": 50}
            for symbol in ("005930", "005935", "000660", "069500")
        ]
    )


def test_auxiliary_preferred_share_is_excluded_from_decision_inputs() -> None:
    candles, technical, extras = _filter_market_inputs(
        _candles(),
        _technical(),
        {"005930", "000660"},
        benchmark=None,
    )
    assert set(candles["symbol"]) == {"005930", "000660"}
    assert set(technical["symbol"]) == {"005930", "000660"}
    assert extras == ("005935", "069500")


def test_explicit_benchmark_is_kept_but_preferred_share_is_not() -> None:
    candles, technical, extras = _filter_market_inputs(
        _candles(),
        _technical(),
        {"005930", "000660"},
        benchmark="069500",
    )
    assert set(candles["symbol"]) == {"005930", "000660", "069500"}
    assert set(technical["symbol"]) == {"005930", "000660", "069500"}
    assert extras == ("005935",)


def test_missing_decision_symbol_fails_closed() -> None:
    candles = _candles().loc[lambda frame: frame["symbol"] != "000660"]
    with pytest.raises(ValueError, match="missing required decision symbols: 000660"):
        _filter_market_inputs(
            candles,
            _technical(),
            {"005930", "000660"},
            benchmark=None,
        )
