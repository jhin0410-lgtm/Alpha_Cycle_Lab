"""Deterministic post-backtest scenario and factor stress analysis."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


PATH_SUMMARY_COLUMNS = [
    "scenario",
    "observations",
    "cumulative_return",
    "annualized_return",
    "annualized_volatility",
    "maximum_drawdown",
    "worst_period_return",
    "terminal_growth",
    "terminal_loss_vs_base",
]
PATH_COLUMNS = [
    "date",
    "scenario",
    "base_return",
    "stressed_return",
    "growth",
]
FACTOR_STRESS_COLUMNS = [
    "scenario",
    "alpha_component",
    "factor_component",
    "estimated_period_return",
    "estimated_annualized_return",
    "shocks",
    "contributions",
]


def _finite(value: float, label: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


@dataclass(frozen=True)
class PathStressScenario:
    """A transparent transformation of the observed strategy return path."""

    name: str
    recurring_shift_bps: float = 0.0
    volatility_multiplier: float = 1.0
    cost_drag_bps: float = 0.0
    one_time_shock: float = 0.0
    shock_date: date | None = None

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("Scenario name cannot be empty")
        if name.casefold() == "base":
            raise ValueError("Scenario name 'base' is reserved")
        object.__setattr__(self, "name", name)
        shift = _finite(self.recurring_shift_bps, "recurring_shift_bps")
        multiplier = _finite(self.volatility_multiplier, "volatility_multiplier")
        cost = _finite(self.cost_drag_bps, "cost_drag_bps")
        shock = _finite(self.one_time_shock, "one_time_shock")
        if multiplier < 0:
            raise ValueError("volatility_multiplier cannot be negative")
        if cost < 0:
            raise ValueError("cost_drag_bps cannot be negative")
        if shock <= -1:
            raise ValueError("one_time_shock must be greater than -1")
        if shock != 0.0 and self.shock_date is None:
            raise ValueError("shock_date is required when one_time_shock is non-zero")
        if shock == 0.0 and self.shock_date is not None:
            raise ValueError("shock_date requires a non-zero one_time_shock")
        object.__setattr__(self, "recurring_shift_bps", shift)
        object.__setattr__(self, "volatility_multiplier", multiplier)
        object.__setattr__(self, "cost_drag_bps", cost)
        object.__setattr__(self, "one_time_shock", shock)


@dataclass(frozen=True)
class FactorStressScenario:
    """A one-period factor shock applied to previously estimated factor betas."""

    name: str
    shocks: dict[str, float]

    def __post_init__(self) -> None:
        name = self.name.strip()
        if not name:
            raise ValueError("Factor scenario name cannot be empty")
        if not self.shocks:
            raise ValueError("Factor scenario shocks cannot be empty")
        normalized: dict[str, float] = {}
        for factor, shock in self.shocks.items():
            factor_name = str(factor).strip()
            if not factor_name:
                raise ValueError("Factor shock identifiers cannot be empty")
            normalized[factor_name] = _finite(shock, f"shock for {factor_name}")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "shocks", normalized)


@dataclass(frozen=True)
class StressConfig:
    """Validated scenario definitions loaded from YAML or constructed directly."""

    path_scenarios: tuple[PathStressScenario, ...] = ()
    factor_scenarios: tuple[FactorStressScenario, ...] = ()

    def __post_init__(self) -> None:
        names = [scenario.name for scenario in (*self.path_scenarios, *self.factor_scenarios)]
        folded = [name.casefold() for name in names]
        if len(folded) != len(set(folded)):
            raise ValueError("Scenario names must be unique across the stress configuration")
        if not names:
            raise ValueError("Stress configuration must contain at least one scenario")


@dataclass(frozen=True)
class StressTestResult:
    """Complete deterministic stress-test audit output."""

    path_summary: pd.DataFrame
    path_returns: pd.DataFrame
    factor_summary: pd.DataFrame
    breakeven: dict[str, float]


def _parse_date(value: Any, label: str) -> date | None:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {value}") from exc
    return parsed.date()


def _mapping_list(raw: Any, label: str) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{label} must be a YAML list")
    items: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"Each {label} entry must be a YAML mapping")
        items.append(item)
    return items


def load_stress_config(path: str | Path) -> StressConfig:
    """Load deterministic stress definitions from a local YAML file."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"Stress configuration does not exist: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid stress YAML configuration: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Stress configuration root must be a YAML mapping")

    path_scenarios: list[PathStressScenario] = []
    for item in _mapping_list(raw.get("path_scenarios"), "path_scenarios"):
        path_scenarios.append(
            PathStressScenario(
                name=str(item.get("name", "")),
                recurring_shift_bps=float(item.get("recurring_shift_bps", 0.0)),
                volatility_multiplier=float(item.get("volatility_multiplier", 1.0)),
                cost_drag_bps=float(item.get("cost_drag_bps", 0.0)),
                one_time_shock=float(item.get("one_time_shock", 0.0)),
                shock_date=_parse_date(item.get("shock_date"), "shock_date"),
            )
        )

    factor_scenarios: list[FactorStressScenario] = []
    for item in _mapping_list(raw.get("factor_scenarios"), "factor_scenarios"):
        shocks = item.get("shocks")
        if not isinstance(shocks, dict):
            raise ValueError("Factor scenario shocks must be a YAML mapping")
        factor_scenarios.append(
            FactorStressScenario(
                name=str(item.get("name", "")),
                shocks={str(key): float(value) for key, value in shocks.items()},
            )
        )
    return StressConfig(tuple(path_scenarios), tuple(factor_scenarios))


