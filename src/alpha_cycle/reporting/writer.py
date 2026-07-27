"""Write a complete auditable backtest artifact set."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult

CORPORATE_ACTION_COLUMNS = [
    "effective_date",
    "ticker",
    "action_type",
    "ratio",
    "quantity_before",
    "quantity_after",
    "average_cost_before",
    "average_cost_after",
    "cash_effect",
    "status",
    "reason",
]


def write_outputs(
    output_dir: Path,
    result: BacktestResult,
    metrics: dict[str, Any],
    *,
    strategy_name: str | None = None,
    initial_cash: Decimal | None = None,
) -> list[Path]:
    """Create all documented CSV, JSON, and Markdown outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "equity_curve.csv": pd.DataFrame(result.equity_curve),
        "positions.csv": pd.DataFrame(result.positions),
        "orders.csv": pd.DataFrame(result.orders),
        "fills.csv": pd.DataFrame(
            [
                {
                    **asdict(fill),
                    "timestamp": fill.timestamp.isoformat(),
                    "side": fill.side.value,
                    "price": str(fill.price),
                    "commission": str(fill.commission),
                    "tax": str(fill.tax),
                    "slippage": str(fill.slippage),
                }
                for fill in result.fills
            ]
        ),
        "trades.csv": pd.DataFrame(result.trades),
        "corporate_actions.csv": pd.DataFrame(
            result.corporate_actions,
            columns=CORPORATE_ACTION_COLUMNS,
        ),
    }
    written: list[Path] = []
    for name, frame in files.items():
        path = output_dir / name
        frame.to_csv(path, index=False)
        written.append(path)
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    written.append(metrics_path)
    report_path = output_dir / "backtest_report.md"
    metric_lines = "\n".join(f"- `{key}`: {value:.6f}" for key, value in metrics.items())
    report_path.write_text(
        "# Backtest Report\n\n"
        "Research simulation only; this is not investment advice or a performance claim.\n\n"
        "## Parameters\n\n"
        f"- Strategy: {strategy_name or 'unknown'}\n"
        f"- Initial cash: {initial_cash if initial_cash is not None else 'default'}\n"
        f"- Corporate actions applied: {len(result.corporate_actions)}\n\n"
        "## Metrics\n\n"
        f"{metric_lines}\n",
        encoding="utf-8",
    )
    written.append(report_path)
    return written
