from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from alpha_cycle.backtest.engine import BacktestConfig, BacktestEngine, ExecutionPrice
from alpha_cycle.brokers.simulated import SimulatedBroker
from alpha_cycle.data.market import MarketDataFeed, validate_ohlcv
from alpha_cycle.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    Side,
    TargetPosition,
    TimeInForce,
)
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.risk.manager import RiskConfig, RiskManager


class FirstSessionTargetStrategy:
    def __init__(self, weight: float = 0.6) -> None:
        self.weight = weight
        self._used = False

    def generate_targets(
        self,
        event_date: date,
        history: pd.DataFrame,
    ) -> list[TargetPosition] | None:
        del event_date, history
        if self._used:
            return None
        self._used = True
        return [TargetPosition("AAA", self.weight)]


def _risk() -> RiskManager:
    return RiskManager(
        RiskConfig(
            max_positions=10,
            max_single_position=1.0,
            max_gross_exposure=1.0,
            max_daily_turnover=1.0,
            max_order_pct_of_trading_value=1.0,
            max_daily_loss=1.0,
            max_portfolio_drawdown=1.0,
        )
    )


def _bars(
    days: int,
    *,
    volume: int = 1_000,
    halted_first: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for day in range(1, days + 1):
        rows.append(
            {
                "date": f"2024-01-{day:02d}",
                "ticker": "AAA",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": volume,
                "trading_value": 1_000_000,
                "is_halted": halted_first and day == 1,
            }
        )
    return pd.DataFrame(rows)


def test_order_tracks_remaining_quantity_and_can_be_cancelled() -> None:
    order = Order(
        "O1",
        date(2024, 1, 1),
        "AAA",
        Side.BUY,
        10,
        Decimal("100"),
        time_in_force=TimeInForce.GTC,
    )
    order.record_fill(4, date(2024, 1, 2))
    assert order.status is OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 4
    assert order.remaining_quantity == 6
    order.cancel(date(2024, 1, 3), "research_cancel")
    assert order.status is OrderStatus.CANCELLED
    assert order.last_attempt_reason == "research_cancel"


def test_broker_can_fill_one_order_across_multiple_sessions() -> None:
    portfolio = Portfolio(Decimal("100000"))
    broker = SimulatedBroker(max_volume_participation=Decimal("0.1"))
    order = Order(
        "O1",
        date(2024, 1, 1),
        "AAA",
        Side.BUY,
        10,
        Decimal("100"),
        time_in_force=TimeInForce.GTC,
    )
    capacity = broker.volume_capacity(50)
    first = broker.execute(
        order,
        Decimal("100"),
        date(2024, 1, 2),
        portfolio,
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        available_quantity=capacity,
    )
    second = broker.execute(
        order,
        Decimal("100"),
        date(2024, 1, 3),
        portfolio,
        high_price=Decimal("101"),
        low_price=Decimal("99"),
        available_quantity=capacity,
    )
    assert first is not None and second is not None
    assert first.quantity == second.quantity == 5
    assert first.order_id == second.order_id == "O1"
    assert first.fill_id != second.fill_id
    assert order.status is OrderStatus.FILLED
    assert order.remaining_quantity == 0


def test_limit_order_waits_until_daily_range_reaches_limit() -> None:
    portfolio = Portfolio(Decimal("100000"))
    broker = SimulatedBroker()
    order = Order(
        "O1",
        date(2024, 1, 1),
        "AAA",
        Side.BUY,
        2,
        Decimal("100"),
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        limit_price=Decimal("95"),
    )
    missed = broker.execute(
        order,
        Decimal("100"),
        date(2024, 1, 2),
        portfolio,
        high_price=Decimal("103"),
        low_price=Decimal("96"),
        available_quantity=10,
    )
    assert missed is None
    assert order.status is OrderStatus.PENDING
    assert order.last_attempt_reason == "limit_not_reached"
    filled = broker.execute(
        order,
        Decimal("100"),
        date(2024, 1, 3),
        portfolio,
        high_price=Decimal("102"),
        low_price=Decimal("94"),
        available_quantity=10,
    )
    assert filled is not None
    assert filled.price == Decimal("95")
    assert order.status is OrderStatus.FILLED


def test_day_limit_order_expires_after_one_daily_bar_attempt() -> None:
    config = BacktestConfig(
        initial_cash=Decimal("1000"),
        execution_price=ExecutionPrice.SAME_CLOSE,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.DAY,
        limit_offset_bps=Decimal("1000"),
    )
    engine = BacktestEngine(
        MarketDataFeed(_bars(1)),
        FirstSessionTargetStrategy(weight=0.5),
        Portfolio(config.initial_cash),
        SimulatedBroker(max_volume_participation=config.max_volume_participation),
        _risk(),
        config,
    )
    result = engine.run()
    assert not result.fills
    assert result.orders[0]["status"] == "expired"
    assert result.orders[0]["last_attempt_reason"] == "limit_not_reached"


def test_gtc_order_survives_halt_and_fills_next_session() -> None:
    config = BacktestConfig(
        initial_cash=Decimal("1000"),
        execution_price=ExecutionPrice.SAME_CLOSE,
        time_in_force=TimeInForce.GTC,
    )
    engine = BacktestEngine(
        MarketDataFeed(_bars(2, halted_first=True)),
        FirstSessionTargetStrategy(weight=0.5),
        Portfolio(config.initial_cash),
        SimulatedBroker(max_volume_participation=config.max_volume_participation),
        _risk(),
        config,
    )
    result = engine.run()
    assert len(result.fills) == 1
    assert result.fills[0].timestamp.date() == date(2024, 1, 2)
    assert result.orders[0]["status"] == "filled"
    assert result.orders[0]["filled_quantity"] == 5


def test_engine_emits_multiple_unique_fills_for_one_gtc_order() -> None:
    config = BacktestConfig(
        initial_cash=Decimal("1000"),
        execution_price=ExecutionPrice.SAME_CLOSE,
        time_in_force=TimeInForce.GTC,
        max_volume_participation=Decimal("0.4"),
    )
    engine = BacktestEngine(
        MarketDataFeed(_bars(3, volume=5)),
        FirstSessionTargetStrategy(weight=0.6),
        Portfolio(config.initial_cash),
        SimulatedBroker(max_volume_participation=config.max_volume_participation),
        _risk(),
        config,
    )
    result = engine.run()
    assert [fill.quantity for fill in result.fills] == [2, 2, 2]
    assert len({fill.fill_id for fill in result.fills}) == 3
    assert {fill.order_id for fill in result.fills} == {"O00000001"}
    assert result.orders[0]["status"] == "filled"
    assert result.orders[0]["remaining_quantity"] == 0


def test_halt_flag_validation_is_strict() -> None:
    valid, _ = validate_ohlcv(_bars(1, halted_first=True))
    assert bool(valid.loc[0, "is_halted"])
    broken = _bars(1)
    broken["is_halted"] = "unknown"
    with pytest.raises(ValueError, match="Invalid is_halted"):
        validate_ohlcv(broken)


def test_invalid_limit_and_participation_settings_are_rejected() -> None:
    with pytest.raises(ValueError, match="limit_price"):
        Order(
            "O1",
            date(2024, 1, 1),
            "AAA",
            Side.BUY,
            1,
            Decimal("100"),
            order_type=OrderType.LIMIT,
        )
    with pytest.raises(ValueError, match="max_volume_participation"):
        BacktestConfig(max_volume_participation=Decimal("1.1"))
