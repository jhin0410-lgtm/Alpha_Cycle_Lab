"""CLI for official OpenDART and ECOS research-intelligence snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from alpha_cycle.data.research import RevisionPolicy
from alpha_cycle.intelligence.fundamental_macro import (
    FundamentalMacroCollector,
    write_fundamental_macro_snapshot,
)
from alpha_cycle.providers.ecos import EcosReadOnlyClient, load_ecos_series_config
from alpha_cycle.providers.opendart import REPORT_PERIODS, OpenDartReadOnlyClient


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def _stock_codes(value: str) -> list[str]:
    """Normalize comma-separated KRX codes while preserving leading zeroes."""

    raw_codes = [item.strip() for item in value.split(",") if item.strip()]
    if not raw_codes:
        raise ValueError("--symbols must include at least one symbol")
    normalized: list[str] = []
    for raw in raw_codes:
        if not raw.isdigit() or len(raw) > 6:
            raise ValueError("--symbols must contain numeric KRX codes of at most six digits")
        code = raw.zfill(6)
        if code not in normalized:
            normalized.append(code)
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-research",
        description="Collect official OpenDART and ECOS point-in-time research data",
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help='comma-separated KRX codes; quote in PowerShell, for example "005930,000660"',
    )
    parser.add_argument("--business-year", type=int, required=True)
    parser.add_argument("--report-code", choices=tuple(REPORT_PERIODS), required=True)
    parser.add_argument("--fs-div", choices=("CFS", "OFS"), default="CFS")
    parser.add_argument("--disclosure-begin", type=_iso_date, required=True)
    parser.add_argument("--disclosure-end", type=_iso_date, required=True)
    parser.add_argument("--evaluation-date", type=_iso_date, required=True)
    parser.add_argument(
        "--revision-policy",
        choices=tuple(policy.value for policy in RevisionPolicy),
        default=RevisionPolicy.LATEST_KNOWN.value,
    )
    parser.add_argument("--ecos-config", type=Path, required=True)
    parser.add_argument("--market-snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        symbols = _stock_codes(args.symbols)
        if args.business_year < 2015:
            raise ValueError("--business-year must be 2015 or later")
        if not args.ecos_config.is_file():
            raise ValueError(f"ECOS config does not exist: {args.ecos_config}")
        if args.market_snapshot is not None and not args.market_snapshot.exists():
            raise ValueError(f"Market snapshot does not exist: {args.market_snapshot}")
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        if args.max_retries < 0:
            raise ValueError("--max-retries cannot be negative")
        opendart = OpenDartReadOnlyClient.from_env()
        ecos = EcosReadOnlyClient.from_env()
        for client in (opendart, ecos):
            client.timeout_seconds = args.timeout_seconds
            client.max_retries = args.max_retries
        snapshot = FundamentalMacroCollector(opendart, ecos).collect(
            symbols,
            business_year=args.business_year,
            report_code=args.report_code,
            fs_div=args.fs_div,
            disclosure_begin=args.disclosure_begin,
            disclosure_end=args.disclosure_end,
            ecos_specs=load_ecos_series_config(args.ecos_config),
            evaluation_date=args.evaluation_date,
            revision_policy=RevisionPolicy(args.revision_policy),
            market_snapshot=args.market_snapshot,
        )
        written = write_fundamental_macro_snapshot(args.output, snapshot)
        print(
            json.dumps(
                {
                    "status": "collected",
                    "snapshot_id": snapshot.snapshot_id,
                    "captured_at": snapshot.captured_at.isoformat(),
                    "evaluation_date": snapshot.evaluation_date.isoformat(),
                    "market_snapshot_id": snapshot.market_snapshot_id,
                    "financial_rows": len(snapshot.financials),
                    "disclosure_rows": len(snapshot.disclosures),
                    "macro_rows": len(snapshot.macro),
                    "output_directory": str(written[0].parent.resolve()),
                    "output_files": len(written),
                    "order_api_enabled": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
