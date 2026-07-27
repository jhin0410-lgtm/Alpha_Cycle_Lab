from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from alpha_cycle.cli import main


def test_cli_writes_stress_audit_outputs(tmp_path: Path) -> None:
    stress_config = tmp_path / "stress.yaml"
    stress_config.write_text(
        """
path_scenarios:
  - name: bear
    recurring_shift_bps: -10
    volatility_multiplier: 1.5
    cost_drag_bps: 2
""".strip(),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    code = main(
        [
            "backtest",
            "--input",
            "data/sample/prices.csv",
            "--strategy",
            "buy_hold",
            "--initial-cash",
            "80000000",
            "--stress-config",
            str(stress_config),
            "--output",
            str(output),
        ]
    )
    assert code == 0
    expected = {
        "equity_curve.csv",
        "positions.csv",
        "orders.csv",
        "fills.csv",
        "trades.csv",
        "corporate_actions.csv",
        "metrics.json",
        "backtest_report.md",
        "stress_scenarios.csv",
        "stress_paths.csv",
        "factor_stress.csv",
        "stress_summary.json",
    }
    assert {path.name for path in output.iterdir()} == expected
    scenarios = pd.read_csv(output / "stress_scenarios.csv")
    assert scenarios["scenario"].tolist() == ["base", "bear"]
    factor_stress = pd.read_csv(output / "factor_stress.csv")
    assert factor_stress.empty
    assert "estimated_period_return" in factor_stress.columns
    summary = json.loads((output / "stress_summary.json").read_text(encoding="utf-8"))
    assert summary["path_scenario_count"] == 1
    assert summary["factor_scenario_count"] == 0
