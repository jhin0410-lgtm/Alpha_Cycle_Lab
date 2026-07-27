"""Explicitly simulated execution and configurable transaction costs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from alpha_cycle.domain.models import Fill, Order, OrderStatus, Side
from alpha_cycle.portfolio.portfolio import Portfolio

ZERO = Decimal("0")


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
    ) -> Fill | None:
        """Attempt one execution and return a fill or rejection."""


class SimulatedBroker(BrokerAdapter):
    """Deterministic local broker with no network or live-order path."""

    def __init__(
        self,
        commission: CommissionModel | None = None,
        slippage: SlippageModel | None = None,
    ) -> None:
        self.commission = commission or CommissionModel()
        self.slippage = slippage or SlippageModel()

    def execute(
        self,
        order: Order,
        market_price: Decimal,
        event_date: date,
        portfolio: Portfolio,
        *,
        execution_timestamp: datetime | None = None,
    ) -> Fill | None:
        """Fill an order at the supplied event price after local cash/holding checks."""
        execution_price = self.slippage.execution_price(order.side, market_price)
        notional = execution_price * order.quantity
        commission, tax = self.commission.calculate(order.side, notional)
        if order.side is Side.BUY and notional + commission + tax > portfolio.cash:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "insufficient_cash"
            return None
        position = portfolio.positions.get(order.ticker)
        held = position.quantity if position else 0
        if order.side is Side.SELL and order.quantity > held:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "insufficient_position"
            return None
        raw_slippage = abs(execution_price - market_price) * order.quantity
        timestamp = execution_timestamp
        if timestamp is None:
            timestamp = datetime.combine(event_date, time(9, 0), tzinfo=None)
            if timestamp.tzinfo is None:
                timestamp = datetime.combine(event_date, time(9, 0), tzinfo=None)
        fill = Fill(
            order_id=order.order_id,
            timestamp=timestamp,
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            price=execution_price,
            commission=commission,
            tax=tax,
            slippage=raw_slippage,
        )
        portfolio.apply_fill(fill)
        order.status = OrderStatus.FILLED
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
    ) -> Fill | None:
        """Reject because live trading is outside this project version."""
        raise RuntimeError("Live KIS order execution is intentionally disabled")
