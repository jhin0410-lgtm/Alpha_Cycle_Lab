from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from alpha_cycle.backtest.engine import BacktestConfig, BacktestEngine, ExecutionPrice
from alpha_cycle.brokers.simulated import SimulatedBroker
from alpha_cycle.data.market import MarketDataFeed
from alpha_cycle.domain.models import TargetPosition
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.risk.manager import RiskConfig, RiskManager
from alpha_cycle.strategies.examples import BuyAndHoldStrategy


def run_engine(prices: pd.DataFrame, strategy: object) -> tuple[object, Portfolio]:
    portfolio = Portfolio(Decimal("10000"))
    engine = BacktestEngine(
        MarketDataFeed(prices),
        strategy,  # type: ignore[arg-type]
        portfolio,
        SimulatedBroker(),
        RiskManager(
            RiskConfig(
                max_single_position=1,
                max_gross_exposure=1,
                max_daily_turnover=1,
                max_order_pct_of_trading_value=1,
                max_daily_loss=1,
                max_portfolio_drawdown=1,
            )
        ),
        BacktestConfig(initial_cash=Decimal("10000")),
    )
    return engine.run(), portfolio


def test_buy_hold_uses_next_open(prices: pd.DataFrame) -> None:
    result, portfolio = run_engine(prices, BuyAndHoldStrategy(["AAA"]))
    assert result.fills[0].timestamp.date() == date(2024, 1, 2)
    next_bar = prices.query("date == '2024-01-02' and ticker == 'AAA'").iloc[0]
    expected_open = Decimal(str(next_bar["open"]))
    assert result.fills[0].price == expected_open
    assert portfolio.positions["AAA"].quantity > 0


class TwoStageStrategy:
    def __init__(self) -> None:
        self.calls = 0

    def generate_targets(
        self, event_date: date, history: pd.DataFrame
    ) -> list[TargetPosition] | None:
        del event_date
        self.calls += 1
        if self.calls == 1:
            return [TargetPosition("AAA", 0.5), TargetPosition("BBB", 0.5)]
        if self.calls == 4:
            return [TargetPosition("AAA", 0.2), TargetPosition("BBB", 0.8)]
        return None


def test_multi_asset_rebalancing_and_determinism(prices: pd.DataFrame) -> None:
    first, _ = run_engine(prices, TwoStageStrategy())
    second, _ = run_engine(prices, TwoStageStrategy())
    assert len(first.fills) >= 2
    assert first.orders == second.orders
    assert first.equity_curve == second.equity_curve


class AuditStrategy:
    def __init__(self) -> None:
        self.observed: list[tuple[date, date]] = []

    def generate_targets(
        self, event_date: date, history: pd.DataFrame
    ) -> list[TargetPosition] | None:
        self.observed.append((event_date, history["date"].max()))
        return None


def test_engine_never_exposes_future_rows(prices: pd.DataFrame) -> None:
    strategy = AuditStrategy()
    result, _ = run_engine(prices, strategy)
    assert result.fills == []
    assert all(event_date == maximum for event_date, maximum in strategy.observed)


def test_same_close_is_explicit(prices: pd.DataFrame) -> None:
    portfolio = Portfolio(Decimal("10000"))
    engine = BacktestEngine(
        MarketDataFeed(prices),
        BuyAndHoldStrategy(["AAA"]),
        portfolio,
        SimulatedBroker(),
        RiskManager(
            RiskConfig(
                max_single_position=1,
                max_gross_exposure=1,
                max_daily_turnover=1,
                max_order_pct_of_trading_value=1,
                max_daily_loss=1,
                max_portfolio_drawdown=1,
            )
        ),
        BacktestConfig(
            initial_cash=Decimal("10000"), execution_price=ExecutionPrice.SAME_CLOSE
        ),
    )
    result = engine.run()
    assert result.fills[0].timestamp.date() == date(2024, 1, 1)
