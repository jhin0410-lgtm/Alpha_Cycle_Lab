"""Deterministic benchmark alignment and linear factor attribution."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from alpha_cycle.backtest.engine import BacktestResult


class AlignmentPolicy(StrEnum):
    """How missing benchmark or factor dates are handled."""

    STRICT = "strict"
    INNER = "inner"


BENCHMARK_COLUMNS = ("date", "benchmark", "return")
FACTOR_COLUMNS = ("date", "factor", "return")


@dataclass(frozen=True)
class AttributionResult:
    """Aligned return path plus benchmark and optional factor summaries."""

    benchmark_id: str
    alignment_policy: AlignmentPolicy
    aligned_returns: pd.DataFrame
    benchmark_metrics: dict[str, float | int]
    factor_attribution: dict[str, Any] | None = None


def _validate_return_frame(
    frame: pd.DataFrame,
    *,
    required: tuple[str, ...],
    identifier: str,
    label: str,
) -> pd.DataFrame:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing {label} columns: {', '.join(missing)}")
    data = frame.loc[:, list(required)].copy()
    data["date"] = pd.to_datetime(data["date"], errors="raise").dt.date
    if data[list(required)].isna().any().any():
        raise ValueError(f"{label} required values cannot be missing")
    data[identifier] = data[identifier].astype(str).str.strip()
    if data[identifier].eq("").any():
        raise ValueError(f"{label} identifiers cannot be empty")
    data["return"] = pd.to_numeric(data["return"], errors="raise").astype(float)
    if not np.isfinite(data["return"].to_numpy()).all():
        raise ValueError(f"{label} returns must be finite")
    duplicate = data.duplicated(["date", identifier], keep=False)
    if duplicate.any():
        raise ValueError(f"Duplicate {label} date and identifier rows are not allowed")
    return data.sort_values(["date", identifier], kind="stable").reset_index(drop=True)


def validate_benchmark_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate simple benchmark returns without filling missing sessions."""
    data = _validate_return_frame(
        frame,
        required=BENCHMARK_COLUMNS,
        identifier="benchmark",
        label="benchmark",
    )
    if (data["return"] < -1.0).any():
        raise ValueError("Benchmark simple returns cannot be below -1")
    return data


def validate_factor_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate long-form factor returns."""
    return _validate_return_frame(
        frame,
        required=FACTOR_COLUMNS,
        identifier="factor",
        label="factor",
    )


class CsvBenchmarkReturnsAdapter:
    """Load a local benchmark return CSV; no network access is performed."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> pd.DataFrame:
        if not self.path.is_file():
            raise ValueError(f"Benchmark CSV does not exist: {self.path}")
        return validate_benchmark_returns(pd.read_csv(self.path))


