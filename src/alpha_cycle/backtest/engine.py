"""Chronological event engine with explicit target, order, risk, and fill stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

import pandas as pd

from alpha_cycle.brokers.simulated import SimulatedBroker
from alpha_cycle.calendar.base import TradingCalendar
from alpha_cycle.calendar.rebalance import MonthlyRebalanceSchedule, WeeklyRebalanceSchedule
from alpha_cycle.data.market import MarketDataFeed
from alpha_cycle.domain.models import Fill, Order, OrderStatus, Side, TargetPosition
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.risk.manager import RiskManager
from alpha_cycle.strategies.protocol import Strategy


class ExecutionPrice(StrEnum):
    """Supported timing conventions."""

    NEXT_OPEN = "next_open"
    SAME_CLOSE = "same_close"


@dataclass(frozen=True)
class BacktestConfig:
    """Core simulation configuration."""

    initial_cash: Decimal = Decimal("100000000")
    execution_price: ExecutionPrice = ExecutionPrice.NEXT_OPEN
    periods_per_year: int = 252
    risk_free_rate: float = 0.0
    rebalance_frequency: str = "every_session"
    rebalance_anchor: str = "first_session"


@dataclass
class BacktestResult:
    """Complete deterministic audit trail."""

    equity_curve: list[dict[str, object]] = field(default_factory=list)
    positions: list[dict[str, object]] = field(default_factory=list)
    orders: list[dict[str, object]] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    trades: list[dict[str, object]] = field(default_factory=list)
    turnover: float = 0.0


class BacktestEngine:
    """Coordinate the feed and isolated strategy, risk, broker, and portfolio layers."""

    def __init__(
        self,
        feed: MarketDataFeed,
        strategy: Strategy,
        portfolio: Portfolio,
        broker: SimulatedBroker,
        risk_manager: RiskManager,
        config: BacktestConfig,
        *,
        calendar: TradingCalendar | None = None,
    ) -> None:
        self.feed = feed
        self.strategy = strategy
        self.portfolio = portfolio
        self.broker = broker
        self.risk = risk_manager
        self.config = config
        self.calendar = calendar or getattr(feed, "calendar", None)
        self._rebalance_schedule = self._build_rebalance_schedule(config)
        self._order_sequence = 0

    @staticmethod
    def _build_rebalance_schedule(config: BacktestConfig):
        frequency = (config.rebalance_frequency or "every_session").lower()
        if frequency == "every_session":
            return None
        if frequency == "weekly":
            return WeeklyRebalanceSchedule(anchor=config.rebalance_anchor)
        if frequency == "monthly":
            return MonthlyRebalanceSchedule(anchor=config.rebalance_anchor)
        raise ValueError(f"Unsupported rebalance_frequency: {config.rebalance_frequency}")

    @staticmethod
    def _decimal(value: object) -> Decimal:
        return Decimal(str(value))

    def _orders_from_targets(
        self,
        targets: list[TargetPosition],
        event_date: date,
        bars: pd.DataFrame,
        price_column: str,
    ) -> list[Order]:
        price_map = {
            str(row["ticker"]): self._decimal(row[price_column])
            for _, row in bars.iterrows()
        }
        self.portfolio.mark(price_map)
        target_map = {target.ticker: target.weight for target in targets}
        all_tickers = sorted(set(self.portfolio.positions) | set(target_map))
        equity = self.portfolio.total_equity
        orders: list[Order] = []
        for ticker in all_tickers:
            price = price_map.get(ticker)
            if price is None:
                continue
            held = self.portfolio.positions.get(ticker)
            current_quantity = held.quantity if held else 0
            desired_value = equity * self._decimal(target_map.get(ticker, 0.0))
            desired_quantity = int((desired_value / price).to_integral_value(rounding=ROUND_FLOOR))
            delta = desired_quantity - current_quantity
            if delta == 0:
                continue
            self._order_sequence += 1
            orders.append(
                Order(
                    order_id=f"O{self._order_sequence:08d}",
                    created_at=event_date,
                    ticker=ticker,
                    side=Side.BUY if delta > 0 else Side.SELL,
                    quantity=abs(delta),
                    reference_price=price,
                )
            )
        return sorted(orders, key=lambda order: (order.side is Side.BUY, order.ticker))

    def _process_orders(
        self,
        orders: list[Order],
        event_date: date,
        bars: pd.DataFrame,
        price_column: str,
        result: BacktestResult,
        peak_equity: Decimal,
        day_start_equity: Decimal,
        *,
        execution_timestamp: datetime | None = None,
    ) -> None:
        bars_by_ticker = {str(row["ticker"]): row for _, row in bars.iterrows()}
        daily_notional = Decimal("0")
        for order in orders:
            row = bars_by_ticker.get(order.ticker)
            if row is None:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "missing_execution_bar"
            else:
                decision = self.risk.evaluate(
                    order,
                    self.portfolio,
                    trading_value=self._decimal(row["trading_value"]),
                    daily_order_notional=daily_notional,
                    peak_equity=peak_equity,
                    day_start_equity=day_start_equity,
                )
                if not decision.approved:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = decision.code
                else:
                    fill = self.broker.execute(
                        order,
                        self._decimal(row[price_column]),
                        event_date,
                        self.portfolio,
                        execution_timestamp=execution_timestamp,
                    )
                    if fill is not None:
                        result.fills.append(fill)
                        daily_notional += fill.gross_value
            result.orders.append(
                {
                    **asdict(order),
                    "created_at": order.created_at.isoformat(),
                    "side": order.side.value,
                    "status": order.status.value,
                    "reference_price": str(order.reference_price),
                }
            )

    def _should_rebalance(self, event_date: date) -> bool:
        if self._rebalance_schedule is None:
            return True
        if self.calendar is None:
            return True
        return self._rebalance_schedule.should_rebalance(event_date, self.calendar)

    def _execution_timestamp(self, event_date: date, *, close: bool) -> datetime:
        if self.calendar is None:
            return datetime.combine(event_date, time(9, 0), tzinfo=ZoneInfo("Asia/Seoul"))
        if close:
            return self.calendar.session_close(event_date)
        return self.calendar.session_open(event_date)

    def run(self) -> BacktestResult:
        """Run all events in chronological order without future-row access."""
        result = BacktestResult()
        pending_targets: tuple[list[TargetPosition], date] | None = None
        peak_equity = self.portfolio.total_equity
        for event_date in self.feed.dates:
            bars = self.feed.bars_on(event_date)
            day_start = self.portfolio.total_equity
            if pending_targets is not None:
                pending_targets_list, pending_execution_date = pending_targets
                if event_date == pending_execution_date:
                    execution_bars = self.feed.bars_on(pending_execution_date)
                    if not execution_bars.empty:
                        orders = self._orders_from_targets(
                            pending_targets_list, event_date, execution_bars, "open"
                        )
                        self._process_orders(
                            orders,
                            pending_execution_date,
                            execution_bars,
                            "open",
                            result,
                            peak_equity,
                            day_start,
                            execution_timestamp=self._execution_timestamp(
                                pending_execution_date, close=False
                            ),
                        )
                    pending_targets = None

            history = self.feed.history_through(event_date)
            if self._should_rebalance(event_date):
                targets = self.strategy.generate_targets(event_date, history)
            else:
                targets = None
            if targets is not None:
                if self.config.execution_price is ExecutionPrice.SAME_CLOSE:
                    orders = self._orders_from_targets(targets, event_date, bars, "close")
                    self._process_orders(
                        orders,
                        event_date,
                        bars,
                        "close",
                        result,
                        peak_equity,
                        day_start,
                        execution_timestamp=self._execution_timestamp(event_date, close=True),
                    )
                else:
                    if self.calendar is None:
                        index = self.feed.dates.index(event_date)
                        next_event_date = (
                            self.feed.dates[index + 1]
                            if index + 1 < len(self.feed.dates)
                            else None
                        )
                    else:
                        try:
                            next_event_date = self.calendar.next_session(event_date)
                        except ValueError:
                            next_event_date = None
                    if next_event_date is not None:
                        pending_targets = (targets, next_event_date)

            close_prices = {
                str(row["ticker"]): self._decimal(row["close"]) for _, row in bars.iterrows()
            }
            self.portfolio.mark(close_prices)
            equity = self.portfolio.total_equity
            peak_equity = max(peak_equity, equity)
            result.equity_curve.append(
                {
                    "date": event_date.isoformat(),
                    "cash": str(self.portfolio.cash),
                    "equity": str(equity),
                    "realized_pnl": str(self.portfolio.realized_pnl),
                    "unrealized_pnl": str(self.portfolio.unrealized_pnl),
                    "cash_weight": self.portfolio.cash_weight,
                }
            )
            result.positions.extend(self.portfolio.snapshot(event_date))
        average_equity = sum(
            (Decimal(str(row["equity"])) for row in result.equity_curve), start=Decimal("0")
        ) / max(len(result.equity_curve), 1)
        result.turnover = (
            float(self.portfolio.traded_notional / average_equity) if average_equity else 0.0
        )
        result.trades = [
            {
                "date": fill.timestamp.date().isoformat(),
                "ticker": fill.ticker,
                "side": fill.side.value,
                "quantity": fill.quantity,
                "price": str(fill.price),
                "gross_value": str(fill.gross_value),
            }
            for fill in result.fills
        ]
        return result
