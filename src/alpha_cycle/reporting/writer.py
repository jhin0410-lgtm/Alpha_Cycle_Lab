"""Write a complete auditable backtest artifact set."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult
from alpha_cycle.reporting.attribution import AttributionResult

ORDER_COLUMNS = [
    "order_id",
    "created_at",
    "ticker",
    "side",
    "quantity",
    "reference_price",
    "status",
    "rejection_reason",
    "order_type",
    "time_in_force",
    "limit_price",
    "filled_quantity",
    "remaining_quantity",
    "last_attempt_at",
    "last_attempt_reason",
]
FILL_COLUMNS = [
    "fill_id",
    "order_id",
    "timestamp",
    "ticker",
    "side",
    "quantity",
    "price",
    "commission",
    "tax",
    "slippage",
]
TRADE_COLUMNS = [
    "fill_id",
    "order_id",
    "date",
    "ticker",
    "side",
    "quantity",
    "price",
    "gross_value",
]
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


def _attribution_payload(attribution: AttributionResult) -> dict[str, Any]:
    return {
        "benchmark_id": attribution.benchmark_id,
        "alignment_policy": attribution.alignment_policy.value,
        "benchmark_metrics": attribution.benchmark_metrics,
        "factor_attribution": attribution.factor_attribution,
    }


def write_outputs(
    output_dir: Path,
    result: BacktestResult,
    metrics: dict[str, Any],
    *,
    strategy_name: str | None = None,
    initial_cash: Decimal | None = None,
    attribution: AttributionResult | None = None,
) -> list[Path]:
    """Create all documented CSV, JSON, and Markdown outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fill_rows = [
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
    files = {
        "equity_curve.csv": pd.DataFrame(result.equity_curve),
        "positions.csv": pd.DataFrame(result.positions),
        "orders.csv": pd.DataFrame(result.orders, columns=ORDER_COLUMNS),
        "fills.csv": pd.DataFrame(fill_rows, columns=FILL_COLUMNS),
        "trades.csv": pd.DataFrame(result.trades, columns=TRADE_COLUMNS),
        "corporate_actions.csv": pd.DataFrame(
            result.corporate_actions,
            columns=CORPORATE_ACTION_COLUMNS,
        ),
    }
    if attribution is not None:
        files["benchmark_alignment.csv"] = attribution.aligned_returns.copy()

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

    attribution_lines = ""
    if attribution is not None:
        attribution_path = output_dir / "attribution_summary.json"
        attribution_path.write_text(
            json.dumps(
                _attribution_payload(attribution),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        written.append(attribution_path)
        attribution_lines = (
            "\n## Benchmark and Factor Attribution\n\n"
            f"- Benchmark: {attribution.benchmark_id}\n"
            f"- Alignment policy: {attribution.alignment_policy.value}\n"
            f"- Aligned observations: {len(attribution.aligned_returns)}\n"
            f"- Factor model: {'enabled' if attribution.factor_attribution else 'not provided'}\n"
        )

    report_path = output_dir / "backtest_report.md"
    metric_lines = "\n".join(f"- `{key}`: {float(value):.6f}" for key, value in metrics.items())
    report_path.write_text(
        "# Backtest Report\n\n"
        "Research simulation only; this is not investment advice or a performance claim.\n\n"
        "## Parameters\n\n"
        f"- Strategy: {strategy_name or 'unknown'}\n"
        f"- Initial cash: {initial_cash if initial_cash is not None else 'default'}\n"
        f"- Orders: {len(result.orders)}\n"
        f"- Fills: {len(result.fills)}\n"
        f"- Corporate actions applied: {len(result.corporate_actions)}\n\n"
        "## Metrics\n\n"
        f"{metric_lines}\n"
        f"{attribution_lines}",
        encoding="utf-8",
    )
    written.append(report_path)
    return written
