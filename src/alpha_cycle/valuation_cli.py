"""CLI for official share-count, valuation, and financial-history evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alpha_cycle.intelligence.valuation import (
    build_valuation_evidence_snapshot,
    load_security_mappings,
    write_valuation_evidence_snapshot,
)
from alpha_cycle.providers.opendart import OpenDartCredentials
from alpha_cycle.providers.opendart_valuation import OpenDartValuationClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-valuation",
        description="Build point-in-time OpenDART valuation and financial-history evidence",
    )
    parser.add_argument("--research-snapshot", type=Path, required=True)
    parser.add_argument("--market-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history-years", type=int, default=3)
    parser.add_argument("--fs-div", choices=("CFS", "OFS"), default="CFS")
    parser.add_argument("--security-config", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if not args.research_snapshot.is_dir():
            raise ValueError(f"Research snapshot does not exist: {args.research_snapshot}")
        if not args.market_snapshot.is_dir():
            raise ValueError(f"Market snapshot does not exist: {args.market_snapshot}")
        if args.security_config is not None and not args.security_config.is_file():
            raise ValueError(f"Security config does not exist: {args.security_config}")
        if args.history_years <= 0 or args.history_years > 10:
            raise ValueError("--history-years must be between 1 and 10")
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        if args.max_retries < 0:
            raise ValueError("--max-retries cannot be negative")

        client = OpenDartValuationClient(
            OpenDartCredentials.from_env(),
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
        )
        snapshot = build_valuation_evidence_snapshot(
            args.research_snapshot,
            args.market_snapshot,
            client,
            history_years=args.history_years,
            fs_div=args.fs_div,
            security_mappings=load_security_mappings(args.security_config),
        )
        written = write_valuation_evidence_snapshot(args.output, snapshot)
        print(
            json.dumps(
                {
                    "status": "built",
                    "snapshot_id": snapshot.snapshot_id,
                    "evaluation_date": snapshot.evaluation_date.isoformat(),
                    "research_snapshot_id": snapshot.research_snapshot_id,
                    "market_snapshot_id": snapshot.market_snapshot_id,
                    "symbols": snapshot.valuation_metrics["ticker"].astype(str).tolist(),
                    "history_rows": len(snapshot.financial_history),
                    "market_cap_complete_count": int(
                        snapshot.valuation_metrics["market_cap_complete"].astype(bool).sum()
                    ),
                    "valuation_scored_count": int(
                        snapshot.valuation_metrics["valuation_score"].notna().sum()
                    ),
                    "warnings": list(snapshot.warnings),
                    "output_directory": str(written[0].parent.resolve()),
                    "output_files": len(written),
                    "consensus_available": False,
                    "order_api_enabled": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
