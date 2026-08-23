from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from alpha_cycle.research_request_preflight_v2_1 import preflight_pending_request_theses


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run typed InvestmentThesisSnapshot preflight for a recorded research request."
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path.cwd() / ".alpha_cycle_artifacts",
    )
    parser.add_argument("--processed-at", type=datetime.fromisoformat)
    parser.add_argument(
        "--research-cutoff-at",
        type=datetime.fromisoformat,
        help=(
            "Point-in-time research cutoff. Required for replay requests; prospective requests "
            "default to --processed-at. Must include a timezone offset when supplied."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(UTC)
    processed_at = args.processed_at or now
    if processed_at.tzinfo is None or processed_at.utcoffset() is None:
        raise SystemExit("--processed-at must include a timezone offset")
    research_cutoff_at = args.research_cutoff_at
    if research_cutoff_at is not None and (
        research_cutoff_at.tzinfo is None or research_cutoff_at.utcoffset() is None
    ):
        raise SystemExit("--research-cutoff-at must include a timezone offset")
    run_id = args.run_id or f"thesis-preflight-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    receipt = preflight_pending_request_theses(
        request_id=args.request_id,
        run_id=run_id,
        processed_at=processed_at,
        artifact_root=args.artifact_root,
        research_cutoff_at=research_cutoff_at,
    )
    print(json.dumps(receipt.payload(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
