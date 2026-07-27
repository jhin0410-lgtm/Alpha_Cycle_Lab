from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from alpha_cycle.backtest.engine import BacktestConfig, BacktestEngine, ExecutionPrice
from alpha_cycle.brokers.simulated import SimulatedBroker
from alpha_cycle.calendar.rebalance import MonthlyRebalanceSchedule, WeeklyRebalanceSchedule
from alpha_cycle.calendar.sessions import ExplicitTradingCalendar
from alpha_cycle.data.market import MarketDataFeed
from alpha_cycle.domain.models import TargetPosition
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.risk.manager import RiskConfig, RiskManager
from alpha_cycle.strategies.examples import BuyAndHoldStrategy


def make_calendar() -> ExplicitTradingCalendar:
    return ExplicitTradingCalendar(
        name="XKRX_TEST",
        sessions=[
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 5),
            date(2024, 1, 8),
        ],
        timezone=ZoneInfo("Asia/Seoul"),
        open_time=time(9, 0),
        close_time=time(15, 30),
    )


def test_calendar_detects_sessions_and_timezones() -> None:
    calendar = make_calendar()

    assert calendar.is_session(date(2024, 1, 3))
    assert not calendar.is_session(date(2024, 1, 6))
    assert calendar.next_session(date(2024, 1, 3)) == date(2024, 1, 4)
    assert calendar.previous_session(date(2024, 1, 4)) == date(2024, 1, 3)
    assert calendar.sessions_between(date(2024, 1, 3), date(2024, 1, 5)) == [
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]

    open_dt = calendar.session_open(date(2024, 1, 3))
    close_dt = calendar.session_close(date(2024, 1, 3))
    assert open_dt.tzinfo is not None
    assert close_dt.tzinfo is not None
    assert open_dt == datetime(2024, 1, 3, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    assert close_dt == datetime(2024, 1, 3, 15, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    assert calendar.session_label(open_dt) == date(2024, 1, 3)

    with pytest.raises(ValueError):
        calendar.session_label(datetime(2024, 1, 3, 9, 0))


def test_feed_rejects_non_trading_session_values() -> None:
    calendar = make_calendar()
    rows = [
        {
            "date": "2024-01-02",
            "ticker": "AAA",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000,
            "trading_value": 1_000_000,
        },
        {
            "date": "2024-01-06",
            "ticker": "AAA",
            "open": 101.0,
            "high": 102.0,
            "low": 100.0,
            "close": 101.0,
            "volume": 1_000,
            "trading_value": 1_000_000,
        },
    ]
    with pytest.raises(ValueError, match="non-trading"):
        MarketDataFeed(pd.DataFrame(rows), calendar=calendar)


def test_engine_uses_calendar_next_open_and_timezone_aware_fills() -> None:
    calendar = make_calendar()
    rows = [
        {
            "date": "2024-01-02",
            "ticker": "AAA",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000,
            "trading_value": 1_000_000,
        },
        {
            "date": "2024-01-03",
            "ticker": "AAA",
            "open": 101.0,
            "high": 102.0,
            "low": 100.0,
            "close": 101.0,
            "volume": 1_000,
            "trading_value": 1_000_000,
        },
    ]
    feed = MarketDataFeed(pd.DataFrame(rows), calendar=calendar)
    portfolio = Portfolio(Decimal("10000"))
    engine = BacktestEngine(
        feed,
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
        BacktestConfig(initial_cash=Decimal("10000")),
        calendar=calendar,
    )
    result = engine.run()
    assert result.fills[0].timestamp.tzinfo is not None
    assert result.fills[0].timestamp == datetime(2024, 1, 3, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    assert result.fills[0].price == Decimal("101")


def test_rebalance_schedules_follow_calendar_boundaries() -> None:
    calendar = make_calendar()
    weekly = WeeklyRebalanceSchedule(anchor="first_session")
    monthly = MonthlyRebalanceSchedule(anchor="first_session")

    assert weekly.should_rebalance(date(2024, 1, 2), calendar)
    assert not weekly.should_rebalance(date(2024, 1, 3), calendar)
    assert monthly.should_rebalance(date(2024, 1, 2), calendar)
    assert not monthly.should_rebalance(date(2024, 1, 4), calendar)
