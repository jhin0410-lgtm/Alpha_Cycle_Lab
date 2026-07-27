"""Explicitly simulated execution and configurable transaction costs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_FLOOR, Decimal
from zoneinfo import ZoneInfo

from alpha_cycle.domain.models import Fill, Order, OrderStatus, OrderType, Side
from alpha_cycle.portfolio.portfolio import Portfolio

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class CommissionModel:
    """Side-specific commissions and sell tax, expressed as decimal rates."""

    buy_rate: Decimal = ZERO
    sell_rate: Decimal = ZERO
    sell_tax_rate: Decimal = ZERO

    def calculate(self, side: Side, notional: Decimal) -> tuple[Decimal, Decimal]:
        """Return commission and tax for an execution."""
        rate = self.buy_rate if side is Side.BUY else self.sell_rate
        commission = notional * rate
        tax = notional * self.sell_tax_rate if side is Side.SELL else ZERO
        return commission, tax


@dataclass(frozen=True)
class SlippageModel:
    """Fixed per-share plus basis-point adverse price movement."""

    bps: Decimal = ZERO
    fixed_per_share: Decimal = ZERO

    def execution_price(self, side: Side, market_price: Decimal) -> Decimal:
        """Return adverse simulated execution price."""
        proportional = market_price * self.bps / Decimal("10000")
        impact = proportional + self.fixed_per_share
        return market_price + impact if side is Side.BUY else market_price - impact


class BrokerAdapter(ABC):
    """Broker interface; live order capability is intentionally absent."""

    live_trading_enabled: bool = False

    @abstractmethod
    def execute(
        self,
        order: Order,
        market_price: Decimal,
        event_date: date,
        portfolio: Portfolio,
        *,
        execution_timestamp: datetime | None = None,
        high_price: Decimal | None = None,
        low_price: Decimal | None = None,
        available_quantity: int | None = None,
        is_halted: bool = False,
    ) -> Fill | None:
        """Attempt one execution and return at most one deterministic fill."""


class SimulatedBroker(BrokerAdapter):
    """Deterministic daily-bar broker with no network or live-order path."""

    def __init__(
        self,
        commission: CommissionModel | None = None,
        slippage: SlippageModel | None = None,
        *,
        max_volume_participation: Decimal = ONE,
    ) -> None:
        if max_volume_participation <= ZERO or max_volume_participation > ONE:
            raise ValueError("max_volume_participation must be greater than 0 and at most 1")
        self.commission = commission or CommissionModel()
        self.slippage = slippage or SlippageModel()
        self.max_volume_participation = max_volume_participation
        self._fill_sequence = 0

    def volume_capacity(self, volume: object) -> int:
        """Maximum shares this broker may fill from one daily bar."""
        numeric = Decimal(str(volume))
        if numeric < ZERO:
            raise ValueError("Daily volume cannot be negative")
        return int(
            (numeric * self.max_volume_participation).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )

    def _next_fill_id(self) -> str:
        self._fill_sequence += 1
        return f"F{self._fill_sequence:08d}"

    @staticmethod
    def _limit_base_price(
        order: Order,
        market_price: Decimal,
        *,
        high_price: Decimal | None,
        low_price: Decimal | None,
    ) -> Decimal | None:
        if order.order_type is OrderType.MARKET:
            return market_price
        limit_price = order.limit_price
        if limit_price is None:  # defensive; Order validates this on construction
            raise ValueError("Limit order is missing limit_price")
        if order.side is Side.BUY:
            if low_price is None or low_price > limit_price:
                return None
            return min(market_price, limit_price)
        if high_price is None or high_price < limit_price:
            return None
        return max(market_price, limit_price)

    def _affordable_buy_quantity(
        self,
        execution_price: Decimal,
        cash: Decimal,
    ) -> int:
        per_share_cash = execution_price * (ONE + self.commission.buy_rate)
        if per_share_cash <= ZERO:
            return 0
        return int((cash / per_share_cash).to_integral_value(rounding=ROUND_FLOOR))

    def execute(
        self,
        order: Order,
        market_price: Decimal,
        event_date: date,
        portfolio: Portfolio,
        *,
        execution_timestamp: datetime | None = None,
        high_price: Decimal | None = None,
        low_price: Decimal | None = None,
        available_quantity: int | None = None,
        is_halted: bool = False,
    ) -> Fill | None:
        """Attempt one market or limit fill while preserving unfilled quantity."""
        if not order.is_open:
            return None
        if is_halted:
            order.record_attempt(event_date, "trading_halted")
            return None
        base_price = self._limit_base_price(
            order,
            market_price,
            high_price=high_price,
            low_price=low_price,
        )
        if base_price is None:
            order.record_attempt(event_date, "limit_not_reached")
            return None
        execution_price = self.slippage.execution_price(order.side, base_price)
        quantity = order.remaining_quantity
        if available_quantity is not None:
            quantity = min(quantity, max(available_quantity, 0))
        if quantity <= 0:
            order.record_attempt(event_date, "volume_cap")
            return None

        if order.side is Side.BUY:
            quantity = min(
                quantity,
                self._affordable_buy_quantity(execution_price, portfolio.cash),
            )
            if quantity <= 0:
                order.record_attempt(event_date, "insufficient_cash")
                if order.filled_quantity == 0:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = "insufficient_cash"
                return None
        else:
            position = portfolio.positions.get(order.ticker)
            held = position.quantity if position else 0
            quantity = min(quantity, held)
            if quantity <= 0:
                order.record_attempt(event_date, "insufficient_position")
                if order.filled_quantity == 0:
                    order.status = OrderStatus.REJECTED
                    order.rejection_reason = "insufficient_position"
                return None

        notional = execution_price * quantity
        commission, tax = self.commission.calculate(order.side, notional)
        raw_slippage = abs(execution_price - base_price) * quantity
        timestamp = execution_timestamp or datetime.combine(
            event_date,
            time(9, 0),
            tzinfo=ZoneInfo("Asia/Seoul"),
        )
        fill = Fill(
            order_id=order.order_id,
            timestamp=timestamp,
            ticker=order.ticker,
            side=order.side,
            quantity=quantity,
            price=execution_price,
            commission=commission,
            tax=tax,
            slippage=raw_slippage,
            fill_id=self._next_fill_id(),
        )
        portfolio.apply_fill(fill)
        order.record_fill(quantity, event_date)
        return fill


class KISBrokerAdapter(BrokerAdapter):
    """Safety stub documenting a future adapter; every order is disabled."""

    live_trading_enabled = False

    def execute(
        self,
        order: Order,
        market_price: Decimal,
        event_date: date,
        portfolio: Portfolio,
        *,
        execution_timestamp: datetime | None = None,
        high_price: Decimal | None = None,
        low_price: Decimal | None = None,
        available_quantity: int | None = None,
        is_halted: bool = False,
    ) -> Fill | None:
        """Reject because live trading is outside this project version."""
        raise RuntimeError("Live KIS order execution is intentionally disabled")
