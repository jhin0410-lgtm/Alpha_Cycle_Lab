"""CLI for investment decision snapshots and forward outcome labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alpha_cycle.intelligence.decision import write_investment_decision_snapshot
from alpha_cycle.intelligence.decision_resilient import (
    build_investment_decision_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import (
    DecisionPolicy,
    load_company_exposures,
)
from alpha_cycle.intelligence.outcomes import write_outcome_labels
from alpha_cycle.providers.opendart import normalize_listed_stock_code


def _horizons(value: str) -> tuple[int, ...]:
    try:
        result = tuple(sorted(set(int(item.strip()) for item in value.split(",") if item.strip())))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("horizons must be comma-separated integers") from exc
    if not result or any(item <= 0 for item in result):
        raise argparse.ArgumentTypeError("horizons must contain positive integers")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-decision",
        description="Build explainable investment decisions and forward outcome labels",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build a decision-intelligence snapshot")
    build.add_argument("--research-snapshot", type=Path, required=True)
    build.add_argument("--market-snapshot", type=Path, required=True)
    build.add_argument("--valuation-snapshot", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--benchmark")
    build.add_argument("--company-config", type=Path)
    build.add_argument("--recent-disclosure-days", type=int, default=365)
    build.add_argument("--positive-threshold", type=float, default=3.8)
    build.add_argument("--mixed-threshold", type=float, default=2.8)
    build.add_argument("--minimum-coverage", type=float, default=0.55)

    label = subparsers.add_parser("label", help="label a prior decision with future prices")
    label.add_argument("--decision-snapshot", type=Path, required=True)
    label.add_argument("--future-market-snapshot", type=Path, required=True)
    label.add_argument("--output", type=Path, required=True)
    label.add_argument("--horizons", type=_horizons, default=(1, 5, 20, 60))
    label.add_argument("--benchmark")
    return parser


def _build(args: argparse.Namespace) -> int:
    if args.company_config is not None and not args.company_config.is_file():
        raise ValueError(f"Company config does not exist: {args.company_config}")
    if args.valuation_snapshot is not None and not args.valuation_snapshot.is_dir():
        raise ValueError(f"Valuation snapshot does not exist: {args.valuation_snapshot}")
    benchmark = normalize_listed_stock_code(args.benchmark) if args.benchmark else None
    policy = DecisionPolicy(
        recent_disclosure_days=args.recent_disclosure_days,
        positive_threshold=args.positive_threshold,
        mixed_threshold=args.mixed_threshold,
        minimum_coverage=args.minimum_coverage,
    )
    snapshot = build_investment_decision_snapshot(
        args.research_snapshot,
        args.market_snapshot,
        valuation_snapshot=args.valuation_snapshot,
        benchmark=benchmark,
        exposures=load_company_exposures(args.company_config),
        policy=policy,
    )
    written = write_investment_decision_snapshot(args.output, snapshot)
    states = {
        str(key): int(value)
        for key, value in snapshot.scorecards["decision_state"].value_counts().items()
    }
    print(
        json.dumps(
            {
                "status": "built",
                "snapshot_id": snapshot.snapshot_id,
                "evaluation_date": snapshot.evaluation_date.isoformat(),
                "research_snapshot_id": snapshot.research_snapshot_id,
                "market_snapshot_id": snapshot.market_snapshot_id,
                "valuation_snapshot_id": snapshot.valuation_snapshot_id,
                "symbols": snapshot.scorecards["ticker"].astype(str).tolist(),
                "decision_states": states,
                "warnings": list(snapshot.warnings),
                "output_directory": str(written[0].parent.resolve()),
                "output_files": len(written),
                "valuation_available": snapshot.valuation_snapshot_id is not None,
                "valuation_scored_count": int(
                    snapshot.scorecards["valuation_score"].notna().sum()
                ),
                "consensus_available": False,
                "order_api_enabled": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _label(args: argparse.Namespace) -> int:
    benchmark = normalize_listed_stock_code(args.benchmark) if args.benchmark else None
    written = write_outcome_labels(
        args.output,
        args.decision_snapshot,
        args.future_market_snapshot,
        horizons=args.horizons,
        benchmark=benchmark,
    )
    print(
        json.dumps(
            {
                "status": "labeled",
                "output_directory": str(written[0].parent.resolve()),
                "output_files": len(written),
                "horizons": list(args.horizons),
                "benchmark": benchmark,
                "order_api_enabled": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "build":
            return _build(args)
        if args.command == "label":
            return _label(args)
        raise ValueError(f"Unknown command: {args.command}")
    except (ValueError, OSError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
