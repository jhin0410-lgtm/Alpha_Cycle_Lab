from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from alpha_cycle.backtest.engine import BacktestConfig, BacktestEngine, ExecutionPrice
from alpha_cycle.brokers.simulated import SimulatedBroker
from alpha_cycle.data.integrity import (
    CorporateActionStore,
    CorporateActionType,
    PriceBasis,
    UniverseMembershipStore,
    validate_corporate_actions,
    validate_universe_membership,
)
from alpha_cycle.data.market import MarketDataFeed
from alpha_cycle.domain.models import Fill, Side, TargetPosition
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.risk.manager import RiskConfig, RiskManager


class NoopStrategy:
    def generate_targets(
        self, event_date: date, history: pd.DataFrame
    ) -> list[TargetPosition] | None:
        del event_date, history
        return None


class OutsideUniverseStrategy:
    def __init__(self) -> None:
        self.seen_tickers: tuple[str, ...] = ()

    def generate_targets(
        self, event_date: date, history: pd.DataFrame
    ) -> list[TargetPosition] | None:
        del event_date
        self.seen_tickers = tuple(sorted(history["ticker"].astype(str).unique()))
        return [TargetPosition("BBB", 0.5)]


def _risk_manager() -> RiskManager:
    return RiskManager(
        RiskConfig(
            max_single_position=1.0,
            max_gross_exposure=1.0,
            max_daily_turnover=1.0,
            max_order_pct_of_trading_value=1.0,
            max_daily_loss=1.0,
            max_portfolio_drawdown=1.0,
        )
    )


def _prices(*, close_aaa: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2024-01-03",
                "ticker": "AAA",
                "open": close_aaa,
                "high": close_aaa + 1,
                "low": close_aaa - 1,
                "close": close_aaa,
                "adjusted_close": close_aaa * 10,
                "volume": 1_000,
                "trading_value": 1_000_000,
            },
            {
                "date": "2024-01-03",
                "ticker": "BBB",
                "open": 80,
                "high": 81,
                "low": 79,
                "close": 80,
                "adjusted_close": 800,
                "volume": 1_000,
                "trading_value": 1_000_000,
            },
        ]
    )


def _split_frame(*, action_type: str = "split", ratio: object = 2) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "action_type": action_type,
                "effective_date": "2024-01-03",
                "available_date": "2024-01-02",
                "source": "fixture",
                "revision_id": "v1",
                "ratio": ratio,
            }
        ]
    )


def _seed_position(portfolio: Portfolio) -> None:
    portfolio.apply_fill(
        Fill(
            order_id="seed",
            timestamp=datetime(2024, 1, 2, 15, 30, tzinfo=ZoneInfo("Asia/Seoul")),
            ticker="AAA",
            side=Side.BUY,
            quantity=10,
            price=Decimal("100"),
            commission=Decimal("0"),
            tax=Decimal("0"),
            slippage=Decimal("0"),
        )
    )


def test_price_basis_is_explicit_and_adjusted_close_does_not_replace_close() -> None:
    feed = MarketDataFeed(_prices())
    assert feed.price_basis is PriceBasis.RAW
    bars = feed.bars_on(date(2024, 1, 3))
    assert bars.loc[0, "close"] == 100
    assert bars.loc[0, "adjusted_close"] == 1000

    adjusted_feed = MarketDataFeed(
        _prices(),
        price_basis=PriceBasis.SPLIT_ADJUSTED,
    )
    with pytest.raises(ValueError, match="require raw"):
        BacktestEngine(
            adjusted_feed,
            NoopStrategy(),
            Portfolio(Decimal("10000")),
            SimulatedBroker(),
            _risk_manager(),
            BacktestConfig(),
        )


def test_corporate_action_store_blocks_future_information() -> None:
    store = CorporateActionStore(_split_frame())
    assert store.as_of(date(2024, 1, 1)).empty
    actions = store.actions_effective_on(
        date(2024, 1, 3),
        information_date=date(2024, 1, 3),
    )
    assert len(actions) == 1
    assert actions[0].ratio == Decimal("2")


@pytest.mark.parametrize("ratio", [0, 1, -2])
def test_invalid_split_ratios_are_rejected(ratio: int) -> None:
    with pytest.raises(ValueError, match="Split ratio"):
        validate_corporate_actions(_split_frame(ratio=ratio))


def test_split_cannot_define_cash_amount() -> None:
    frame = _split_frame()
    frame["cash_amount"] = 10
    with pytest.raises(ValueError, match="cash_amount"):
        validate_corporate_actions(frame)


