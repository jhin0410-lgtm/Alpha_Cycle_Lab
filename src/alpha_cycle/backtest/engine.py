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
from alpha_cycle.calendar.rebalance import (
    MonthlyRebalanceSchedule,
    RebalanceSchedule,
    WeeklyRebalanceSchedule,
)
from alpha_cycle.data.integrity import (
    CorporateActionStore,
    CorporateActionType,
    PriceBasis,
    UniverseMembershipStore,
)
from alpha_cycle.data.market import MarketDataFeed
from alpha_cycle.domain.models import (
    Fill,
    Order,
    OrderStatus,
    OrderType,
    Side,
    TargetPosition,
    TimeInForce,
)
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.risk.manager import RiskManager
from alpha_cycle.strategies.protocol import Strategy


class ExecutionPrice(StrEnum):
    """Supported timing conventions."""

    NEXT_OPEN = "next_open"
    SAME_CLOSE = "same_close"


@dataclass(frozen=True)
class BacktestConfig:
    """Core simulation and order-lifecycle configuration."""

    initial_cash: Decimal = Decimal("100000000")
    execution_price: ExecutionPrice = ExecutionPrice.NEXT_OPEN
    periods_per_year: int = 252
    risk_free_rate: float = 0.0
    rebalance_frequency: str = "every_session"
    rebalance_anchor: str = "first_session"
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_offset_bps: Decimal = Decimal("0")
    max_volume_participation: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.limit_offset_bps < 0:
            raise ValueError("limit_offset_bps cannot be negative")
        if not Decimal("0") < self.max_volume_participation <= Decimal("1"):
            raise ValueError("max_volume_participation must be greater than 0 and at most 1")


@dataclass
class BacktestResult:
    """Complete deterministic audit trail."""

    equity_curve: list[dict[str, object]] = field(default_factory=list)
    positions: list[dict[str, object]] = field(default_factory=list)
    orders: list[dict[str, object]] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    trades: list[dict[str, object]] = field(default_factory=list)
    corporate_actions: list[dict[str, object]] = field(default_factory=list)
    turnover: float = 0.0


