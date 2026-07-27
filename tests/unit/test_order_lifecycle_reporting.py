from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult
from alpha_cycle.config import load_config
from alpha_cycle.domain.models import Fill, OrderType, Side, TimeInForce
from alpha_cycle.reporting.writer import write_outputs


def test_execution_config_loads_typed_lifecycle_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
backtest:
  initial_cash: 1000000
execution:
  order_type: limit
  time_in_force: gtc
  limit_offset_bps: 125
  max_volume_participation: 0.2
""".strip(),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.backtest.order_type is OrderType.LIMIT
    assert config.backtest.time_in_force is TimeInForce.GTC
    assert config.backtest.limit_offset_bps == Decimal("125")
    assert config.backtest.max_volume_participation == Decimal("0.2")


def test_writer_allows_multiple_fills_per_order_and_keeps_fill_ids_unique(
    tmp_path: Path,
) -> None:
    timestamp = datetime(2024, 1, 2, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    result = BacktestResult(
        orders=[
            {
                "order_id": "O1",
                "created_at": "2024-01-01",
                "ticker": "AAA",
                "side": "buy",
                "quantity": 10,
                "reference_price": "100",
                "status": "filled",
                "rejection_reason": None,
                "order_type": "market",
                "time_in_force": "gtc",
                "limit_price": None,
                "filled_quantity": 10,
                "remaining_quantity": 0,
                "last_attempt_at": "2024-01-03",
                "last_attempt_reason": None,
            }
        ],
        fills=[
            Fill(
                order_id="O1",
                timestamp=timestamp,
                ticker="AAA",
                side=Side.BUY,
                quantity=4,
                price=Decimal("100"),
                commission=Decimal("0"),
                tax=Decimal("0"),
                slippage=Decimal("0"),
                fill_id="F1",
            ),
            Fill(
                order_id="O1",
                timestamp=timestamp,
                ticker="AAA",
                side=Side.BUY,
                quantity=6,
                price=Decimal("100"),
                commission=Decimal("0"),
                tax=Decimal("0"),
                slippage=Decimal("0"),
                fill_id="F2",
            ),
        ],
        trades=[
            {
                "fill_id": "F1",
                "order_id": "O1",
                "date": "2024-01-02",
                "ticker": "AAA",
                "side": "buy",
                "quantity": 4,
                "price": "100",
                "gross_value": "400",
            },
            {
                "fill_id": "F2",
                "order_id": "O1",
                "date": "2024-01-02",
                "ticker": "AAA",
                "side": "buy",
                "quantity": 6,
                "price": "100",
                "gross_value": "600",
            },
        ],
    )
    write_outputs(tmp_path, result, {})
    fills = pd.read_csv(tmp_path / "fills.csv")
    orders = pd.read_csv(tmp_path / "orders.csv")
    assert fills["fill_id"].is_unique
    assert fills["order_id"].tolist() == ["O1", "O1"]
    assert orders.loc[0, "filled_quantity"] == 10
    assert orders.loc[0, "remaining_quantity"] == 0
