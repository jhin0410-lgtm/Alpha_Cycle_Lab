from datetime import UTC, date
from decimal import Decimal

from alpha_cycle.brokers.simulated import CommissionModel, SimulatedBroker, SlippageModel
from alpha_cycle.domain.models import Fill, Order, OrderStatus, Side
from alpha_cycle.portfolio.portfolio import Portfolio


def make_fill(side: Side, quantity: int, price: str) -> Fill:
    from datetime import datetime

    return Fill(
        "x",
        datetime(2024, 1, 1, tzinfo=UTC),
        "AAA",
        side,
        quantity,
        Decimal(price),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )


def test_average_cost_and_realized_unrealized_pnl() -> None:
    portfolio = Portfolio(Decimal("10000"))
    portfolio.apply_fill(make_fill(Side.BUY, 10, "100"))
    portfolio.apply_fill(make_fill(Side.BUY, 10, "120"))
    assert portfolio.positions["AAA"].average_cost == Decimal("110")
    portfolio.apply_fill(make_fill(Side.SELL, 5, "130"))
    portfolio.mark({"AAA": Decimal("125")})
    assert portfolio.realized_pnl == Decimal("100")
    assert portfolio.unrealized_pnl == Decimal("225")


def test_commission_tax_and_slippage() -> None:
    costs = CommissionModel(
        buy_rate=Decimal("0.001"),
        sell_rate=Decimal("0.002"),
        sell_tax_rate=Decimal("0.003"),
    )
    assert costs.calculate(Side.SELL, Decimal("1000")) == (Decimal("2"), Decimal("3"))
    model = SlippageModel(bps=Decimal("10"), fixed_per_share=Decimal("0.5"))
    assert model.execution_price(Side.BUY, Decimal("100")) == Decimal("100.6")
    assert model.execution_price(Side.SELL, Decimal("100")) == Decimal("99.4")


def test_broker_blocks_order_larger_than_cash() -> None:
    portfolio = Portfolio(Decimal("100"))
    order = Order("o", date(2024, 1, 1), "AAA", Side.BUY, 2, Decimal("100"))
    fill = SimulatedBroker().execute(order, Decimal("100"), date(2024, 1, 1), portfolio)
    assert fill is None
    assert order.status is OrderStatus.REJECTED
    assert order.rejection_reason == "insufficient_cash"
