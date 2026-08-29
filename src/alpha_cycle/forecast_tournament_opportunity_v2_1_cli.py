"""CLI for frozen forecast tournament and 3/6/12M opportunity acceptance."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.forecast_tournament_opportunity_v2_1 import (
    DEFAULT_ESTIMATOR,
    DEFAULT_FEATURE,
    DEFAULT_SOURCE_CAPTURE_DIRECTORY,
    ForecastTournamentError,
    build_forecast_opportunity_bundle,
    persist_forecast_opportunity_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alpha-cycle-forecast-tournament-v2-1")
    parser.add_argument("--frozen-forecast", type=Path, required=True)
    parser.add_argument("--frozen-feature", type=Path, default=DEFAULT_FEATURE)
    parser.add_argument("--selected-estimator", type=Path, default=DEFAULT_ESTIMATOR)
    parser.add_argument(
        "--source-capture-directory", type=Path, default=DEFAULT_SOURCE_CAPTURE_DIRECTORY
    )
    parser.add_argument("--market-snapshot-id", required=True)
    parser.add_argument("--research-snapshot-id", required=True)
    parser.add_argument("--evaluation-date", type=datetime.fromisoformat, required=True)
    parser.add_argument("--captured-at", type=datetime.fromisoformat)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        captured_at = args.captured_at or datetime.now(UTC)
        bundle = build_forecast_opportunity_bundle(
            frozen_forecast_path=args.frozen_forecast,
            captured_at=captured_at,
            evaluation_date=args.evaluation_date.date(),
            market_snapshot_id=args.market_snapshot_id,
            research_snapshot_id=args.research_snapshot_id,
            frozen_feature_path=args.frozen_feature,
            selected_estimator_path=args.selected_estimator,
            source_capture_directory=args.source_capture_directory,
        )
        directory = persist_forecast_opportunity_bundle(
            bundle,
            output_root=args.output,
            frozen_forecast_path=args.frozen_forecast,
            frozen_feature_path=args.frozen_feature,
            selected_estimator_path=args.selected_estimator,
            source_capture_directory=args.source_capture_directory,
        )
        print(
            json.dumps(
                {
                    "status": "recorded",
                    "artifact_id": bundle.artifact_id,
                    "output_directory": str(directory.resolve()),
                    "eligible_candidate_ids": [
                        item.candidate_id
                        for item in bundle.tournament.candidates
                        if item.tournament_eligible
                    ],
                    "winner_candidate_id": bundle.tournament.winner_candidate_id,
                    "outcome_scoring_available": (
                        bundle.tournament.outcome_scoring_available
                    ),
                    "opportunities": [item.payload() for item in bundle.opportunities],
                    "partial_ranking_available": False,
                    "overall_ranking_available": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, TypeError, ValueError, ForecastTournamentError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
