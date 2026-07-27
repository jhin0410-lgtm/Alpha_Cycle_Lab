"""Defensive performance metrics for research simulations."""

from __future__ import annotations

import math
import statistics
from typing import Any

import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult
from alpha_cycle.portfolio.portfolio import Portfolio


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def calculate_metrics(
    result: BacktestResult,
    portfolio: Portfolio,
    *,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0,
    benchmark_returns: pd.Series | None = None,
) -> dict[str, Any]:
    """Calculate stable metrics, returning zero for undefined no-observation ratios."""
    if not result.equity_curve:
        return {
            key: 0.0
            for key in (
                "cumulative_return",
                "annualized_return",
                "annualized_volatility",
                "maximum_drawdown",
                "sharpe_ratio",
                "sortino_ratio",
                "calmar_ratio",
                "win_rate",
                "profit_factor",
                "turnover",
                "total_commission",
                "total_tax",
                "total_slippage",
                "benchmark_excess_return",
            )
        }
    equity = [float(str(row["equity"])) for row in result.equity_curve]
    returns = [
        _safe_ratio(current, prior) - 1.0
        for prior, current in zip(equity, equity[1:], strict=False)
        if prior != 0
    ]
    cumulative = _safe_ratio(equity[-1], equity[0]) - 1.0
    years = max((len(equity) - 1) / periods_per_year, 0.0)
    annualized_return = (1.0 + cumulative) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    volatility = (
        statistics.stdev(returns) * math.sqrt(periods_per_year)
        if len(returns) > 1
        else 0.0
    )
    peak = equity[0]
    maximum_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        maximum_drawdown = max(maximum_drawdown, 1.0 - _safe_ratio(value, peak))
    periodic_rf = risk_free_rate / periods_per_year
    excess = [value - periodic_rf for value in returns]
    sharpe = (
        statistics.mean(excess) / statistics.stdev(excess) * math.sqrt(periods_per_year)
        if len(excess) > 1 and statistics.stdev(excess) != 0
        else 0.0
    )
    downside = [value for value in excess if value < 0]
    downside_deviation = (
        math.sqrt(statistics.mean(value**2 for value in downside)) if downside else 0.0
    )
    excess_mean = statistics.mean(excess) if excess else 0.0
    sortino = _safe_ratio(excess_mean * math.sqrt(periods_per_year), downside_deviation)
    calmar = _safe_ratio(annualized_return, maximum_drawdown)
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    win_rate = _safe_ratio(float(len(wins)), float(len(returns)))
    profit_factor = _safe_ratio(sum(wins), abs(sum(losses)))
    benchmark_cumulative = (
        math.prod(1.0 + float(value) for value in benchmark_returns.fillna(0.0).tolist())
        - 1.0
        if benchmark_returns is not None and not benchmark_returns.empty
        else 0.0
    )
    return {
        "cumulative_return": cumulative,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "maximum_drawdown": maximum_drawdown,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "turnover": result.turnover,
        "total_commission": float(portfolio.total_commission),
        "total_tax": float(portfolio.total_tax),
        "total_slippage": float(portfolio.total_slippage),
        "benchmark_excess_return": cumulative - benchmark_cumulative,
    }
