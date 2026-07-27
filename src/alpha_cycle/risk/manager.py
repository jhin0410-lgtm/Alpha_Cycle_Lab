"""Structured deterministic pre-trade risk decisions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from alpha_cycle.domain.models import Order, Side
from alpha_cycle.portfolio.portfolio import Portfolio


class KillSwitch(Protocol):
    """Extension point for a future operational kill switch."""

    def is_active(self) -> bool:
        """Whether all order activity must stop."""
        ...


@dataclass(frozen=True)
class RiskConfig:
    """Configurable long-only portfolio and liquidity limits."""

    max_positions: int = 100
    max_single_position: float = 0.25
    max_gross_exposure: float = 1.0
    max_daily_turnover: float = 0.40
    max_order_pct_of_trading_value: float = 0.01
    max_order_value: Decimal | None = None
    max_daily_loss: float = 0.05
    max_portfolio_drawdown: float = 0.20


@dataclass(frozen=True)
class RiskDecision:
    """Structured allow/reject result."""

    approved: bool
    code: str
    reason: str


class RiskManager:
    """Pre-trade checks without broker side effects."""

    def __init__(self, config: RiskConfig, kill_switch: KillSwitch | None = None) -> None:
        self.config = config
        self.kill_switch = kill_switch

    def evaluate(
        self,
        order: Order,
        portfolio: Portfolio,
        *,
        trading_value: Decimal,
        daily_order_notional: Decimal,
        peak_equity: Decimal,
        day_start_equity: Decimal,
    ) -> RiskDecision:
        """Evaluate one order against position, exposure, liquidity, and loss limits."""
        if self.kill_switch and self.kill_switch.is_active():
            return RiskDecision(False, "kill_switch", "Kill switch is active")
        equity = portfolio.total_equity
        if equity <= 0:
            return RiskDecision(False, "non_positive_equity", "Portfolio equity is not positive")
        if order.quantity <= 0:
            return RiskDecision(False, "invalid_quantity", "Order quantity must be positive")
        if self.config.max_order_value is not None and order.notional > self.config.max_order_value:
            return RiskDecision(False, "max_order_value", "Order exceeds ticker order-value cap")
        current_position = portfolio.positions.get(order.ticker)
        is_new_position = (
            order.side is Side.BUY
            and (current_position is None or current_position.quantity == 0)
        )
        open_positions = sum(
            position.quantity > 0 for position in portfolio.positions.values()
        )
        if is_new_position and open_positions >= self.config.max_positions:
            return RiskDecision(False, "max_positions", "Maximum position count exceeded")
        if trading_value <= 0 or (
            order.notional / trading_value
            > Decimal(str(self.config.max_order_pct_of_trading_value))
        ):
            return RiskDecision(False, "liquidity", "Order exceeds trading-value participation cap")
        if (
            daily_order_notional + order.notional
        ) / equity > Decimal(str(self.config.max_daily_turnover)):
            return RiskDecision(False, "daily_turnover", "Daily turnover limit exceeded")
        current_value = portfolio.market_value(order.ticker)
        signed = order.notional if order.side is Side.BUY else -order.notional
        resulting_value = max(Decimal("0"), current_value + signed)
        if resulting_value / equity > Decimal(str(self.config.max_single_position)):
            return RiskDecision(False, "single_position", "Single-position limit exceeded")
        gross = sum(
            (portfolio.market_value(ticker) for ticker in portfolio.positions),
            start=Decimal("0"),
        )
        resulting_gross = max(Decimal("0"), gross + signed)
        if resulting_gross / equity > Decimal(str(self.config.max_gross_exposure)):
            return RiskDecision(False, "gross_exposure", "Gross-exposure limit exceeded")
        if day_start_equity > 0 and (
            day_start_equity - equity
        ) / day_start_equity > Decimal(str(self.config.max_daily_loss)):
            return RiskDecision(False, "daily_loss", "Daily loss limit exceeded")
        if peak_equity > 0 and (
            peak_equity - equity
        ) / peak_equity > Decimal(str(self.config.max_portfolio_drawdown)):
            return RiskDecision(False, "drawdown", "Portfolio drawdown limit exceeded")
        return RiskDecision(True, "approved", "All pre-trade checks passed")
