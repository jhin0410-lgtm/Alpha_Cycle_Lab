from __future__ import annotations

import json
from decimal import Decimal

import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult
from alpha_cycle.reporting.attribution import AlignmentPolicy, AttributionResult
from alpha_cycle.reporting.writer import write_outputs


def test_writer_adds_attribution_outputs_without_changing_base_artifacts(tmp_path) -> None:
    result = BacktestResult(
        equity_curve=[
            {"date": "2024-01-02", "equity": "100"},
            {"date": "2024-01-03", "equity": "101"},
        ]
    )
    aligned = pd.DataFrame(
        [
            {
                "date": "2024-01-03",
                "strategy_return": 0.01,
                "benchmark_return": 0.005,
                "active_return": 0.005,
                "strategy_growth": 1.01,
                "benchmark_growth": 1.005,
                "relative_growth": 1.004975124,
            }
        ]
    )
    attribution = AttributionResult(
        benchmark_id="KOSPI",
        alignment_policy=AlignmentPolicy.STRICT,
        aligned_returns=aligned,
        benchmark_metrics={"benchmark_observations": 1},
        factor_attribution=None,
    )
    written = write_outputs(
        tmp_path,
        result,
        {"cumulative_return": 0.01},
        strategy_name="buy_hold",
        initial_cash=Decimal("100"),
        attribution=attribution,
    )
    names = {path.name for path in written}
    assert "benchmark_alignment.csv" in names
    assert "attribution_summary.json" in names
    assert "equity_curve.csv" in names
    payload = json.loads((tmp_path / "attribution_summary.json").read_text(encoding="utf-8"))
    assert payload["benchmark_id"] == "KOSPI"
    assert payload["alignment_policy"] == "strict"
    report = (tmp_path / "backtest_report.md").read_text(encoding="utf-8")
    assert "Benchmark and Factor Attribution" in report