class BacktestEngine:
    """Coordinate feed, strategy, integrity, orders, risk, broker, and portfolio."""

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
        corporate_actions: CorporateActionStore | None = None,
        universe_store: UniverseMembershipStore | None = None,
        universe_name: str | None = None,
    ) -> None:
        if feed.price_basis is not PriceBasis.RAW:
            raise ValueError(
                "Backtest execution and portfolio marking require raw market prices"
            )
        if (universe_store is None) != (universe_name is None):
            raise ValueError("universe_store and universe_name must be provided together")
        if broker.max_volume_participation != config.max_volume_participation:
            raise ValueError(
                "Broker and BacktestConfig max_volume_participation must match"
            )
        self.feed = feed
        self.strategy = strategy
        self.portfolio = portfolio
        self.broker = broker
        self.risk = risk_manager
        self.config = config
        self.calendar = calendar or feed.calendar
        self.corporate_action_store = corporate_actions
        self.universe_store = universe_store
        self.universe_name = universe_name
        self._rebalance_schedule: RebalanceSchedule | None = self._build_rebalance_schedule(
            config
        )
        self._order_sequence = 0
        self._applied_action_keys: set[
            tuple[str, CorporateActionType, date, str]
        ] = set()

    @staticmethod
    def _build_rebalance_schedule(config: BacktestConfig) -> RebalanceSchedule | None:
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

    def _active_universe(self, event_date: date) -> set[str] | None:
        if self.universe_store is None or self.universe_name is None:
            return None
        return set(
            self.universe_store.members_as_of(
                self.universe_name,
                event_date,
                information_date=event_date,
            )
        )

    def _next_order_id(self) -> str:
        self._order_sequence += 1
        return f"O{self._order_sequence:08d}"

    def _limit_price(self, side: Side, reference_price: Decimal) -> Decimal | None:
        if self.config.order_type is OrderType.MARKET:
            return None
        offset = self.config.limit_offset_bps / Decimal("10000")
        multiplier = (
            Decimal("1") - offset if side is Side.BUY else Decimal("1") + offset
        )
        price = reference_price * multiplier
        if price <= 0:
            raise ValueError("Configured limit offset produces a non-positive price")
        return price

    def _projected_quantity(self, ticker: str, working_orders: list[Order]) -> int:
        held = self.portfolio.positions.get(ticker)
        projected = held.quantity if held else 0
        for order in working_orders:
            if not order.is_open or order.ticker != ticker:
                continue
            signed = (
                order.remaining_quantity
                if order.side is Side.BUY
                else -order.remaining_quantity
            )
            projected += signed
        return max(projected, 0)

    def _orders_from_targets(
        self,
        targets: list[TargetPosition],
        event_date: date,
        bars: pd.DataFrame,
        price_column: str,
        *,
        active_universe: set[str] | None = None,
        working_orders: list[Order] | None = None,
    ) -> list[Order]:
        open_orders = working_orders or []
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
            outside_universe = active_universe is not None and ticker not in active_universe
            if outside_universe and ticker not in target_map:
                continue
            price = price_map.get(ticker)
            if price is None:
                continue
            desired_value = equity * self._decimal(target_map.get(ticker, 0.0))
            desired_quantity = int(
                (desired_value / price).to_integral_value(rounding=ROUND_FLOOR)
            )
            projected_quantity = self._projected_quantity(ticker, open_orders)
            delta = desired_quantity - projected_quantity
            if delta == 0:
                continue
            side = Side.BUY if delta > 0 else Side.SELL
            order = Order(
                order_id=self._next_order_id(),
                created_at=event_date,
                ticker=ticker,
                side=side,
                quantity=abs(delta),
                reference_price=price,
                order_type=self.config.order_type,
                time_in_force=self.config.time_in_force,
                limit_price=self._limit_price(side, price),
            )
            if outside_universe:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = "outside_active_universe"
            orders.append(order)
        return sorted(orders, key=lambda order: (order.side is Side.BUY, order.ticker))

    @staticmethod
    def _order_record(order: Order) -> dict[str, object]:
        return {
            **asdict(order),
            "created_at": order.created_at.isoformat(),
            "side": order.side.value,
            "status": order.status.value,
            "order_type": order.order_type.value,
            "time_in_force": order.time_in_force.value,
            "reference_price": str(order.reference_price),
            "limit_price": str(order.limit_price) if order.limit_price is not None else None,
            "last_attempt_at": (
                order.last_attempt_at.isoformat() if order.last_attempt_at is not None else None
            ),
            "remaining_quantity": order.remaining_quantity,
        }

    def _session_volume_capacity(self, bars: pd.DataFrame) -> dict[str, int]:
        return {
            str(row["ticker"]): self.broker.volume_capacity(row["volume"])
            for _, row in bars.iterrows()
        }

    def _process_orders(
        self,
        orders: list[Order],
        event_date: date,
        bars: pd.DataFrame,
        price_column: str,
        result: BacktestResult,
        peak_equity: Decimal,
        day_start_equity: Decimal,
        daily_notional: Decimal,
        volume_remaining: dict[str, int],
        *,
        open_timestamp: datetime,
        close_timestamp: datetime,
    ) -> tuple[list[Order], Decimal]:
        bars_by_ticker = {str(row["ticker"]): row for _, row in bars.iterrows()}
        surviving: list[Order] = []
        for order in sorted(orders, key=lambda item: (item.created_at, item.order_id)):
            if not order.is_open:
                continue
            row = bars_by_ticker.get(order.ticker)
            if row is None:
                order.record_attempt(event_date, "missing_execution_bar")
            else:
                available_quantity = volume_remaining.get(order.ticker, 0)
                halted = bool(row.get("is_halted", False))
                proposed_quantity = min(order.remaining_quantity, available_quantity)
                if halted or proposed_quantity <= 0:
                    fill = self.broker.execute(
                        order,
                        self._decimal(row[price_column]),
                        event_date,
                        self.portfolio,
                        execution_timestamp=(
                            close_timestamp
                            if order.order_type is OrderType.LIMIT
                            else open_timestamp
                        ),
                        high_price=self._decimal(row["high"]),
                        low_price=self._decimal(row["low"]),
                        available_quantity=available_quantity,
                        is_halted=halted,
                    )
                else:
                    decision = self.risk.evaluate(
                        order,
                        self.portfolio,
                        trading_value=self._decimal(row["trading_value"]),
                        daily_order_notional=daily_notional,
                        peak_equity=peak_equity,
                        day_start_equity=day_start_equity,
                        proposed_quantity=proposed_quantity,
                    )
                    if not decision.approved:
                        order.record_attempt(event_date, decision.code)
                        if order.filled_quantity == 0:
                            order.status = OrderStatus.REJECTED
                            order.rejection_reason = decision.code
                        fill = None
                    else:
                        fill = self.broker.execute(
                            order,
                            self._decimal(row[price_column]),
                            event_date,
                            self.portfolio,
                            execution_timestamp=(
                                close_timestamp
                                if order.order_type is OrderType.LIMIT
                                else open_timestamp
                            ),
                            high_price=self._decimal(row["high"]),
                            low_price=self._decimal(row["low"]),
                            available_quantity=available_quantity,
                            is_halted=False,
                        )
                if fill is not None:
                    result.fills.append(fill)
                    daily_notional += fill.gross_value
                    volume_remaining[order.ticker] = max(
                        volume_remaining.get(order.ticker, 0) - fill.quantity,
                        0,
                    )
            if order.is_open and order.time_in_force is TimeInForce.DAY:
                order.expire(
                    event_date,
                    order.last_attempt_reason or "day_order_expired",
                )
            if order.is_open:
                surviving.append(order)
        return surviving, daily_notional

    def _apply_corporate_actions(
        self,
        event_date: date,
        result: BacktestResult,
    ) -> None:
        store = self.corporate_action_store
        if store is None:
            return
        actions = store.actions_effective_on(
            event_date,
            information_date=event_date,
        )
        for action in actions:
            if action.event_key in self._applied_action_keys:
                continue
            if action.action_type not in {
                CorporateActionType.SPLIT,
                CorporateActionType.REVERSE_SPLIT,
            }:
                raise ValueError(
                    f"Unsupported corporate action {action.action_type.value} "
                    f"for {action.ticker} on {event_date}"
                )
            if action.ratio is None:
                raise ValueError("Split corporate action is missing ratio")
            application = self.portfolio.apply_split(
                action.ticker,
                action.ratio,
                event_date,
                action_type=action.action_type,
            )
            result.corporate_actions.append(
                {
                    "effective_date": application.effective_date.isoformat(),
                    "ticker": application.ticker,
                    "action_type": application.action_type.value,
                    "ratio": str(application.ratio),
                    "quantity_before": application.quantity_before,
                    "quantity_after": application.quantity_after,
                    "average_cost_before": str(application.average_cost_before),
                    "average_cost_after": str(application.average_cost_after),
                    "cash_effect": str(application.cash_effect),
                    "status": application.status,
                    "reason": application.reason,
                }
            )
            self._applied_action_keys.add(action.event_key)

    def _should_rebalance(self, event_date: date) -> bool:
        schedule = self._rebalance_schedule
        calendar = self.calendar
        if schedule is None or calendar is None:
            return True
        return bool(schedule.should_rebalance(event_date, calendar))

    def _execution_timestamp(self, event_date: date, *, close: bool) -> datetime:
        if self.calendar is None:
            session_time = time(15, 30) if close else time(9, 0)
            return datetime.combine(
                event_date,
                session_time,
                tzinfo=ZoneInfo("Asia/Seoul"),
            )
        if close:
            return self.calendar.session_close(event_date)
        return self.calendar.session_open(event_date)

    def run(self) -> BacktestResult:
        """Run all events chronologically without exposing future rows."""
        result = BacktestResult()
        pending_targets: tuple[list[TargetPosition], date] | None = None
        working_orders: list[Order] = []
        all_orders: list[Order] = []
        peak_equity = self.portfolio.total_equity

        for event_date in self.feed.dates:
            self._apply_corporate_actions(event_date, result)
            bars = self.feed.bars_on(event_date)
            day_start = self.portfolio.total_equity
            active_universe = self._active_universe(event_date)
            volume_remaining = self._session_volume_capacity(bars)
            daily_notional = Decimal("0")
            open_timestamp = self._execution_timestamp(event_date, close=False)
            close_timestamp = self._execution_timestamp(event_date, close=True)

            open_attempt_orders = list(working_orders)
            working_orders = []
            if pending_targets is not None:
                pending_targets_list, pending_execution_date = pending_targets
                if event_date == pending_execution_date:
                    new_orders = self._orders_from_targets(
                        pending_targets_list,
                        event_date,
                        bars,
                        "open",
                        active_universe=active_universe,
                        working_orders=open_attempt_orders,
                    )
                    all_orders.extend(new_orders)
                    open_attempt_orders.extend(new_orders)
                    pending_targets = None

            if open_attempt_orders:
                working_orders, daily_notional = self._process_orders(
                    open_attempt_orders,
                    event_date,
                    bars,
                    "open",
                    result,
                    peak_equity,
                    day_start,
                    daily_notional,
                    volume_remaining,
                    open_timestamp=open_timestamp,
                    close_timestamp=close_timestamp,
                )

            history = self.feed.history_through(event_date)
            if active_universe is not None:
                history = history.loc[history["ticker"].isin(active_universe)].copy()
            targets = (
                self.strategy.generate_targets(event_date, history)
                if self._should_rebalance(event_date)
                else None
            )
            if targets is not None:
                if self.config.execution_price is ExecutionPrice.SAME_CLOSE:
                    new_orders = self._orders_from_targets(
                        targets,
                        event_date,
                        bars,
                        "close",
                        active_universe=active_universe,
                        working_orders=working_orders,
                    )
                    all_orders.extend(new_orders)
                    same_close_survivors, daily_notional = self._process_orders(
                        new_orders,
                        event_date,
                        bars,
                        "close",
                        result,
                        peak_equity,
                        day_start,
                        daily_notional,
                        volume_remaining,
                        open_timestamp=close_timestamp,
                        close_timestamp=close_timestamp,
                    )
                    working_orders.extend(same_close_survivors)
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
                str(row["ticker"]): self._decimal(row["close"])
                for _, row in bars.iterrows()
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
            (Decimal(str(row["equity"])) for row in result.equity_curve),
            start=Decimal("0"),
        ) / max(len(result.equity_curve), 1)
        result.turnover = (
            float(self.portfolio.traded_notional / average_equity)
            if average_equity
            else 0.0
        )
        result.orders = [self._order_record(order) for order in all_orders]
        result.trades = [
            {
                "fill_id": fill.fill_id,
                "order_id": fill.order_id,
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
