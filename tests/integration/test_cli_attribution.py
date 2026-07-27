from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_cycle.cli import main


def test_cli_writes_benchmark_and_factor_artifacts(tmp_path: Path) -> None:
    dates = pd.date_range("2024-01-02", periods=25, freq="B")
    prices = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "ticker": "AAA",
            "open": [100 + index for index in range(25)],
            "high": [101 + index for index in range(25)],
            "low": [99 + index for index in range(25)],
            "close": [100.5 + index for index in range(25)],
            "volume": 100000,
            "trading_value": 10000000,
        }
    )
    return_dates = dates[1:]
    benchmark = pd.DataFrame(
        {
            "date": return_dates.strftime("%Y-%m-%d"),
            "benchmark": "KOSPI",
            "return": [0.001 + (index % 3) * 0.0001 for index in range(24)],
        }
    )
    factors = pd.DataFrame(
        {
            "date": return_dates.strftime("%Y-%m-%d"),
            "factor": "market",
            "return": [0.0005 + (index % 5) * 0.0001 for index in range(24)],
        }
    )
    price_path = tmp_path / "prices.csv"
    benchmark_path = tmp_path / "benchmark.csv"
    factor_path = tmp_path / "factors.csv"
    output_path = tmp_path / "outputs"
    prices.to_csv(price_path, index=False)
    benchmark.to_csv(benchmark_path, index=False)
    factors.to_csv(factor_path, index=False)

    exit_code = main(
        [
            "backtest",
            "--input",
            str(price_path),
            "--strategy",
            "buy_hold",
            "--initial-cash",
            "1000000",
            "--benchmark",
            str(benchmark_path),
            "--benchmark-id",
            "KOSPI",
            "--factors",
            str(factor_path),
            "--min-factor-observations",
            "5",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    expected = {
        "equity_curve.csv",
        "positions.csv",
        "orders.csv",
        "fills.csv",
        "trades.csv",
        "corporate_actions.csv",
        "metrics.json",
        "backtest_report.md",
        "benchmark_alignment.csv",
        "attribution_summary.json",
    }
    assert {path.name for path in output_path.iterdir()} == expected
    metrics = json.loads((output_path / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["benchmark_observations"] == 24
    assert metrics["factor_observations"] == 24
    summary = json.loads(
        (output_path / "attribution_summary.json").read_text(encoding="utf-8")
    )
    assert summary["benchmark_id"] == "KOSPI"
    assert summary["factor_attribution"]["observations"] == 24
