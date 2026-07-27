from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from alpha_cycle.scenarios import (
    FactorStressScenario,
    PathStressScenario,
    StressConfig,
    calculate_breakeven,
    load_stress_config,
    run_stress_tests,
    write_stress_outputs,
)


def strategy_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-02", periods=5, freq="D").date,
            "strategy_return": [0.02, -0.01, 0.03, -0.02, 0.01],
        }
    )


def test_neutral_path_scenario_preserves_base_returns() -> None:
    result = run_stress_tests(
        strategy_frame(),
        StressConfig(path_scenarios=(PathStressScenario(name="neutral"),)),
    )
    base = result.path_returns.loc[result.path_returns["scenario"] == "base"]
    neutral = result.path_returns.loc[result.path_returns["scenario"] == "neutral"]
    assert neutral["stressed_return"].tolist() == pytest.approx(
        base["stressed_return"].tolist()
    )
    neutral_summary = result.path_summary.loc[
        result.path_summary["scenario"] == "neutral"
    ].iloc[0]
    assert float(neutral_summary["terminal_loss_vs_base"]) == pytest.approx(0.0)


def test_path_scenario_applies_recurring_cost_volatility_and_one_time_shock() -> None:
    scenario = PathStressScenario(
        name="bear",
        recurring_shift_bps=-5,
        volatility_multiplier=1.5,
        cost_drag_bps=2,
        one_time_shock=-0.10,
        shock_date=date(2024, 1, 4),
    )
    result = run_stress_tests(
        strategy_frame(),
        StressConfig(path_scenarios=(scenario,)),
    )
    stressed = result.path_returns.loc[result.path_returns["scenario"] == "bear"]
    base_mean = strategy_frame()["strategy_return"].mean()
    unshocked = base_mean + 1.5 * (0.03 - base_mean) - 0.0005 - 0.0002
    expected = (1.0 + unshocked) * 0.9 - 1.0
    actual = stressed.loc[stressed["date"] == date(2024, 1, 4), "stressed_return"]
    assert float(actual.iloc[0]) == pytest.approx(expected)


def test_missing_shock_date_and_invalid_simple_return_are_rejected() -> None:
    with pytest.raises(ValueError, match="shock_date is required"):
        PathStressScenario(name="broken", one_time_shock=-0.1)

    scenario = PathStressScenario(
        name="missing-date",
        one_time_shock=-0.2,
        shock_date=date(2030, 1, 1),
    )
    with pytest.raises(ValueError, match="not in the strategy return path"):
        run_stress_tests(
            strategy_frame(),
            StressConfig(path_scenarios=(scenario,)),
        )

    catastrophic = PathStressScenario(
        name="catastrophic",
        recurring_shift_bps=-20_000,
    )
    with pytest.raises(ValueError, match="at or below -1"):
        run_stress_tests(
            strategy_frame(),
            StressConfig(path_scenarios=(catastrophic,)),
        )


def test_breakeven_recurring_drag_reduces_profitable_path_to_one() -> None:
    returns = pd.Series([0.03, 0.02, -0.01, 0.04])
    breakeven = calculate_breakeven(returns)
    drag = breakeven["recurring_cost_drag_bps_to_breakeven"]
    terminal = float(np.prod(1.0 + returns.to_numpy() - drag / 10_000.0))
    assert terminal == pytest.approx(1.0, abs=1e-10)
    expected_one_time = 1.0 / float(np.prod(1.0 + returns.to_numpy())) - 1.0
    assert breakeven["one_time_return_to_breakeven"] == pytest.approx(expected_one_time)


def test_factor_stress_uses_estimated_betas_and_alpha() -> None:
    attribution = {
        "alpha_periodic": 0.001,
        "betas": {"market": 1.2, "value": -0.5},
    }
    config = StressConfig(
        factor_scenarios=(
            FactorStressScenario(
                name="risk-off",
                shocks={"market": -0.10, "value": 0.02},
            ),
        )
    )
    result = run_stress_tests(
        strategy_frame(),
        config,
        factor_attribution=attribution,
    )
    row = result.factor_summary.iloc[0]
    expected = 0.001 + 1.2 * -0.10 + -0.5 * 0.02
    assert float(row["estimated_period_return"]) == pytest.approx(expected)
    assert json.loads(str(row["contributions"])) == pytest.approx(
        {"market": -0.12, "value": -0.01}
    )


def test_factor_stress_requires_attribution_and_known_factors() -> None:
    config = StressConfig(
        factor_scenarios=(FactorStressScenario(name="rates", shocks={"rates": 0.01}),)
    )
    with pytest.raises(ValueError, match="require factor attribution"):
        run_stress_tests(strategy_frame(), config)
    with pytest.raises(ValueError, match="unknown factors"):
        run_stress_tests(
            strategy_frame(),
            config,
            factor_attribution={"alpha_periodic": 0.0, "betas": {"market": 1.0}},
        )


def test_yaml_loader_validates_names_and_writes_stable_outputs(tmp_path: Path) -> None:
    config_path = tmp_path / "stress.yaml"
    config_path.write_text(
        """
path_scenarios:
  - name: bear
    recurring_shift_bps: -10
    volatility_multiplier: 1.25
    cost_drag_bps: 3
factor_scenarios:
  - name: market_crash
    shocks:
      market: -0.08
""".strip(),
        encoding="utf-8",
    )
    config = load_stress_config(config_path)
    result = run_stress_tests(
        strategy_frame(),
        config,
        factor_attribution={"alpha_periodic": 0.0, "betas": {"market": 1.1}},
    )
    files = write_stress_outputs(tmp_path / "outputs", result)
    assert [path.name for path in files] == [
        "stress_scenarios.csv",
        "stress_paths.csv",
        "factor_stress.csv",
        "stress_summary.json",
    ]
    assert list(pd.read_csv(files[0]).columns) == list(result.path_summary.columns)
    assert list(pd.read_csv(files[2]).columns) == list(result.factor_summary.columns)
    payload = json.loads(files[3].read_text(encoding="utf-8"))
    assert payload["path_scenario_count"] == 1
    assert payload["factor_scenario_count"] == 1

    duplicate_path = tmp_path / "duplicate.yaml"
    duplicate_path.write_text(
        """
path_scenarios:
  - name: duplicate
factor_scenarios:
  - name: DUPLICATE
    shocks:
      market: -0.01
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be unique"):
        load_stress_config(duplicate_path)
