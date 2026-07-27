from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SAMPLE_INPUT = REPO_ROOT / "data" / "sample" / "prices.csv"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "example.yaml"
REQUIRED_FILES = [
    "equity_curve.csv",
    "positions.csv",
    "orders.csv",
    "fills.csv",
    "trades.csv",
    "metrics.json",
    "backtest_report.md",
]


def _run_cli(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    pythonpath = command_env.get("PYTHONPATH")
    command_env["PYTHONPATH"] = (
        str(SRC_ROOT) if not pythonpath else f"{SRC_ROOT}{os.pathsep}{pythonpath}"
    )
    return subprocess.run(
        [sys.executable, "-m", "alpha_cycle.cli", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        env=command_env,
        check=False,
    )


def _assert_output_contract(output_dir: Path) -> None:
    assert output_dir.exists()
    for filename in REQUIRED_FILES:
        path = output_dir / filename
        assert path.exists(), f"Missing output file: {filename}"
        assert path.stat().st_size > 0, f"Output file should not be empty: {filename}"

    equity = pd.read_csv(output_dir / "equity_curve.csv")
    assert list(equity.columns)[:2] == ["date", "cash"]
    assert equity["date"].is_monotonic_increasing
    assert not equity["date"].duplicated().any()
    assert (equity["equity"].astype(float) >= 0).all()

    positions = pd.read_csv(output_dir / "positions.csv")
    assert {"date", "ticker", "quantity", "average_cost"}.issubset(set(positions.columns))
    assert positions["quantity"].astype(int).ge(0).all()
    assert not positions["ticker"].isna().any()
    assert positions["ticker"].astype(str).str.len().gt(0).all()

    orders = pd.read_csv(output_dir / "orders.csv")
    assert {"order_id", "ticker", "side", "quantity", "status"}.issubset(set(orders.columns))
    assert orders["order_id"].is_unique
    assert (orders["quantity"].astype(int) != 0).all()
    assert set(orders["side"]).issubset({"buy", "sell"})
    assert set(orders["status"]).issubset({"filled", "rejected", "pending"})

    fills = pd.read_csv(output_dir / "fills.csv")
    assert {
        "order_id",
        "ticker",
        "quantity",
        "price",
        "commission",
        "tax",
        "slippage",
    }.issubset(set(fills.columns))
    assert fills["order_id"].is_unique
    assert (fills["quantity"].astype(int) > 0).all()
    assert (fills["price"].astype(float) > 0).all()
    assert (fills["commission"].astype(float) >= 0).all()
    assert (fills["tax"].astype(float) >= 0).all()
    assert (fills["slippage"].astype(float) >= 0).all()

    trades = pd.read_csv(output_dir / "trades.csv")
    assert {"date", "ticker", "side", "quantity", "price", "gross_value"}.issubset(
        set(trades.columns)
    )
    for value in trades["gross_value"].astype(float):
        assert value >= 0

    metrics = json.loads((output_dir / "metrics.json").read_text(encoding="utf-8"))
    required_keys = {
        "cumulative_return",
        "annualized_return",
        "annualized_volatility",
        "maximum_drawdown",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "win_rate",
        "profit_factor",
        "turnover",
        "total_commission",
        "total_tax",
        "total_slippage",
    }
    assert required_keys.issubset(set(metrics))
    for value in metrics.values():
        if isinstance(value, (int, float)):
            assert isinstance(value, (int, float))
            assert value == value
            assert value not in {float("inf"), float("-inf")}

    report = (output_dir / "backtest_report.md").read_text(encoding="utf-8")
    assert report.strip()
    assert "Backtest Report" in report or "backtest" in report.lower()
    assert "80000000" in report or "80,000,000" in report
    assert "Metrics" in report
    assert "performance claim" in report.lower() or "investment advice" in report.lower()


def test_cli_backtest_writes_all_contract_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "cli-output"
    result = _run_cli(
        "backtest",
        "--input",
        str(SAMPLE_INPUT),
        "--strategy",
        "momentum",
        "--initial-cash",
        "80000000",
        "--config",
        str(EXAMPLE_CONFIG),
        "--output",
        str(output_dir),
    )
    assert result.returncode == 0, result.stderr
    assert "Backtest completed" in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    _assert_output_contract(output_dir)


def test_cli_outputs_are_deterministic_for_same_inputs(tmp_path: Path) -> None:
    output_a = tmp_path / "run_a"
    output_b = tmp_path / "run_b"
    result_a = _run_cli(
        "backtest",
        "--input",
        str(SAMPLE_INPUT),
        "--strategy",
        "momentum",
        "--initial-cash",
        "80000000",
        "--config",
        str(EXAMPLE_CONFIG),
        "--output",
        str(output_a),
    )
    result_b = _run_cli(
        "backtest",
        "--input",
        str(SAMPLE_INPUT),
        "--strategy",
        "momentum",
        "--initial-cash",
        "80000000",
        "--config",
        str(EXAMPLE_CONFIG),
        "--output",
        str(output_b),
    )
    assert result_a.returncode == 0
    assert result_b.returncode == 0
    assert (output_a / "metrics.json").read_text(encoding="utf-8") == (
        output_b / "metrics.json"
    ).read_text(encoding="utf-8")
    assert (output_a / "equity_curve.csv").read_text(encoding="utf-8") == (
        output_b / "equity_curve.csv"
    ).read_text(encoding="utf-8")
    orders_a = pd.read_csv(output_a / "orders.csv")
    orders_b = pd.read_csv(output_b / "orders.csv")
    assert orders_a["order_id"].tolist() == orders_b["order_id"].tolist()
    fills_a = pd.read_csv(output_a / "fills.csv")
    fills_b = pd.read_csv(output_b / "fills.csv")
    assert fills_a["order_id"].tolist() == fills_b["order_id"].tolist()


@pytest.mark.parametrize(
    ("args", "expected_text"),
    [
        (("backtest", "--input", "does-not-exist.csv", "--strategy", "momentum"), "Input CSV"),
        (
            ("backtest", "--input", str(SAMPLE_INPUT), "--strategy", "unknown"),
            "invalid",
        ),
        (
            (
                "backtest",
                "--input",
                str(SAMPLE_INPUT),
                "--strategy",
                "momentum",
                "--config",
                "bad.yaml",
            ),
            "YAML",
        ),
        (
            (
                "backtest",
                "--input",
                str(SAMPLE_INPUT),
                "--strategy",
                "momentum",
                "--initial-cash",
                "0",
            ),
            "positive",
        ),
        (
            (
                "backtest",
                "--input",
                str(SAMPLE_INPUT),
                "--strategy",
                "momentum",
                "--config",
                "bad.yaml",
            ),
            "YAML",
        ),
    ],
)
def test_cli_errors_return_user_friendly_messages(
    tmp_path: Path, args: tuple[str, ...], expected_text: str
) -> None:
    output_dir = tmp_path / "out"
    if args[-1] == "bad.yaml":
        bad_path = tmp_path / "bad.yaml"
        bad_path.write_text("not: [valid", encoding="utf-8")
        args = args[:-1] + (str(bad_path),)
    result = _run_cli(*args, "--output", str(output_dir))
    assert result.returncode != 0
    assert expected_text in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_uses_cli_values_over_yaml_config(tmp_path: Path) -> None:
    output_dir = tmp_path / "override"
    result = _run_cli(
        "backtest",
        "--input",
        str(SAMPLE_INPUT),
        "--strategy",
        "momentum",
        "--initial-cash",
        "90000000",
        "--config",
        str(EXAMPLE_CONFIG),
        "--output",
        str(output_dir),
    )
    assert result.returncode == 0
    report_text = (output_dir / "backtest_report.md").read_text(encoding="utf-8")
    assert "90000000" in report_text
    assert "80000000" not in report_text


def test_cli_reports_invalid_ohlcv_columns(tmp_path: Path) -> None:
    bad_input = tmp_path / "bad.csv"
    sample = pd.read_csv(SAMPLE_INPUT)
    sample = sample.drop(columns=["close"])
    sample.to_csv(bad_input, index=False)
    output_dir = tmp_path / "invalid-ohlcv"
    result = _run_cli(
        "backtest",
        "--input",
        str(bad_input),
        "--strategy",
        "momentum",
        "--initial-cash",
        "80000000",
        "--config",
        str(EXAMPLE_CONFIG),
        "--output",
        str(output_dir),
    )
    assert result.returncode != 0
    assert "Missing required columns" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_reports_output_path_creation_failure(tmp_path: Path) -> None:
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    output_dir = blocked_parent / "subdir"
    result = _run_cli(
        "backtest",
        "--input",
        str(SAMPLE_INPUT),
        "--strategy",
        "momentum",
        "--initial-cash",
        "80000000",
        "--config",
        str(EXAMPLE_CONFIG),
        "--output",
        str(output_dir),
    )
    assert result.returncode != 0
    assert "Error:" in result.stderr
    assert "Traceback" not in result.stderr