def test_universe_membership_is_point_in_time_and_member_to_is_exclusive() -> None:
    frame = pd.DataFrame(
        [
            {
                "universe": "TEST",
                "ticker": "AAA",
                "member_from": "2024-01-02",
                "member_to": "2024-01-05",
                "available_date": "2024-01-01",
                "source": "fixture",
                "revision_id": "v1",
            },
            {
                "universe": "TEST",
                "ticker": "BBB",
                "member_from": "2024-01-03",
                "member_to": None,
                "available_date": "2024-01-03",
                "source": "fixture",
                "revision_id": "v1",
            },
        ]
    )
    store = UniverseMembershipStore(frame)
    assert store.members_as_of("TEST", date(2024, 1, 2)) == ("AAA",)
    assert store.members_as_of("TEST", date(2024, 1, 3)) == ("AAA", "BBB")
    assert store.members_as_of("TEST", date(2024, 1, 5)) == ("BBB",)


def test_overlapping_universe_intervals_are_rejected() -> None:
    frame = pd.DataFrame(
        [
            {
                "universe": "TEST",
                "ticker": "AAA",
                "member_from": "2024-01-01",
                "member_to": "2024-02-01",
                "available_date": "2024-01-01",
                "source": "fixture",
                "revision_id": "v1",
            },
            {
                "universe": "TEST",
                "ticker": "AAA",
                "member_from": "2024-01-15",
                "member_to": None,
                "available_date": "2024-01-01",
                "source": "fixture",
                "revision_id": "v2",
            },
        ]
    )
    with pytest.raises(ValueError, match="Overlapping"):
        validate_universe_membership(frame)


def test_portfolio_split_preserves_cash_pnl_and_cost_basis() -> None:
    portfolio = Portfolio(Decimal("10000"))
    _seed_position(portfolio)
    cash_before = portfolio.cash
    realized_before = portfolio.realized_pnl
    cost_before = portfolio.positions["AAA"].average_cost * 10

    application = portfolio.apply_split(
        "AAA",
        Decimal("2"),
        date(2024, 1, 3),
        action_type=CorporateActionType.SPLIT,
    )

    assert application.quantity_after == 20
    assert portfolio.positions["AAA"].average_cost == Decimal("50")
    assert portfolio.cash == cash_before
    assert portfolio.realized_pnl == realized_before
    assert portfolio.positions["AAA"].average_cost * 20 == cost_before
    assert portfolio.last_prices["AAA"] == Decimal("50")


def test_fractional_reverse_split_is_rejected() -> None:
    portfolio = Portfolio(Decimal("10000"))
    _seed_position(portfolio)
    with pytest.raises(ValueError, match="fractional shares"):
        portfolio.apply_split(
            "AAA",
            Decimal("0.15"),
            date(2024, 1, 3),
            action_type=CorporateActionType.REVERSE_SPLIT,
        )


def test_engine_applies_split_before_session_processing() -> None:
    portfolio = Portfolio(Decimal("10000"))
    _seed_position(portfolio)
    engine = BacktestEngine(
        MarketDataFeed(_prices(close_aaa=50)),
        NoopStrategy(),
        portfolio,
        SimulatedBroker(),
        _risk_manager(),
        BacktestConfig(),
        corporate_actions=CorporateActionStore(_split_frame()),
    )
    result = engine.run()
    assert portfolio.positions["AAA"].quantity == 20
    assert portfolio.positions["AAA"].average_cost == Decimal("50")
    assert result.corporate_actions[0]["status"] == "applied"
    assert result.equity_curve[0]["equity"] == "10000"


def test_engine_filters_strategy_history_and_rejects_outside_target() -> None:
    memberships = pd.DataFrame(
        [
            {
                "universe": "TEST",
                "ticker": "AAA",
                "member_from": "2024-01-03",
                "member_to": None,
                "available_date": "2024-01-03",
                "source": "fixture",
                "revision_id": "v1",
            }
        ]
    )
    strategy = OutsideUniverseStrategy()
    engine = BacktestEngine(
        MarketDataFeed(_prices()),
        strategy,
        Portfolio(Decimal("10000")),
        SimulatedBroker(),
        _risk_manager(),
        BacktestConfig(execution_price=ExecutionPrice.SAME_CLOSE),
        universe_store=UniverseMembershipStore(memberships),
        universe_name="TEST",
    )
    result = engine.run()
    assert strategy.seen_tickers == ("AAA",)
    assert result.orders[0]["ticker"] == "BBB"
    assert result.orders[0]["status"] == "rejected"
    assert result.orders[0]["rejection_reason"] == "outside_active_universe"
    assert not result.fills


def test_engine_stops_on_unsupported_corporate_action() -> None:
    dividend = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "action_type": "cash_dividend",
                "effective_date": "2024-01-03",
                "available_date": "2024-01-02",
                "source": "fixture",
                "revision_id": "v1",
                "cash_amount": 1,
                "currency": "KRW",
            }
        ]
    )
    engine = BacktestEngine(
        MarketDataFeed(_prices()),
        NoopStrategy(),
        Portfolio(Decimal("10000")),
        SimulatedBroker(),
        _risk_manager(),
        BacktestConfig(),
        corporate_actions=CorporateActionStore(dividend),
    )
    with pytest.raises(
        ValueError,
        match="Unsupported corporate action cash_dividend",
    ):
        engine.run()
