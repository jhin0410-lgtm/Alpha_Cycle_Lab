"""Collect immutable KIS broker-research estimate evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from alpha_cycle.intelligence.expectations import (
    ExpectationIntelligenceCollector,
    write_expectation_intelligence_snapshot,
)
from alpha_cycle.providers.kis_research import KisResearchReadOnlyClient

DEFAULT_SYMBOLS = ("005930", "000660")
DEFAULT_OUTPUT_ROOT = Path("data/private/live-research/expectation-intelligence")


def _symbol(value: str) -> str:
    text = value.strip()
    if len(text) != 6 or not text.isdigit():
        raise argparse.ArgumentTypeError("symbol must be a six-digit stock code")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kis-expectations",
        description=(
            "Collect KIS single-broker research estimates without enabling account or order APIs"
        ),
    )
    parser.add_argument(
        "--symbol",
        action="append",
        type=_symbol,
        dest="symbols",
        help="six-digit stock code; may be repeated",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        if args.max_retries < 0:
            raise ValueError("--max-retries cannot be negative")
        symbols = tuple(args.symbols or DEFAULT_SYMBOLS)
        client = KisResearchReadOnlyClient.from_env(
            timeout_seconds=args.timeout_seconds,
            max_retries=args.max_retries,
        )
        snapshot = ExpectationIntelligenceCollector(client).collect(symbols)
        files = write_expectation_intelligence_snapshot(args.output, snapshot)
        destination = files[0].parent
        payload = {
            "status": "completed",
            "snapshot_id": snapshot.snapshot_id,
            "directory": str(destination.resolve()),
            "provider": snapshot.provider,
            "source_scope": snapshot.source_scope,
            "symbols": list(snapshot.symbols),
            "semantic_status": "raw_structure_only",
            "consensus_certified": False,
            "revision_certified": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "next_action": (
                "Inspect structure.csv and raw_estimate_perform.json before assigning "
                "financial semantics or computing revisions."
            ),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        payload = {
            "status": "blocked",
            "reason": "kis_expectation_evidence_unavailable",
            "error": str(exc),
            "consensus_certified": False,
            "revision_certified": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
