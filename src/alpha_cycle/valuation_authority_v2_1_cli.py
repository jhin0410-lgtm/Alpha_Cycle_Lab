"""CLI for replayable, fail-closed valuation authority acceptance."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.valuation_authority_v2_1 import (
    ValuationAuthorityError,
    build_valuation_authority,
    persist_valuation_authority,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alpha-cycle-valuation-authority-v2-1")
    parser.add_argument("--market-snapshot", type=Path, required=True)
    parser.add_argument("--research-snapshot", type=Path, required=True)
    parser.add_argument("--legacy-valuation-snapshot", type=Path)
    parser.add_argument("--security", action="append", required=True)
    parser.add_argument("--captured-at", type=datetime.fromisoformat)
    parser.add_argument("--horizon-trading-days", type=int, default=250)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        captured_at = args.captured_at or datetime.now(UTC)
        artifacts = []
        for security_id in sorted(set(args.security)):
            artifact = build_valuation_authority(
                market_directory=args.market_snapshot,
                research_directory=args.research_snapshot,
                legacy_valuation_directory=args.legacy_valuation_snapshot,
                security_id=security_id,
                captured_at=captured_at,
                horizon_trading_days=args.horizon_trading_days,
            )
            directory = persist_valuation_authority(
                artifact,
                output_root=args.output,
                market_directory=args.market_snapshot,
                research_directory=args.research_snapshot,
                legacy_valuation_directory=args.legacy_valuation_snapshot,
            )
            payload = artifact.payload_without_id()
            price = next(item for item in artifact.inputs if item.role == "current_price")
            artifacts.append(
                {
                    "security_id": security_id,
                    "artifact_id": artifact.artifact_id,
                    "output_directory": str(directory.resolve()),
                    "current_trusted_price": price.value,
                    "eligible_methods": payload["eligible_methods"],
                    "share_count_authority_established": payload[
                        "share_count_authority_established"
                    ],
                    "capital_structure_authority_established": payload[
                        "capital_structure_authority_established"
                    ],
                    "forward_estimate_authority_established": payload[
                        "forward_estimate_authority_established"
                    ],
                    "price_implied_requirement_authority_established": payload[
                        "price_implied_requirement_authority_established"
                    ],
                    "payoff_surface_authority_established": payload[
                        "payoff_surface_authority_established"
                    ],
                    "probabilities_available": False,
                    "blockers": payload["blockers"],
                }
            )
        print(json.dumps({"status": "recorded", "artifacts": artifacts}, sort_keys=True))
        return 0
    except (OSError, TypeError, ValueError, ValuationAuthorityError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
