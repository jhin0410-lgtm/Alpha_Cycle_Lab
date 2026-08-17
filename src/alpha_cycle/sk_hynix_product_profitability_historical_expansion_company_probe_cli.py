from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_company_probe import (
    DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT,
    run_expansion_company_profitability_probe,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_frontier import (
    DEFAULT_HISTORICAL_EXPANSION_FRONTIER,
    load_historical_expansion_frontier,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe 2021Q1-Q3 and 2022Q1-Q3 SK hynix Revenue/CostOfSales/GrossProfit "
            "from current OpenDART all-accounts payloads without promoting training rows."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--frontier", default=str(DEFAULT_HISTORICAL_EXPANSION_FRONTIER))
    parser.add_argument("--output", default=str(DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    frontier = load_historical_expansion_frontier(Path(args.frontier))
    results = run_expansion_company_profitability_probe(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=args.evaluation_date,
        output=Path(args.output),
    )
    successful = tuple(item.period_id for item in results if item.success)
    failed = tuple(item.period_id for item in results if not item.success)
    summary = {
        "status": "skhynix_historical_expansion_company_profitability_probe_completed",
        "candidate_count": len(results),
        "successful_periods": successful,
        "failed_periods": failed,
        "results": [
            {
                **asdict(item),
                "observation": None
                if item.observation is None
                else {
                    **asdict(item.observation),
                    "period_end": item.observation.period_end.isoformat(),
                    "available_date": item.observation.available_date.isoformat(),
                },
            }
            for item in results
        ],
        "current_retrieval_historical_source_fact": bool(successful),
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "product_profitability_source_fact": False,
        "frontier_promoted": False,
        "training_row_promoted": False,
        "fit_enabled": False,
        "next_action": (
            "retain_successful_company_constraints_and_continue_product_layout_diagnostics_"
            "plus_four_field_cycle_driver_acquisition"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
