"""Small typed YAML configuration loader."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from alpha_cycle.backtest.engine import BacktestConfig, ExecutionPrice
from alpha_cycle.brokers.simulated import CommissionModel, SlippageModel
from alpha_cycle.calendar.sessions import ExplicitTradingCalendar
from alpha_cycle.domain.models import OrderType, TimeInForce
from alpha_cycle.risk.manager import RiskConfig


@dataclass(frozen=True)
class AppConfig:
    """Runtime models derived from YAML."""

    backtest: BacktestConfig
    commission: CommissionModel
    slippage: SlippageModel
    risk: RiskConfig
    calendar: ExplicitTradingCalendar | None = None


def _decimal(value: Any, default: str = "0") -> Decimal:
    return Decimal(str(default if value is None else value))


def _parse_time(value: Any) -> time:
    if not isinstance(value, str) or not value:
        raise ValueError("Time values must be non-empty strings")
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError(f"Invalid time value: {value}") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time value: {value}")
    return time(hour, minute)


def load_config(path: Path | None = None, *, initial_cash: Decimal | None = None) -> AppConfig:
    """Load supported YAML keys with safe research-only defaults."""
    raw: dict[str, Any] = {}
    if path is not None:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML configuration: {exc}") from exc
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError("Configuration root must be a YAML mapping")
        raw = loaded or {}
    backtest = raw.get("backtest", {})
    execution = raw.get("execution", {})
    costs = raw.get("costs", {})
    portfolio = raw.get("portfolio", {})
    risk = raw.get("risk", {})
    calendar_config = raw.get("calendar", {})
    cash = initial_cash or _decimal(backtest.get("initial_cash"), "100000000")
    calendar = None
    if calendar_config:
        try:
            timezone_name = str(calendar_config.get("timezone", "Asia/Seoul"))
            timezone = ZoneInfo(timezone_name)
        except Exception as exc:  # pragma: no cover - defensive user-facing path
            raise ValueError(f"Invalid timezone: {calendar_config.get('timezone')}") from exc
        calendar = ExplicitTradingCalendar(
            name=str(calendar_config.get("name", "CUSTOM")),
            sessions=[],
            timezone=timezone,
            open_time=_parse_time(calendar_config.get("session_open", "09:00")),
            close_time=_parse_time(calendar_config.get("session_close", "15:30")),
        )
    return AppConfig(
        backtest=BacktestConfig(
            initial_cash=cash,
            execution_price=ExecutionPrice(backtest.get("execution_price", "next_open")),
            periods_per_year=int(backtest.get("periods_per_year", 252)),
            risk_free_rate=float(backtest.get("risk_free_rate", 0.0)),
            rebalance_frequency=str(backtest.get("rebalance_frequency", "every_session")),
            rebalance_anchor=str(backtest.get("rebalance_anchor", "first_session")),
            order_type=OrderType(execution.get("order_type", "market")),
            time_in_force=TimeInForce(execution.get("time_in_force", "day")),
            limit_offset_bps=_decimal(execution.get("limit_offset_bps")),
            max_volume_participation=_decimal(
                execution.get("max_volume_participation"),
                "1",
            ),
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
        calendar=calendar,
    )