def validate_strategy_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a dated simple-return path without filling missing observations."""
    required = {"date", "strategy_return"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing strategy return columns: {', '.join(missing)}")
    data = frame.loc[:, ["date", "strategy_return"]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="raise").dt.date
    data["strategy_return"] = pd.to_numeric(
        data["strategy_return"], errors="raise"
    ).astype(float)
    if data.isna().any().any():
        raise ValueError("Strategy return values cannot be missing")
    if data["date"].duplicated().any():
        raise ValueError("Strategy return dates must be unique")
    values = data["strategy_return"].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Strategy returns must be finite")
    if (values <= -1.0).any():
        raise ValueError("Strategy simple returns must be greater than -1")
    if data.empty:
        raise ValueError("Stress testing requires at least one return observation")
    return data.sort_values("date", kind="stable").reset_index(drop=True)


def _path_metrics(
    returns: pd.Series,
    *,
    periods_per_year: int,
    base_terminal_growth: float,
) -> dict[str, float | int]:
    values = returns.to_numpy(dtype=float)
    growth = np.cumprod(1.0 + values)
    running_peak = np.maximum.accumulate(np.concatenate(([1.0], growth)))
    drawdowns = 1.0 - np.concatenate(([1.0], growth)) / running_peak
    terminal_growth = float(growth[-1])
    observations = len(values)
    years = observations / periods_per_year
    annualized_return = terminal_growth ** (1.0 / years) - 1.0 if years > 0 else 0.0
    volatility = (
        float(np.std(values, ddof=1)) * math.sqrt(periods_per_year)
        if observations > 1
        else 0.0
    )
    return {
        "observations": observations,
        "cumulative_return": terminal_growth - 1.0,
        "annualized_return": annualized_return,
        "annualized_volatility": volatility,
        "maximum_drawdown": float(np.max(drawdowns)),
        "worst_period_return": float(np.min(values)),
        "terminal_growth": terminal_growth,
        "terminal_loss_vs_base": terminal_growth - base_terminal_growth,
    }


def _apply_path_scenario(
    base: pd.DataFrame,
    scenario: PathStressScenario,
) -> pd.Series:
    base_returns = base["strategy_return"].astype(float)
    mean_return = float(base_returns.mean())
    stressed = (
        mean_return
        + scenario.volatility_multiplier * (base_returns - mean_return)
        + scenario.recurring_shift_bps / 10_000.0
        - scenario.cost_drag_bps / 10_000.0
    )
    if scenario.one_time_shock != 0.0:
        matches = base.index[base["date"] == scenario.shock_date].tolist()
        if not matches:
            raise ValueError(
                f"Scenario {scenario.name} shock_date is not in the strategy return path: "
                f"{scenario.shock_date}"
            )
        index = matches[0]
        stressed.loc[index] = (1.0 + float(stressed.loc[index])) * (
            1.0 + scenario.one_time_shock
        ) - 1.0
    values = stressed.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"Scenario {scenario.name} produced non-finite returns")
    if (values <= -1.0).any():
        raise ValueError(f"Scenario {scenario.name} produced a simple return at or below -1")
    return stressed.astype(float)


def _terminal_growth_with_drag(values: np.ndarray, drag_bps: float) -> float:
    adjusted = 1.0 + values - drag_bps / 10_000.0
    if (adjusted <= 0.0).any():
        return 0.0
    return float(np.prod(adjusted))


def calculate_breakeven(base_returns: pd.Series) -> dict[str, float]:
    """Calculate deterministic one-time and recurring return drags to terminal breakeven."""
    values = base_returns.to_numpy(dtype=float)
    terminal_growth = float(np.prod(1.0 + values))
    one_time_return = 1.0 / terminal_growth - 1.0
    if terminal_growth <= 1.0:
        recurring_drag_bps = 0.0
    else:
        lower = 0.0
        upper = float(np.min(1.0 + values) * 10_000.0 * (1.0 - 1e-12))
        for _ in range(100):
            midpoint = (lower + upper) / 2.0
            if _terminal_growth_with_drag(values, midpoint) > 1.0:
                lower = midpoint
            else:
                upper = midpoint
        recurring_drag_bps = (lower + upper) / 2.0
    return {
        "base_terminal_growth": terminal_growth,
        "one_time_return_to_breakeven": one_time_return,
        "recurring_cost_drag_bps_to_breakeven": recurring_drag_bps,
    }


def _factor_stress_rows(
    scenarios: tuple[FactorStressScenario, ...],
    factor_attribution: dict[str, Any] | None,
    *,
    periods_per_year: int,
) -> list[dict[str, object]]:
    if not scenarios:
        return []
    if factor_attribution is None:
        raise ValueError(
            "Factor stress scenarios require factor attribution from --benchmark and --factors"
        )
    raw_betas = factor_attribution.get("betas")
    if not isinstance(raw_betas, dict):
        raise ValueError("Factor attribution summary does not contain betas")
    betas = {str(key): float(value) for key, value in raw_betas.items()}
    alpha = _finite(float(factor_attribution.get("alpha_periodic", 0.0)), "alpha_periodic")
    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        unknown = sorted(set(scenario.shocks) - set(betas))
        if unknown:
            raise ValueError(
                f"Factor scenario {scenario.name} references unknown factors: {', '.join(unknown)}"
            )
        contributions = {
            factor: betas[factor] * shock
            for factor, shock in sorted(scenario.shocks.items())
        }
        factor_component = float(sum(contributions.values()))
        estimated = alpha + factor_component
        if estimated <= -1.0 or not math.isfinite(estimated):
            raise ValueError(
                f"Factor scenario {scenario.name} produced an invalid simple return: {estimated}"
            )
        annualized = (1.0 + estimated) ** periods_per_year - 1.0
        rows.append(
            {
                "scenario": scenario.name,
                "alpha_component": alpha,
                "factor_component": factor_component,
                "estimated_period_return": estimated,
                "estimated_annualized_return": annualized,
                "shocks": json.dumps(scenario.shocks, sort_keys=True),
                "contributions": json.dumps(contributions, sort_keys=True),
            }
        )
    return rows


def run_stress_tests(
    strategy_returns: pd.DataFrame,
    config: StressConfig,
    *,
    factor_attribution: dict[str, Any] | None = None,
    periods_per_year: int = 252,
) -> StressTestResult:
    """Run path transformations and optional factor shocks with auditable outputs."""
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    base = validate_strategy_returns(strategy_returns)
    base_values = base["strategy_return"].astype(float)
    base_terminal_growth = float(np.prod(1.0 + base_values.to_numpy(dtype=float)))

    summary_rows: list[dict[str, object]] = []
    path_rows: list[dict[str, object]] = []
    scenarios: list[tuple[str, pd.Series]] = [("base", base_values)]
    scenarios.extend(
        (scenario.name, _apply_path_scenario(base, scenario))
        for scenario in config.path_scenarios
    )
    for name, returns in scenarios:
        metrics = _path_metrics(
            returns,
            periods_per_year=periods_per_year,
            base_terminal_growth=base_terminal_growth,
        )
        summary_rows.append({"scenario": name, **metrics})
        growth = (1.0 + returns).cumprod()
        for row_index in range(len(base)):
            path_rows.append(
                {
                    "date": base.loc[row_index, "date"],
                    "scenario": name,
                    "base_return": float(base_values.loc[row_index]),
                    "stressed_return": float(returns.loc[row_index]),
                    "growth": float(growth.loc[row_index]),
                }
            )

    factor_rows = _factor_stress_rows(
        config.factor_scenarios,
        factor_attribution,
        periods_per_year=periods_per_year,
    )
    return StressTestResult(
        path_summary=pd.DataFrame(summary_rows, columns=PATH_SUMMARY_COLUMNS),
        path_returns=pd.DataFrame(path_rows, columns=PATH_COLUMNS),
        factor_summary=pd.DataFrame(factor_rows, columns=FACTOR_STRESS_COLUMNS),
        breakeven=calculate_breakeven(base_values),
    )


def write_stress_outputs(output_dir: str | Path, result: StressTestResult) -> list[Path]:
    """Write stable CSV and JSON stress-test audit artifacts."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "stress_scenarios.csv": result.path_summary,
        "stress_paths.csv": result.path_returns,
        "factor_stress.csv": result.factor_summary,
    }
    written: list[Path] = []
    for name, frame in files.items():
        path = directory / name
        frame.to_csv(path, index=False)
        written.append(path)
    summary_path = directory / "stress_summary.json"
    payload = {
        "breakeven": result.breakeven,
        "path_scenario_count": max(len(result.path_summary) - 1, 0),
        "factor_scenario_count": len(result.factor_summary),
    }
    summary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    written.append(summary_path)
    return written