class CsvFactorReturnsAdapter:
    """Load a local factor return CSV; no network access is performed."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> pd.DataFrame:
        if not self.path.is_file():
            raise ValueError(f"Factor CSV does not exist: {self.path}")
        return validate_factor_returns(pd.read_csv(self.path))


def strategy_returns_from_result(result: BacktestResult) -> pd.DataFrame:
    """Convert the equity audit trail into dated simple returns."""
    if len(result.equity_curve) < 2:
        return pd.DataFrame(columns=["date", "strategy_return"])
    frame = pd.DataFrame(result.equity_curve, columns=["date", "equity"])
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date
    frame["equity"] = pd.to_numeric(frame["equity"], errors="raise").astype(float)
    if not np.isfinite(frame["equity"].to_numpy()).all() or (frame["equity"] <= 0).any():
        raise ValueError("Equity curve values must be positive and finite for attribution")
    if frame["date"].duplicated().any():
        raise ValueError("Equity curve dates must be unique for attribution")
    frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
    returns = frame["equity"].pct_change().iloc[1:]
    return pd.DataFrame(
        {
            "date": frame["date"].iloc[1:].tolist(),
            "strategy_return": returns.astype(float).tolist(),
        }
    )


def _select_benchmark(frame: pd.DataFrame, benchmark_id: str | None) -> tuple[str, pd.DataFrame]:
    identifiers = tuple(sorted(frame["benchmark"].unique().tolist()))
    if not identifiers:
        raise ValueError("Benchmark data is empty")
    if benchmark_id is None:
        if len(identifiers) != 1:
            raise ValueError("--benchmark-id is required when the CSV contains multiple benchmarks")
        selected_id = identifiers[0]
    else:
        selected_id = benchmark_id.strip()
        if selected_id not in identifiers:
            raise ValueError(f"Benchmark not found: {selected_id}")
    selected = frame.loc[frame["benchmark"] == selected_id, ["date", "return"]].rename(
        columns={"return": "benchmark_return"}
    )
    return selected_id, selected.reset_index(drop=True)


def align_returns(
    strategy_returns: pd.DataFrame,
    benchmark_returns: pd.DataFrame,
    *,
    benchmark_id: str | None = None,
    factor_returns: pd.DataFrame | None = None,
    policy: AlignmentPolicy = AlignmentPolicy.STRICT,
) -> tuple[str, pd.DataFrame]:
    """Align strategy, benchmark, and factor returns without forward filling."""
    if strategy_returns.empty:
        raise ValueError("Attribution requires at least one strategy return observation")
    strategy = strategy_returns.loc[:, ["date", "strategy_return"]].copy()
    strategy["date"] = pd.to_datetime(strategy["date"], errors="raise").dt.date
    strategy["strategy_return"] = pd.to_numeric(
        strategy["strategy_return"], errors="raise"
    ).astype(float)
    if strategy["date"].duplicated().any():
        raise ValueError("Strategy return dates must be unique")
    if not np.isfinite(strategy["strategy_return"].to_numpy()).all():
        raise ValueError("Strategy returns must be finite")

    selected_id, selected_benchmark = _select_benchmark(
        validate_benchmark_returns(benchmark_returns), benchmark_id
    )
    aligned = strategy.merge(selected_benchmark, on="date", how="left", validate="one_to_one")

    factor_columns: list[str] = []
    if factor_returns is not None:
        validated_factors = validate_factor_returns(factor_returns)
        pivoted = validated_factors.pivot(index="date", columns="factor", values="return")
        pivoted = pivoted.sort_index().sort_index(axis=1)
        factor_columns = [f"factor__{name}" for name in pivoted.columns]
        pivoted.columns = factor_columns
        aligned = aligned.merge(
            pivoted.reset_index(),
            on="date",
            how="left",
            validate="one_to_one",
        )

    required_columns = ["benchmark_return", *factor_columns]
    missing_mask = aligned[required_columns].isna().any(axis=1)
    if policy is AlignmentPolicy.STRICT and missing_mask.any():
        missing_dates = ", ".join(str(value) for value in aligned.loc[missing_mask, "date"].tolist())
        raise ValueError(f"Missing benchmark or factor returns for strategy dates: {missing_dates}")
    if policy is AlignmentPolicy.INNER:
        aligned = aligned.loc[~missing_mask].copy()
    if aligned.empty:
        raise ValueError("No aligned observations remain after applying alignment policy")

    aligned["active_return"] = aligned["strategy_return"] - aligned["benchmark_return"]
    aligned["strategy_growth"] = (1.0 + aligned["strategy_return"]).cumprod()
    aligned["benchmark_growth"] = (1.0 + aligned["benchmark_return"]).cumprod()
    aligned["relative_growth"] = aligned["strategy_growth"] / aligned["benchmark_growth"]
    return selected_id, aligned.reset_index(drop=True)


def _cumulative(values: pd.Series) -> float:
    return float(np.prod(1.0 + values.to_numpy(dtype=float)) - 1.0)


def _annualize(cumulative_return: float, observations: int, periods_per_year: int) -> float:
    if observations <= 0 or cumulative_return <= -1.0:
        return 0.0
    years = observations / periods_per_year
    return (1.0 + cumulative_return) ** (1.0 / years) - 1.0 if years > 0 else 0.0


def calculate_benchmark_metrics(
    aligned: pd.DataFrame,
    *,
    periods_per_year: int = 252,
) -> dict[str, float | int]:
    """Calculate relative performance metrics from already aligned returns."""
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    strategy = aligned["strategy_return"].astype(float)
    benchmark = aligned["benchmark_return"].astype(float)
    active = strategy - benchmark
    observations = len(aligned)
    strategy_cumulative = _cumulative(strategy)
    benchmark_cumulative = _cumulative(benchmark)
    tracking_error = (
        float(active.std(ddof=1)) * math.sqrt(periods_per_year) if observations > 1 else 0.0
    )
    active_std = float(active.std(ddof=1)) if observations > 1 else 0.0
    information_ratio = (
        float(active.mean()) / active_std * math.sqrt(periods_per_year)
        if active_std != 0.0
        else 0.0
    )
    benchmark_variance = float(benchmark.var(ddof=1)) if observations > 1 else 0.0
    beta = (
        float(strategy.cov(benchmark)) / benchmark_variance
        if benchmark_variance != 0.0
        else 0.0
    )
    correlation = (
        float(strategy.corr(benchmark))
        if observations > 1 and float(strategy.std(ddof=1)) != 0.0 and benchmark_variance != 0.0
        else 0.0
    )
    return {
        "benchmark_observations": observations,
        "benchmark_cumulative_return": benchmark_cumulative,
        "benchmark_annualized_return": _annualize(
            benchmark_cumulative, observations, periods_per_year
        ),
        "benchmark_excess_return": strategy_cumulative - benchmark_cumulative,
        "tracking_error": tracking_error,
        "information_ratio": information_ratio,
        "benchmark_beta": beta,
        "benchmark_correlation": correlation,
    }


def calculate_factor_attribution(
    aligned: pd.DataFrame,
    *,
    periods_per_year: int = 252,
    minimum_observations: int = 20,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Estimate an intercept and factor betas with deterministic ordinary least squares."""
    factor_columns = sorted(column for column in aligned.columns if column.startswith("factor__"))
    if not factor_columns:
        raise ValueError("Factor attribution requires at least one factor series")
    observations = len(aligned)
    required_observations = max(minimum_observations, len(factor_columns) + 2)
    if observations < required_observations:
        raise ValueError(
            f"Factor attribution requires at least {required_observations} aligned observations"
        )
    x_factors = aligned[factor_columns].to_numpy(dtype=float)
    y = aligned["strategy_return"].to_numpy(dtype=float)
    design = np.column_stack([np.ones(observations), x_factors])
    coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank < design.shape[1]:
        raise ValueError("Factor design matrix is rank deficient")
    modeled = design @ coefficients
    residual = y - modeled
    total_sum_squares = float(np.sum((y - float(np.mean(y))) ** 2))
    residual_sum_squares = float(np.sum(residual**2))
    r_squared = 1.0 - residual_sum_squares / total_sum_squares if total_sum_squares else 0.0
    residual_volatility = (
        float(np.std(residual, ddof=1)) * math.sqrt(periods_per_year)
        if observations > 1
        else 0.0
    )
    betas = {
        column.removeprefix("factor__"): float(value)
        for column, value in zip(factor_columns, coefficients[1:], strict=True)
    }
    annualized_contributions = {
        column.removeprefix("factor__"): float(beta * aligned[column].mean() * periods_per_year)
        for column, beta in zip(factor_columns, coefficients[1:], strict=True)
    }
    augmented = aligned.copy()
    augmented["modeled_return"] = modeled
    augmented["residual_return"] = residual
    summary: dict[str, Any] = {
        "observations": observations,
        "alpha_periodic": float(coefficients[0]),
        "alpha_annualized": float(coefficients[0] * periods_per_year),
        "r_squared": r_squared,
        "residual_volatility": residual_volatility,
        "betas": betas,
        "annualized_factor_contributions": annualized_contributions,
    }
    return summary, augmented


def analyze_attribution(
    result: BacktestResult,
    benchmark_returns: pd.DataFrame,
    *,
    benchmark_id: str | None = None,
    factor_returns: pd.DataFrame | None = None,
    alignment_policy: AlignmentPolicy = AlignmentPolicy.STRICT,
    periods_per_year: int = 252,
    minimum_factor_observations: int = 20,
) -> AttributionResult:
    """Build the complete benchmark and optional factor analysis."""
    selected_id, aligned = align_returns(
        strategy_returns_from_result(result),
        benchmark_returns,
        benchmark_id=benchmark_id,
        factor_returns=factor_returns,
        policy=alignment_policy,
    )
    benchmark_metrics = calculate_benchmark_metrics(
        aligned, periods_per_year=periods_per_year
    )
    factor_summary: dict[str, Any] | None = None
    if factor_returns is not None:
        factor_summary, aligned = calculate_factor_attribution(
            aligned,
            periods_per_year=periods_per_year,
            minimum_observations=minimum_factor_observations,
        )
    return AttributionResult(
        benchmark_id=selected_id,
        alignment_policy=alignment_policy,
        aligned_returns=aligned,
        benchmark_metrics=benchmark_metrics,
        factor_attribution=factor_summary,
    )
