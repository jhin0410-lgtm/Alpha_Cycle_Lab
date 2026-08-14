from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout import (
    DEFAULT_SCOUT_AFTER_DATE,
    DEFAULT_SEC_POST_EARNINGS_SCOUT_OUTPUT,
    capture_post_earnings_product_mix_scout,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and archive post-earnings SK hynix SEC 6-K product-mix source candidates."
        )
    )
    parser.add_argument("--observed-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--after-date",
        type=date.fromisoformat,
        default=DEFAULT_SCOUT_AFTER_DATE,
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SEC_POST_EARNINGS_SCOUT_OUTPUT),
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit(
            "SEC_EDGAR_USER_AGENT is required and must identify the application plus contact email"
        )
    result = capture_post_earnings_product_mix_scout(
        observed_date=args.observed_date,
        after_date=args.after_date,
        user_agent=user_agent,
        output=Path(args.output),
        timeout_seconds=args.timeout_seconds,
    )
    summary = {
        "status": result["status"],
        "evidence_id": result["evidence_id"],
        "observed_date": result["observed_date"],
        "after_date": result["after_date"],
        "filing_count": result["filing_count"],
        "candidate_count": result["candidate_count"],
        "candidate_accessions": result["candidate_accessions"],
        "discovery_only": result["discovery_only"],
        "product_baseline_eligible": result["product_baseline_eligible"],
        "allocation_resolver_registered": result["allocation_resolver_registered"],
        "artifact_directory": result["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
