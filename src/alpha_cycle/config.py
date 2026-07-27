"""Small typed YAML configuration loader."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from alpha_cycle.backtest.engine import BacktestConfig, ExecutionPrice
from alpha_cycle.brokers.simulated import CommissionModel, SlippageModel
from alpha_cycle.risk.manager import RiskConfig


@dataclass(frozen=True)
class AppConfig:
    """Runtime models derived from YAML."""

    backtest: BacktestConfig
    commission: CommissionModel
    slippage: SlippageModel
    risk: RiskConfig


def _decimal(value: Any, default: str = "0") -> Decimal:
    return Decimal(str(default if value is None else value))


def load_config(path: Path | None = None, *, initial_cash: Decimal | None = None) -> AppConfig:
    """Load supported YAML keys with safe research-only defaults."""
    raw: dict[str, Any] = {}
    if path is not None:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError("Configuration root must be a YAML mapping")
        raw = loaded or {}
    backtest = raw.get("backtest", {})
    costs = raw.get("costs", {})
    portfolio = raw.get("portfolio", {})
    risk = raw.get("risk", {})
    cash = initial_cash or _decimal(backtest.get("initial_cash"), "100000000")
    return AppConfig(
        backtest=BacktestConfig(
            initial_cash=cash,
            execution_price=ExecutionPrice(backtest.get("execution_price", "next_open")),
            periods_per_year=int(backtest.get("periods_per_year", 252)),
            risk_free_rate=float(backtest.get("risk_free_rate", 0.0)),
        ),
        commission=CommissionModel(
            buy_rate=_decimal(costs.get("buy_commission_rate")),
            sell_rate=_decimal(costs.get("sell_commission_rate")),
            sell_tax_rate=_decimal(costs.get("sell_tax_rate")),
        ),
        slippage=SlippageModel(
            bps=_decimal(costs.get("slippage_bps")),
            fixed_per_share=_decimal(costs.get("fixed_slippage")),
        ),
        risk=RiskConfig(
            max_positions=int(portfolio.get("max_positions", 100)),
            max_single_position=float(
                portfolio.get("max_single_position", risk.get("max_single_position", 1.0))
            ),
            max_gross_exposure=float(portfolio.get("max_gross_exposure", 1.0)),
            max_daily_turnover=float(risk.get("max_daily_turnover", 1.0)),
            max_order_pct_of_trading_value=float(
                risk.get("max_order_pct_of_trading_value", 1.0)
            ),
            max_order_value=(
                _decimal(risk["max_order_value"])
                if risk.get("max_order_value") is not None
                else None
            ),
            max_daily_loss=float(risk.get("max_daily_loss", 1.0)),
            max_portfolio_drawdown=float(risk.get("max_portfolio_drawdown", 1.0)),
        ),
    )
