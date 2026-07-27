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


class OrderStatus(StrEnum):
    """Lifecycle state for a simulated order."""

    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"


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
    """Integer-share order produced by the portfolio/order layer."""

    order_id: str
    created_at: date
    ticker: str
    side: Side
    quantity: int
    reference_price: Decimal
    status: OrderStatus = OrderStatus.PENDING
    rejection_reason: str | None = None

    @property
    def notional(self) -> Decimal:
        """Reference notional before costs."""
        return self.reference_price * self.quantity


@dataclass(frozen=True)
class Fill:
    """Immutable simulated execution."""

    order_id: str
    timestamp: datetime
    ticker: str
    side: Side
    quantity: int
    price: Decimal
    commission: Decimal
    tax: Decimal
    slippage: Decimal

    @property
    def gross_value(self) -> Decimal:
        """Executed shares times execution price."""
        return self.price * self.quantity

