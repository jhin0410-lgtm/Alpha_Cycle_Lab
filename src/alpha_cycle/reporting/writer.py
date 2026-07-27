"""Write a complete auditable backtest artifact set."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult


def write_outputs(
    output_dir: Path, result: BacktestResult, metrics: dict[str, Any]
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
    }
    written: list[Path] = []
    for name, frame in files.items():
        path = output_dir / name
        frame.to_csv(path, index=False)
        written.append(path)
    metrics_path = output_dir / "metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    written.append(metrics_path)
    report_path = output_dir / "backtest_report.md"
    metric_lines = "\n".join(f"- `{key}`: {value:.6f}" for key, value in metrics.items())
    report_path.write_text(
        "# Backtest Report\n\n"
        "Research simulation only; this is not investment advice or a performance claim.\n\n"
        "## Metrics\n\n"
        f"{metric_lines}\n",
        encoding="utf-8",
    )
    written.append(report_path)
    return written

