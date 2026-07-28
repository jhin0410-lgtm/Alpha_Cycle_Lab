"""Command-line entry point for research, intelligence, and paper state."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from alpha_cycle.backtest.engine import BacktestEngine
from alpha_cycle.brokers.reconciliation import (
    load_broker_snapshot,
    local_state_from_store,
    reconcile_account_state,
    write_reconciliation_outputs,
)
from alpha_cycle.brokers.simulated import SimulatedBroker
from alpha_cycle.config import load_config
from alpha_cycle.data.market import MarketDataFeed
from alpha_cycle.intelligence import MarketIntelligenceCollector, write_market_intelligence_snapshot
from alpha_cycle.paper import PaperRunMetadata, PaperTradingStore
from alpha_cycle.portfolio.portfolio import Portfolio
from alpha_cycle.providers import TossInvestReadOnlyClient
from alpha_cycle.reporting.attribution import (
    AlignmentPolicy,
    CsvBenchmarkReturnsAdapter,
    CsvFactorReturnsAdapter,
    analyze_attribution,
    strategy_returns_from_result,
)
from alpha_cycle.reporting.metrics import calculate_metrics
from alpha_cycle.reporting.writer import write_outputs
from alpha_cycle.risk.manager import RiskManager
from alpha_cycle.scenarios import load_stress_config, run_stress_tests, write_stress_outputs
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
    backtest.add_argument("--benchmark", type=Path, help="long-form benchmark return CSV")
    backtest.add_argument("--benchmark-id", help="benchmark identifier for multiple series")
    backtest.add_argument("--factors", type=Path, help="long-form factor return CSV")
    backtest.add_argument(
        "--alignment-policy",
        choices=tuple(policy.value for policy in AlignmentPolicy),
        default=AlignmentPolicy.STRICT.value,
    )
    backtest.add_argument("--min-factor-observations", type=int, default=20)
    backtest.add_argument(
        "--stress-config",
        type=Path,
        help="YAML path and factor stress scenario definitions",
    )

    intelligence = commands.add_parser(
        "market-intel",
        help="collect read-only TossInvest prices and calculate technical features",
    )
    intelligence.add_argument(
        "--symbols",
        required=True,
        help="comma-separated KR or US symbols, for example 005930,000660 or AAPL,MSFT",
    )
    intelligence.add_argument("--interval", choices=("1m", "1d"), default="1d")
    intelligence.add_argument("--count", type=int, default=100)
    intelligence.add_argument(
        "--adjusted",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="request adjusted candles explicitly; default is raw/unadjusted",
    )
    intelligence.add_argument("--output", type=Path, required=True)
    intelligence.add_argument("--timeout-seconds", type=float, default=10.0)
    intelligence.add_argument("--max-retries", type=int, default=3)

    paper = commands.add_parser("paper-state", help="manage a local paper state database")
    paper_commands = paper.add_subparsers(dest="paper_action", required=True)
    paper_init = paper_commands.add_parser("init", help="initialize immutable run metadata")
    paper_init.add_argument("--database", type=Path, required=True)
    paper_init.add_argument("--run-id", required=True)
    paper_init.add_argument("--strategy", required=True)
    paper_init.add_argument("--initial-cash", required=True)
    paper_init.add_argument("--config-digest", required=True)
    paper_verify = paper_commands.add_parser("verify", help="verify the full state hash chain")
    paper_verify.add_argument("--database", type=Path, required=True)
    paper_export = paper_commands.add_parser("export", help="export normalized audit files")
    paper_export.add_argument("--database", type=Path, required=True)
    paper_export.add_argument("--output", type=Path, required=True)

    reconcile = commands.add_parser(
        "broker-reconcile",
        help="compare local paper state with a read-only broker snapshot",
    )
    reconcile.add_argument("--database", type=Path, required=True)
    reconcile.add_argument("--snapshot", type=Path, required=True)
    reconcile.add_argument("--output", type=Path, required=True)
    reconcile.add_argument("--max-snapshot-age-seconds", type=int, default=300)
    reconcile.add_argument("--future-tolerance-seconds", type=int, default=5)
    reconcile.add_argument("--cash-tolerance", default="0")
    reconcile.add_argument("--average-cost-tolerance", default="0.01")
    return parser


def _run_backtest(args: argparse.Namespace) -> None:
    if not args.input.is_file():
        raise ValueError(f"Input CSV does not exist: {args.input}")
    if args.config is not None and not args.config.is_file():
        raise ValueError(f"Config YAML does not exist: {args.config}")
    if args.factors is not None and args.benchmark is None:
        raise ValueError("--factors requires --benchmark")
    if args.min_factor_observations <= 0:
        raise ValueError("--min-factor-observations must be positive")
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
        SimulatedBroker(
            config.commission,
            config.slippage,
            max_volume_participation=config.backtest.max_volume_participation,
        ),
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

    attribution = None
    if args.benchmark is not None:
        benchmark_returns = CsvBenchmarkReturnsAdapter(args.benchmark).load()
        factor_returns = (
            CsvFactorReturnsAdapter(args.factors).load() if args.factors is not None else None
        )
        attribution = analyze_attribution(
            result,
            benchmark_returns,
            benchmark_id=args.benchmark_id,
            factor_returns=factor_returns,
            alignment_policy=AlignmentPolicy(args.alignment_policy),
            periods_per_year=config.backtest.periods_per_year,
            minimum_factor_observations=args.min_factor_observations,
        )
        metrics.update(attribution.benchmark_metrics)
        if attribution.factor_attribution is not None:
            factor_summary = attribution.factor_attribution
            metrics.update(
                {
                    "factor_observations": int(factor_summary["observations"]),
                    "factor_alpha_annualized": float(factor_summary["alpha_annualized"]),
                    "factor_r_squared": float(factor_summary["r_squared"]),
                    "factor_residual_volatility": float(
                        factor_summary["residual_volatility"]
                    ),
                }
            )

    written = write_outputs(
        args.output,
        result,
        metrics,
        strategy_name=args.strategy,
        initial_cash=config.backtest.initial_cash,
        attribution=attribution,
    )
    if args.stress_config is not None:
        stress_config = load_stress_config(args.stress_config)
        factor_attribution = (
            attribution.factor_attribution if attribution is not None else None
        )
        stress_result = run_stress_tests(
            strategy_returns_from_result(result),
            stress_config,
            factor_attribution=factor_attribution,
            periods_per_year=config.backtest.periods_per_year,
        )
        written.extend(write_stress_outputs(args.output, stress_result))

    print(f"Backtest completed: {len(result.fills)} fills, {len(written)} output files")
    print(f"Output directory: {args.output.resolve()}")


def _run_market_intelligence(args: argparse.Namespace) -> None:
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        raise ValueError("--symbols must include at least one symbol")
    if args.count <= 0 or args.count > 200:
        raise ValueError("--count must be between 1 and 200")
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    if args.max_retries < 0:
        raise ValueError("--max-retries cannot be negative")
    client = TossInvestReadOnlyClient.from_env()
    client.timeout_seconds = args.timeout_seconds
    client.max_retries = args.max_retries
    snapshot = MarketIntelligenceCollector(client).collect(
        symbols,
        interval=args.interval,
        count=args.count,
        adjusted=args.adjusted,
    )
    written = write_market_intelligence_snapshot(args.output, snapshot)
    print(
        json.dumps(
            {
                "status": "collected",
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "symbols": list(snapshot.symbols),
                "interval": snapshot.interval,
                "adjusted": snapshot.adjusted,
                "output_directory": str(written[0].parent.resolve()),
                "output_files": len(written),
                "order_api_enabled": False,
            },
            sort_keys=True,
        )
    )


def _run_paper_state(args: argparse.Namespace) -> None:
    store = PaperTradingStore(args.database)
    if args.paper_action == "init":
        store.initialize(
            PaperRunMetadata(
                run_id=args.run_id,
                strategy_name=args.strategy,
                initial_cash=Decimal(args.initial_cash),
                config_digest=args.config_digest,
                created_at=datetime.now(UTC),
            )
        )
        print(f"Paper state initialized: {args.database.resolve()}")
        return
    if not args.database.is_file():
        raise ValueError(f"Paper state database does not exist: {args.database}")
    if args.paper_action == "verify":
        report = store.assert_integrity()
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "sessions": report.sessions,
                    "order_states": report.order_states,
                    "fills": report.fills,
                    "latest_session": (
                        report.latest_session.isoformat()
                        if report.latest_session is not None
                        else None
                    ),
                    "latest_hash": report.latest_hash,
                },
                sort_keys=True,
            )
        )
        return
    written = store.export_audit(args.output)
    print(f"Paper audit exported: {len(written)} files")
    print(f"Output directory: {args.output.resolve()}")


def _run_broker_reconciliation(args: argparse.Namespace) -> None:
    if not args.database.is_file():
        raise ValueError(f"Paper state database does not exist: {args.database}")
    if not args.snapshot.is_file():
        raise ValueError(f"Broker snapshot does not exist: {args.snapshot}")
    local = local_state_from_store(PaperTradingStore(args.database))
    broker = load_broker_snapshot(args.snapshot)
    report = reconcile_account_state(
        local,
        broker,
        max_snapshot_age_seconds=args.max_snapshot_age_seconds,
        future_tolerance_seconds=args.future_tolerance_seconds,
        cash_tolerance=Decimal(args.cash_tolerance),
        average_cost_tolerance=Decimal(args.average_cost_tolerance),
    )
    written = write_reconciliation_outputs(args.output, report)
    print(
        json.dumps(
            {
                "status": report.status.value,
                "can_submit_orders": report.can_submit_orders,
                "blocking_count": report.blocking_count,
                "warning_count": report.warning_count,
                "output_files": len(written),
            },
            sort_keys=True,
        )
    )
    if not report.can_submit_orders:
        raise ValueError(
            "Broker reconciliation did not authorize order submission; review output artifacts"
        )


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
        elif args.command == "market-intel":
            _run_market_intelligence(args)
        elif args.command == "paper-state":
            _run_paper_state(args)
        elif args.command == "broker-reconcile":
            _run_broker_reconciliation(args)
        return 0
    except (ValueError, OSError, InvalidOperation, sqlite3.DatabaseError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
