from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.live_typed_research_runner_v2_1 import run_live_typed_research_round


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the persisted-source typed research bridge")
    parser.add_argument("mode", choices=("prospective", "replay"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--processed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--security-id", action="append", required=True)
    parser.add_argument("--horizon-trading-days", type=int, default=120)
    parser.add_argument("--requested-lane", choices=("fast", "deep"), default="deep")
    parser.add_argument("--request-text", required=True)
    parser.add_argument("--manifest-path", type=Path)
    parser.add_argument("--market-source-directory", type=Path)
    parser.add_argument("--research-source-directory", type=Path)
    parser.add_argument("--evaluation-date", type=date.fromisoformat)
    parser.add_argument("--research-cutoff-at", type=datetime.fromisoformat)
    args = parser.parse_args(argv)
    receipt = run_live_typed_research_round(
        artifact_root=args.artifact_root,
        mode=ResearchRoundMode(args.mode),
        request_id=args.request_id,
        run_id=args.run_id,
        round_id=args.round_id,
        processed_at=args.processed_at,
        security_ids=tuple(args.security_id),
        horizon_trading_days=args.horizon_trading_days,
        requested_lane=UnderwritingLane(args.requested_lane),
        request_text=args.request_text,
        manifest_path=args.manifest_path,
        market_source_directory=args.market_source_directory,
        research_source_directory=args.research_source_directory,
        evaluation_date=args.evaluation_date,
        research_cutoff_at=args.research_cutoff_at,
    )
    print(json.dumps(receipt.payload(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
