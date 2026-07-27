"""Typed domain records shared by the engine layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class Side(StrEnum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Execution instruction supported by the daily-bar simulator."""

    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(StrEnum):
    """How long an unfilled order remains eligible for execution."""

    DAY = "day"
    GTC = "gtc"


class OrderStatus(StrEnum):
    """Lifecycle state for a simulated order."""

    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_ORDER_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.REJECTED,
    OrderStatus.CANCELLED,
    OrderStatus.EXPIRED,
}


@dataclass(frozen=True)
class Signal:
    """Optional directional signal emitted by a strategy."""

    date: date
    ticker: str
    score: float


@dataclass(frozen=True)
class TargetPosition:
    """Desired non-negative portfolio weight."""

    ticker: str
    weight: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError("Target weight must be between 0 and 1")


@dataclass
class Order:
    """Integer-share order with explicit type, lifetime, and cumulative fills."""

    order_id: str
    created_at: date
    ticker: str
    side: Side
    quantity: int
    reference_price: Decimal
    status: OrderStatus = OrderStatus.PENDING
    rejection_reason: str | None = None
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    filled_quantity: int = 0
    last_attempt_at: date | None = None
    last_attempt_reason: str | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive")
        if self.reference_price <= 0:
            raise ValueError("Order reference price must be positive")
        if not 0 <= self.filled_quantity <= self.quantity:
            raise ValueError("filled_quantity must be between zero and order quantity")
        if self.order_type is OrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0:
                raise ValueError("Limit orders require a positive limit_price")
        elif self.limit_price is not None:
            raise ValueError("Market orders cannot define limit_price")

    @property
    def remaining_quantity(self) -> int:
        """Unfilled shares remaining on the original order."""
        return self.quantity - self.filled_quantity

    @property
    def notional(self) -> Decimal:
        """Reference notional for the currently unfilled quantity."""
        return self.reference_price * self.remaining_quantity

    @property
    def is_open(self) -> bool:
        """Whether the order can still receive another simulated fill."""
        return self.status not in TERMINAL_ORDER_STATUSES and self.remaining_quantity > 0

    def record_attempt(self, event_date: date, reason: str | None = None) -> None:
        """Record one deterministic daily-bar execution attempt."""
        self.last_attempt_at = event_date
        self.last_attempt_reason = reason

    def record_fill(self, quantity: int, event_date: date) -> None:
        """Apply a positive fill quantity and advance lifecycle status."""
        if not self.is_open:
            raise ValueError("Cannot fill a terminal order")
        if quantity <= 0 or quantity > self.remaining_quantity:
            raise ValueError("Fill quantity exceeds the remaining order quantity")
        self.filled_quantity += quantity
        self.last_attempt_at = event_date
        self.last_attempt_reason = None
        self.status = (
            OrderStatus.FILLED
            if self.remaining_quantity == 0
            else OrderStatus.PARTIALLY_FILLED
        )

    def expire(self, event_date: date, reason: str = "day_order_expired") -> None:
        """Expire any unfilled remainder without changing completed fills."""
        if self.is_open:
            self.status = OrderStatus.EXPIRED
            self.last_attempt_at = event_date
            self.last_attempt_reason = reason

    def cancel(self, event_date: date, reason: str = "cancelled") -> None:
        """Cancel an open order and preserve its completed-fill history."""
        if not self.is_open:
            raise ValueError("Only open orders can be cancelled")
        self.status = OrderStatus.CANCELLED
        self.last_attempt_at = event_date
        self.last_attempt_reason = reason


@dataclass(frozen=True)
class Fill:
    """Immutable simulated execution; one order may have multiple fills."""

    order_id: str
    timestamp: datetime
    ticker: str
    side: Side
    quantity: int
    price: Decimal
    commission: Decimal
    tax: Decimal
    slippage: Decimal
    fill_id: str = ""

    @property
    def gross_value(self) -> Decimal:
        """Executed shares times execution price."""
        return self.price * self.quantity
