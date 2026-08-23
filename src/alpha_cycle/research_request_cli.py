from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record an immutable Alpha Cycle Lab research request without executing it."
    )
    parser.add_argument("--request-id")
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--horizon", required=True, type=int, choices=(60, 120, 250))
    parser.add_argument("--securities", required=True, nargs="+")
    parser.add_argument(
        "--mode",
        choices=tuple(item.value for item in ResearchRoundMode),
        default=ResearchRoundMode.PROSPECTIVE.value,
    )
    parser.add_argument(
        "--lane",
        choices=tuple(item.value for item in UnderwritingLane),
        default=UnderwritingLane.DEEP.value,
    )
    parser.add_argument("--request-text", required=True)
    parser.add_argument("--tags", nargs="*", default=())
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path.cwd() / ".alpha_cycle_artifacts",
    )
    parser.add_argument("--requested-at", type=datetime.fromisoformat)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(UTC)
    requested_at = args.requested_at or now
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise SystemExit("--requested-at must include a timezone offset")
    request_id = args.request_id or f"request-{now:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    receipt = record_analysis_request(
        request_id=request_id,
        requested_at=requested_at,
        recorded_at=now,
        evaluation_date=args.evaluation_date,
        horizon_trading_days=args.horizon,
        security_ids=tuple(args.securities),
        mode=ResearchRoundMode(args.mode),
        requested_lane=UnderwritingLane(args.lane),
        request_text=args.request_text,
        artifact_root=args.artifact_root,
        tags=tuple(args.tags),
    )
    print(json.dumps(receipt.payload(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
