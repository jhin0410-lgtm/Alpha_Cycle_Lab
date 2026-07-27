from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from alpha_cycle.backtest.engine import BacktestResult
from alpha_cycle.reporting.attribution import (
    AlignmentPolicy,
    align_returns,
    analyze_attribution,
    calculate_benchmark_metrics,
    calculate_factor_attribution,
    strategy_returns_from_result,
    validate_benchmark_returns,
    validate_factor_returns,
)


def benchmark_frame(returns: list[float], *, benchmark: str = "KOSPI") -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=len(returns), freq="B")
    return pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "benchmark": benchmark,
            "return": returns,
        }
    )


def factor_frame(values: dict[str, list[float]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    observations = len(next(iter(values.values())))
    dates = pd.date_range("2024-01-02", periods=observations, freq="B")
    for factor, returns in values.items():
        for event_date, value in zip(dates, returns, strict=True):
            rows.append(
                {
                    "date": event_date.strftime("%Y-%m-%d"),
                    "factor": factor,
                    "return": value,
                }
            )
    return pd.DataFrame(rows)


def strategy_frame(returns: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=len(returns), freq="B")
    return pd.DataFrame(
        {
            "date": [value.date() for value in dates],
            "strategy_return": returns,
        }
    )


def result_from_returns(returns: list[float]) -> BacktestResult:
    dates = pd.date_range("2024-01-01", periods=len(returns) + 1, freq="B")
    equity = 100.0
    rows = [{"date": dates[0].date().isoformat(), "equity": str(equity)}]
    for event_date, value in zip(dates[1:], returns, strict=True):
        equity *= 1.0 + value
        rows.append({"date": event_date.date().isoformat(), "equity": str(equity)})
    return BacktestResult(equity_curve=rows)


def test_return_contracts_reject_duplicates_and_non_finite_values() -> None:
    duplicate = pd.concat([benchmark_frame([0.01]), benchmark_frame([0.02])])
    with pytest.raises(ValueError, match="Duplicate benchmark"):
        validate_benchmark_returns(duplicate)

    factors = factor_frame({"value": [0.01, 0.02]})
    factors.loc[0, "return"] = float("inf")
    with pytest.raises(ValueError, match="must be finite"):
        validate_factor_returns(factors)


def test_strict_alignment_rejects_missing_dates_and_inner_drops_them() -> None:
    strategy = strategy_frame([0.01, 0.02, 0.03])
    benchmark = benchmark_frame([0.01, 0.03]).copy()
    benchmark.loc[1, "date"] = "2024-01-04"
    with pytest.raises(ValueError, match="Missing benchmark"):
        align_returns(strategy, benchmark, policy=AlignmentPolicy.STRICT)

    _, aligned = align_returns(strategy, benchmark, policy=AlignmentPolicy.INNER)
    assert aligned["date"].tolist() == [date(2024, 1, 2), date(2024, 1, 4)]


def test_multiple_benchmarks_require_explicit_identifier() -> None:
    benchmark = pd.concat(
        [benchmark_frame([0.01, 0.02], benchmark="KOSPI"), benchmark_frame([0.0, 0.01], benchmark="KOSDAQ")],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="benchmark-id"):
        align_returns(strategy_frame([0.01, 0.02]), benchmark)

    selected, _ = align_returns(
        strategy_frame([0.01, 0.02]), benchmark, benchmark_id="KOSDAQ"
    )
    assert selected == "KOSDAQ"


def test_identical_benchmark_has_unit_beta_and_zero_tracking_error() -> None:
    returns = [0.01, -0.005, 0.002, 0.004]
    _, aligned = align_returns(strategy_frame(returns), benchmark_frame(returns))
    metrics = calculate_benchmark_metrics(aligned)
    assert metrics["benchmark_excess_return"] == pytest.approx(0.0)
    assert metrics["tracking_error"] == pytest.approx(0.0)
    assert metrics["information_ratio"] == pytest.approx(0.0)
    assert metrics["benchmark_beta"] == pytest.approx(1.0)
    assert metrics["benchmark_correlation"] == pytest.approx(1.0)


def test_factor_regression_recovers_known_coefficients() -> None:
    value = [0.01, -0.01, 0.02, -0.02, 0.015, -0.005, 0.012, -0.008]
    momentum = [-0.004, 0.006, 0.003, -0.007, 0.008, -0.002, -0.005, 0.009]
    strategy = [0.001 + 1.5 * v - 0.5 * m for v, m in zip(value, momentum, strict=True)]
    _, aligned = align_returns(
        strategy_frame(strategy),
        benchmark_frame([0.0] * len(strategy)),
        factor_returns=factor_frame({"value": value, "momentum": momentum}),
    )
    summary, augmented = calculate_factor_attribution(aligned, minimum_observations=3)
    assert summary["alpha_periodic"] == pytest.approx(0.001)
    assert summary["betas"]["value"] == pytest.approx(1.5)
    assert summary["betas"]["momentum"] == pytest.approx(-0.5)
    assert summary["r_squared"] == pytest.approx(1.0)
    assert augmented["residual_return"].abs().max() < 1e-12


def test_rank_deficient_factor_matrix_is_rejected() -> None:
    factor = [0.01, -0.01, 0.02, -0.02, 0.015]
    _, aligned = align_returns(
        strategy_frame(factor),
        benchmark_frame([0.0] * len(factor)),
        factor_returns=factor_frame({"one": factor, "duplicate": factor}),
    )
    with pytest.raises(ValueError, match="rank deficient"):
        calculate_factor_attribution(aligned, minimum_observations=3)


def test_strategy_return_conversion_and_complete_analysis() -> None:
    returns = [0.01, -0.005, 0.007, 0.002]
    result = result_from_returns(returns)
    converted = strategy_returns_from_result(result)
    assert converted["strategy_return"].tolist() == pytest.approx(returns)

    attribution = analyze_attribution(
        result,
        benchmark_frame([0.0] * len(returns)),
        factor_returns=factor_frame({"market": [0.004, -0.002, 0.003, 0.001]}),
        minimum_factor_observations=3,
    )
    assert attribution.benchmark_id == "KOSPI"
    assert attribution.factor_attribution is not None
    assert len(attribution.aligned_returns) == 4
