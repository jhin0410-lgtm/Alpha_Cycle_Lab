"""CLI for converting a fresh Kiwoom export into market-intelligence evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from alpha_cycle.intelligence.kiwoom_primary_market import (
    DEFAULT_OUTPUT_ROOT,
    KiwoomPrimaryMarketError,
    build_kiwoom_primary_snapshot,
    write_kiwoom_primary_snapshot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert the latest fresh read-only Kiwoom OpenAPI+ export into an "
            "immutable Alpha Cycle market-intelligence snapshot"
        )
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--candle-count", type=int, default=100)
    parser.add_argument("--max-age-minutes", type=int, default=30)
    parser.add_argument(
        "--fallback-reason",
        default="tossinvest_ip_allowlist",
        choices=("tossinvest_ip_allowlist",),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        primary = build_kiwoom_primary_snapshot(
            args.output_root,
            candle_count=args.candle_count,
            max_age_minutes=args.max_age_minutes,
            fallback_reason=args.fallback_reason,
        )
        files = write_kiwoom_primary_snapshot(args.output_root, primary)
        payload: dict[str, object] = {
            "status": "completed",
            "provider": primary.snapshot.provider,
            "snapshot_id": primary.snapshot.snapshot_id,
            "market_directory": str(files[0].parent.resolve()),
            "source_kiwoom_snapshot_id": primary.source.snapshot_id,
            "source_export_directory": str(primary.source.export_directory),
            "fallback_reason": primary.fallback_reason,
            "read_only_market_failover_used": True,
            "cross_provider_price_certified": False,
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except (KiwoomPrimaryMarketError, OSError, TypeError, ValueError) as exc:
        payload = {
            "status": "failed",
            "stage": "kiwoom_primary_market",
            "reason": "kiwoom_primary_market_unavailable",
            "error": str(exc),
            "read_only_market_failover_used": False,
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
