"""Explainable technical features derived from normalized candle history."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import sqrt

import numpy as np
import pandas as pd

from alpha_cycle.providers.tossinvest import Candle


@dataclass(frozen=True)
class TechnicalFeatures:
    symbol: str
    interval: str
    adjusted: bool
    observations: int
    last_price: float
    return_1: float | None
    return_5: float | None
    return_20: float | None
    sma_5: float | None
    sma_20: float | None
    price_to_sma_20: float | None
    realized_volatility_20: float | None
    volume_ratio_20: float | None
    drawdown_from_20_high: float | None
    rsi_14: float | None
    trend_efficiency_20: float | None
    trend_direction_20: float | None
    relative_strength_rank_20: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _period_return(series: pd.Series, periods: int) -> float | None:
    if len(series) <= periods:
        return None
    previous = float(series.iloc[-periods - 1])
    current = float(series.iloc[-1])
    if previous <= 0:
        return None
    return current / previous - 1.0


def _simple_average(series: pd.Series, window: int) -> float | None:
    if len(series) < window:
        return None
    return float(series.iloc[-window:].mean())


def _rsi(series: pd.Series, window: int = 14) -> float | None:
    if len(series) <= window:
        return None
    changes = series.diff().dropna().iloc[-window:]
    gains = changes.clip(lower=0).mean()
    losses = -changes.clip(upper=0).mean()
    if float(losses) == 0.0:
        return 100.0 if float(gains) > 0.0 else 50.0
    relative_strength = float(gains / losses)
    return 100.0 - 100.0 / (1.0 + relative_strength)


def _annualization_factor(interval: str) -> float:
    if interval == "1d":
        return sqrt(252.0)
    if interval == "1m":
        return sqrt(252.0 * 390.0)
    raise ValueError("interval must be 1m or 1d")


def calculate_technical_features(candles: tuple[Candle, ...]) -> TechnicalFeatures:
    """Calculate deterministic, explainable features without directional claims."""
    if not candles:
        raise ValueError("At least one candle is required")
    ordered = tuple(sorted(candles, key=lambda item: item.timestamp))
    symbol = ordered[0].symbol
    interval = ordered[0].interval
    adjusted = ordered[0].adjusted
    if any(item.symbol != symbol for item in ordered):
        raise ValueError("All candles must have the same symbol")
    if any(item.interval != interval for item in ordered):
        raise ValueError("All candles must have the same interval")
    if any(item.adjusted != adjusted for item in ordered):
        raise ValueError("All candles must use the same adjustment basis")
    timestamps = [item.timestamp for item in ordered]
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("Candle timestamps must be unique")

    close = pd.Series([float(item.close_price) for item in ordered], dtype="float64")
    volume = pd.Series([float(item.volume) for item in ordered], dtype="float64")
    last_price = float(close.iloc[-1])
    sma_5 = _simple_average(close, 5)
    sma_20 = _simple_average(close, 20)
    returns = close.pct_change(fill_method=None).dropna()

    realized_volatility_20: float | None = None
    if len(returns) >= 20:
        realized_volatility_20 = float(returns.iloc[-20:].std(ddof=1)) * _annualization_factor(
            interval
        )

    volume_ratio_20: float | None = None
    if len(volume) >= 21:
        trailing_average = float(volume.iloc[-21:-1].mean())
        if trailing_average > 0:
            volume_ratio_20 = float(volume.iloc[-1]) / trailing_average

    drawdown_from_20_high: float | None = None
    if len(close) >= 20:
        trailing_high = float(close.iloc[-20:].max())
        if trailing_high > 0:
            drawdown_from_20_high = last_price / trailing_high - 1.0

    trend_efficiency_20: float | None = None
    trend_direction_20: float | None = None
    if len(close) >= 21:
        window = close.iloc[-21:]
        net_change = float(window.iloc[-1] - window.iloc[0])
        path_change = float(window.diff().abs().sum())
        trend_efficiency_20 = abs(net_change) / path_change if path_change > 0 else 0.0
        trend_direction_20 = float(np.sign(net_change))

    return TechnicalFeatures(
        symbol=symbol,
        interval=interval,
        adjusted=adjusted,
        observations=len(ordered),
        last_price=last_price,
        return_1=_period_return(close, 1),
        return_5=_period_return(close, 5),
        return_20=_period_return(close, 20),
        sma_5=sma_5,
        sma_20=sma_20,
        price_to_sma_20=(last_price / sma_20 - 1.0 if sma_20 is not None and sma_20 > 0 else None),
        realized_volatility_20=realized_volatility_20,
        volume_ratio_20=volume_ratio_20,
        drawdown_from_20_high=drawdown_from_20_high,
        rsi_14=_rsi(close),
        trend_efficiency_20=trend_efficiency_20,
        trend_direction_20=trend_direction_20,
    )


def add_relative_strength_ranks(
    features: tuple[TechnicalFeatures, ...],
) -> tuple[TechnicalFeatures, ...]:
    """Rank 20-period returns cross-sectionally from 0 to 1 when available."""
    available = [item for item in features if item.return_20 is not None]
    if len(available) < 2:
        return features
    series = pd.Series(
        {item.symbol: float(item.return_20) for item in available},
        dtype="float64",
    )
    ranks = series.rank(method="average", pct=True)
    return tuple(
        replace(
            item,
            relative_strength_rank_20=(
                float(ranks[item.symbol]) if item.symbol in ranks.index else None
            ),
        )
        for item in features
    )
