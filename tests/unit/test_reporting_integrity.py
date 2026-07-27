from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult
from alpha_cycle.reporting.writer import CORPORATE_ACTION_COLUMNS, write_outputs


def test_writer_always_creates_corporate_action_audit_file(tmp_path: Path) -> None:
    result = BacktestResult()
    written = write_outputs(
        tmp_path,
        result,
        {"cumulative_return": 0.0},
        strategy_name="fixture",
        initial_cash=Decimal("10000"),
    )

    action_path = tmp_path / "corporate_actions.csv"
    assert action_path in written
    assert len(written) == 8
    frame = pd.read_csv(action_path)
    assert frame.empty
    assert frame.columns.tolist() == CORPORATE_ACTION_COLUMNS
    report = (tmp_path / "backtest_report.md").read_text(encoding="utf-8")
    assert "Corporate actions applied: 0" in report


def test_writer_serializes_corporate_action_values(tmp_path: Path) -> None:
    result = BacktestResult(
        corporate_actions=[
            {
                "effective_date": "2024-01-03",
                "ticker": "AAA",
                "action_type": "split",
                "ratio": "2",
                "quantity_before": 10,
                "quantity_after": 20,
                "average_cost_before": "100",
                "average_cost_after": "50",
                "cash_effect": "0",
                "status": "applied",
                "reason": None,
            }
        ]
    )
    write_outputs(
        tmp_path,
        result,
        {"cumulative_return": 0.0},
    )
    frame = pd.read_csv(tmp_path / "corporate_actions.csv")
    assert frame.loc[0, "ticker"] == "AAA"
    assert frame.loc[0, "quantity_after"] == 20
