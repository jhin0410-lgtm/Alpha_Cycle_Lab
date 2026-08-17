from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY,
)
from .intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
    DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
    run_second_wave_acquisition,
)
from .intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    DEFAULT_SECOND_WAVE_FRONTIER,
    load_second_wave_frontier,
)
from .providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire and certify the six 2019Q1-2020Q3 SK hynix historical source rows in "
            "one pass. Failed legacy product parsers are replayed from preserved raw filing "
            "bytes and certified only by exact consolidated-revenue tie-out."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--frontier", default=str(DEFAULT_SECOND_WAVE_FRONTIER))
    parser.add_argument(
        "--product-output", default=str(DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT)
    )
    parser.add_argument(
        "--company-output", default=str(DEFAULT_SECOND_WAVE_COMPANY_OUTPUT)
    )
    parser.add_argument(
        "--product-template-registry",
        default=str(DEFAULT_PRODUCT_REVENUE_TEMPLATE_REGISTRY),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    frontier = load_second_wave_frontier(Path(args.frontier))
    results = run_second_wave_acquisition(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=args.evaluation_date,
        product_output=Path(args.product_output),
        company_output=Path(args.company_output),
        product_template_registry=Path(args.product_template_registry),
    )
    source_complete = [item.period_id for item in results if item.source_layer_complete]
    payload = {
        "status": "skhynix_product_profitability_second_wave_acquisition_completed",
        "frontier_evidence_id": frontier.evidence_id,
        "candidate_count": len(results),
        "target_additional_training_rows": frontier.target_additional_training_rows,
        "driver_numeric_source_certified_count": sum(
            item.driver_four_field_numeric_source_certified for item in results
        ),
        "product_probe_success_count": sum(
            item.product_revenue_probe_success for item in results
        ),
        "product_revenue_certified_count": sum(
            item.product_revenue_certified for item in results
        ),
        "product_recovery_certified_count": sum(
            item.product_recovery is not None and item.product_recovery.certified
            for item in results
        ),
        "company_profitability_verified_count": sum(
            item.company_profitability_verified for item in results
        ),
        "source_layer_complete_count": len(source_complete),
        "source_layer_complete_periods": source_complete,
        "projected_total_training_rows_if_all_six_later_promote": 15,
        "training_row_promoted": False,
        "fit_enabled": False,
        "holdout_period": frontier.holdout_period,
        "holdout_evaluation_allowed": False,
        "results": [
            {
                "period_id": item.period_id,
                "driver_four_field_numeric_source_certified": (
                    item.driver_four_field_numeric_source_certified
                ),
                "product_revenue_probe_success": item.product_revenue_probe_success,
                "product_revenue_certified": item.product_revenue_certified,
                "product_recovery": (
                    None if item.product_recovery is None else asdict(item.product_recovery)
                ),
                "company_profitability_verified": item.company_profitability_verified,
                "source_layer_complete": item.source_layer_complete,
                "product_artifact_pointer": item.product_artifact_pointer,
                "company_observation": (
                    None
                    if item.company_observation is None
                    else {
                        "rcept_no": item.company_observation.rcept_no,
                        "revenue_krw": item.company_observation.revenue_krw,
                        "cost_of_sales_krw": item.company_observation.cost_of_sales_krw,
                        "gross_profit_krw": item.company_observation.gross_profit_krw,
                        "gross_margin_percent": item.company_observation.gross_margin_percent,
                        "raw_payload_sha256": item.company_observation.raw_payload_sha256,
                    }
                ),
                "product_probe_error": item.product_probe_error,
                "company_error": item.company_error,
            }
            for item in results
        ],
        "next_action": (
            "promote_all_six_source_rows_then_build_frozen_15_row_training_candidate"
            if len(source_complete) == 6
            else "only_unresolved_source_layers_require_follow_up"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
