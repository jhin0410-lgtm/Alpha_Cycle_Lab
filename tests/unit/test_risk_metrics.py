from datetime import date
from decimal import Decimal

from alpha_cycle.backtest.engine import BacktestResult
from alpha_cycle.domain.models import Order, Side
from alpha_cycle.portfolio.portfolio import Portfolio, Position
from alpha_cycle.reporting.metrics import calculate_metrics
from alpha_cycle.risk.manager import RiskConfig, RiskManager


def test_max_single_position_rejection() -> None:
    portfolio = Portfolio(Decimal("1000"))
    order = Order("o", date(2024, 1, 1), "AAA", Side.BUY, 6, Decimal("100"))
    decision = RiskManager(
        RiskConfig(
            max_single_position=0.5,
            max_gross_exposure=1,
            max_daily_turnover=1,
            max_order_pct_of_trading_value=1,
        )
    ).evaluate(
        order,
        portfolio,
        trading_value=Decimal("10000"),
        daily_order_notional=Decimal("0"),
        peak_equity=Decimal("1000"),
        day_start_equity=Decimal("1000"),
    )
    assert not decision.approved
    assert decision.code == "single_position"


def test_max_position_count_rejection() -> None:
    portfolio = Portfolio(Decimal("1000"))
    portfolio.positions["HELD"] = Position("HELD", 1, Decimal("100"))
    portfolio.mark({"HELD": Decimal("100")})
    order = Order("o", date(2024, 1, 1), "NEW", Side.BUY, 1, Decimal("100"))
    decision = RiskManager(
        RiskConfig(
            max_positions=1,
            max_single_position=1,
            max_gross_exposure=1,
            max_daily_turnover=1,
            max_order_pct_of_trading_value=1,
        )
    ).evaluate(
        order,
        portfolio,
        trading_value=Decimal("10000"),
        daily_order_notional=Decimal("0"),
        peak_equity=Decimal("1000"),
        day_start_equity=Decimal("1000"),
    )
    assert decision.code == "max_positions"


def test_maximum_drawdown_and_no_trade_metrics() -> None:
    portfolio = Portfolio(Decimal("100"))
    result = BacktestResult(
        equity_curve=[
            {"date": "2024-01-01", "equity": "100"},
            {"date": "2024-01-02", "equity": "120"},
            {"date": "2024-01-03", "equity": "90"},
        ]
    )
    metrics = calculate_metrics(result, portfolio)
    assert metrics["maximum_drawdown"] == 0.25
    assert metrics["turnover"] == 0.0
    assert metrics["total_commission"] == 0.0
    empty = calculate_metrics(BacktestResult(), portfolio)
    assert empty["sharpe_ratio"] == 0.0
