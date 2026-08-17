from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from .intelligence.sk_hynix_product_profitability_historical_expansion_frontier import (
    DEFAULT_HISTORICAL_EXPANSION_FRONTIER,
    load_historical_expansion_frontier,
)
from .intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
    DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
    run_product_revenue_expansion_probe,
)
from .providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Live-probe six pre-2023 SK hynix OpenDART product-revenue candidates in "
            "isolated research output without modifying the canonical historical panel."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--frontier",
        default=str(DEFAULT_HISTORICAL_EXPANSION_FRONTIER),
    )
    parser.add_argument(
        "--template-registry",
        default=str(DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    frontier = load_historical_expansion_frontier(Path(args.frontier))
    results = run_product_revenue_expansion_probe(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=args.evaluation_date,
        output=Path(args.output),
        template_registry=Path(args.template_registry),
    )
    payload = {
        "status": "skhynix_historical_expansion_product_revenue_probe_completed",
        "candidate_count": len(results),
        "successful_periods": [item.period_id for item in results if item.success],
        "failed_periods": [item.period_id for item in results if not item.success],
        "results": [
            {
                "period_id": item.period_id,
                "success": item.success,
                "artifact_pointer": item.artifact_pointer,
                "error_type": item.error_type,
                "error": item.error,
                "canonical_panel_modified": item.canonical_panel_modified,
                "frontier_promoted": item.frontier_promoted,
            }
            for item in results
        ],
        "canonical_panel_modified": False,
        "frontier_promoted": False,
        "fit_enabled": False,
        "holdout_evaluation_enabled": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
