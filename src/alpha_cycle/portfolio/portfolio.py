"""Long-only multi-asset portfolio accounting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from alpha_cycle.domain.models import Fill, Side

ZERO = Decimal("0")


@dataclass
class Position:
    """Share quantity and average cost for one ticker."""

    ticker: str
    quantity: int = 0
    average_cost: Decimal = ZERO
    realized_pnl: Decimal = ZERO


class Portfolio:
    """Cash and long-only positions updated exclusively from fills."""

    def __init__(self, initial_cash: Decimal) -> None:
        if initial_cash <= ZERO:
            raise ValueError("Initial cash must be positive")
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, Position] = {}
        self.last_prices: dict[str, Decimal] = {}
        self.total_commission = ZERO
        self.total_tax = ZERO
        self.total_slippage = ZERO
        self.traded_notional = ZERO

    def apply_fill(self, fill: Fill) -> None:
        """Apply a valid fill and maintain weighted average cost and realized P&L."""
        position = self.positions.setdefault(fill.ticker, Position(fill.ticker))
        if fill.side is Side.BUY:
            cash_required = fill.gross_value + fill.commission + fill.tax
            if cash_required > self.cash:
                raise ValueError("Insufficient cash for fill")
            prior_cost = position.average_cost * position.quantity
            position.quantity += fill.quantity
            position.average_cost = (
                prior_cost + fill.gross_value + fill.commission
            ) / position.quantity
            self.cash -= cash_required
        else:
            if fill.quantity > position.quantity:
                raise ValueError("Cannot sell more shares than held")
            proceeds = fill.gross_value - fill.commission - fill.tax
            position.realized_pnl += proceeds - position.average_cost * fill.quantity
            position.quantity -= fill.quantity
            self.cash += proceeds
            if position.quantity == 0:
                position.average_cost = ZERO
        self.total_commission += fill.commission
        self.total_tax += fill.tax
        self.total_slippage += fill.slippage
        self.traded_notional += fill.gross_value
        self.last_prices[fill.ticker] = fill.price

    def mark(self, prices: dict[str, Decimal]) -> None:
        """Update valuation marks without changing accounting cost."""
        self.last_prices.update(prices)

    def market_value(self, ticker: str) -> Decimal:
        """Current marked value of a position."""
        position = self.positions.get(ticker)
        if position is None:
            return ZERO
        return self.last_prices.get(ticker, position.average_cost) * position.quantity

    @property
    def total_equity(self) -> Decimal:
        """Cash plus marked long market value."""
        return self.cash + sum(
            (self.market_value(ticker) for ticker in self.positions), start=ZERO
        )

    @property
    def unrealized_pnl(self) -> Decimal:
        """Marked P&L on open positions."""
        return sum(
            (
                (self.last_prices.get(ticker, position.average_cost) - position.average_cost)
                * position.quantity
                for ticker, position in self.positions.items()
            ),
            start=ZERO,
        )

    @property
    def realized_pnl(self) -> Decimal:
        """Cumulative realized P&L."""
        return sum((p.realized_pnl for p in self.positions.values()), start=ZERO)

    @property
    def cash_weight(self) -> float:
        """Cash as a fraction of total equity."""
        return float(self.cash / self.total_equity) if self.total_equity else 0.0

    def snapshot(self, event_date: date) -> list[dict[str, object]]:
        """Serializable position rows including valuation fields."""
        rows: list[dict[str, object]] = []
        for ticker, position in sorted(self.positions.items()):
            if position.quantity == 0:
                continue
            row: dict[str, object] = asdict(position)
            row.update(
                {
                    "date": event_date.isoformat(),
                    "market_price": str(self.last_prices.get(ticker, position.average_cost)),
                    "market_value": str(self.market_value(ticker)),
                    "unrealized_pnl": str(
                        (
                            self.last_prices.get(ticker, position.average_cost)
                            - position.average_cost
                        )
                        * position.quantity
                    ),
                    "average_cost": str(position.average_cost),
                    "realized_pnl": str(position.realized_pnl),
                }
            )
            rows.append(row)
        return rows

