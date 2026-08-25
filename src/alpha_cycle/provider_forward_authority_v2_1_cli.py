"""Build or replay provider-specific forward source authority without semantic promotion."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from alpha_cycle.provider_forward_authority_v2_1 import (
    ProviderForwardAuthorityError,
    publish_kis_provider_authority,
    replay_kis_provider_authority,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alpha-cycle-provider-forward-authority-v2-1")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--source", type=Path, required=True)
    publish.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    publish.add_argument("--research-cutoff-at", type=datetime.fromisoformat, required=True)
    publish.add_argument("--output-root", type=Path, required=True)
    replay = subparsers.add_parser("replay")
    replay.add_argument("--artifact", type=Path, required=True)
    replay.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    replay.add_argument("--research-cutoff-at", type=datetime.fromisoformat, required=True)
    replay.add_argument("--expected-artifact-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "publish":
            directory = publish_kis_provider_authority(
                args.source,
                evaluation_date=args.evaluation_date,
                research_cutoff_at=args.research_cutoff_at,
                output_root=args.output_root,
            )
            artifact = replay_kis_provider_authority(
                directory,
                evaluation_date=args.evaluation_date,
                research_cutoff_at=args.research_cutoff_at,
            )
        else:
            directory = args.artifact
            artifact = replay_kis_provider_authority(
                directory,
                evaluation_date=args.evaluation_date,
                research_cutoff_at=args.research_cutoff_at,
                expected_artifact_id=args.expected_artifact_id,
            )
        print(
            json.dumps(
                {
                    "status": "provider_source_replay_verified",
                    "artifact_id": artifact.artifact_id,
                    "artifact_directory": str(directory.resolve()),
                    "provider_id": "korea_investment_openapi",
                    "symbols": list(artifact.symbols),
                    "provider_source_authority": True,
                    "provider_forward_numeric_authority": False,
                    "market_consensus_authority": False,
                    "revision_authority": False,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, TypeError, ProviderForwardAuthorityError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
