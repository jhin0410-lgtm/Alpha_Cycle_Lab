"""Command-line entry point for local research backtests."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from alpha_cycle.backtest.engine import BacktestEngine
from alpha_cycle.brokers.simulated import SimulatedBroker
from alpha_cycle.config import load_config
from alpha_cycle.data.market import MarketDataFeed
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.reporting.metrics import calculate_metrics
from alpha_cycle.reporting.writer import write_outputs
from alpha_cycle.risk.manager import RiskManager
from alpha_cycle.strategies.examples import (
    BuyAndHoldStrategy,
    CrossSectionalMomentumStrategy,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser."""
    parser = argparse.ArgumentParser(prog="alpha-cycle", description="Research backtesting CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    backtest = commands.add_parser("backtest", help="run a deterministic local backtest")
    backtest.add_argument("--input", type=Path, required=True, help="validated OHLCV CSV")
    backtest.add_argument("--strategy", choices=("buy_hold", "momentum"), required=True)
    backtest.add_argument("--initial-cash", help="positive starting cash")
    backtest.add_argument("--output", type=Path, required=True)
    backtest.add_argument("--config", type=Path)
    backtest.add_argument("--lookback", type=int, default=3)
    backtest.add_argument("--top-k", type=int, default=4)
    backtest.add_argument("--rebalance-every", type=int, default=1)
    return parser


def _run_backtest(args: argparse.Namespace) -> None:
    if not args.input.is_file():
        raise ValueError(f"Input CSV does not exist: {args.input}")
    if args.config is not None and not args.config.is_file():
        raise ValueError(f"Config YAML does not exist: {args.config}")
    cash = Decimal(args.initial_cash) if args.initial_cash is not None else None
    if cash is not None and cash <= 0:
        raise ValueError("--initial-cash must be positive")
    config = load_config(args.config, initial_cash=cash)
    feed = MarketDataFeed.from_csv(str(args.input))
    calendar = config.calendar
    if calendar is not None:
        feed = MarketDataFeed.from_csv(str(args.input), calendar=calendar)
    strategy = (
        BuyAndHoldStrategy()
        if args.strategy == "buy_hold"
        else CrossSectionalMomentumStrategy(
            lookback=args.lookback,
            top_k=args.top_k,
            rebalance_every=args.rebalance_every,
        )
    )
    portfolio = Portfolio(config.backtest.initial_cash)
    engine = BacktestEngine(
        feed,
        strategy,
        portfolio,
        SimulatedBroker(config.commission, config.slippage),
        RiskManager(config.risk),
        config.backtest,
        calendar=calendar,
    )
    result = engine.run()
    metrics = calculate_metrics(
        result,
        portfolio,
        periods_per_year=config.backtest.periods_per_year,
        risk_free_rate=config.backtest.risk_free_rate,
    )
    written = write_outputs(
        args.output,
        result,
        metrics,
        strategy_name=args.strategy,
        initial_cash=config.backtest.initial_cash,
    )
    print(f"Backtest completed: {len(result.fills)} fills, {len(written)} output files")
    print(f"Output directory: {args.output.resolve()}")


def main(argv: list[str] | None = None) -> int:
    """Run CLI and convert expected input failures into concise messages."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code in {0, None}:
            return 0
        print("Error: invalid command usage", file=sys.stderr)
        return 2
    try:
        if args.command == "backtest":
            _run_backtest(args)
        return 0
    except (ValueError, OSError, InvalidOperation) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
