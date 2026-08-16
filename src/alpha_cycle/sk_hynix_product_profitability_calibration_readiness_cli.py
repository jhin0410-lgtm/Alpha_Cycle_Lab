from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from alpha_cycle.intelligence.sec_product_profitability_support import (
    DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sec_product_profitability_support_verifier import (
    load_sec_product_profitability_support_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_calibration_inventory import (
    build_skhynix_product_profitability_calibration_inventory,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_holdout import (
    build_skhynix_product_profitability_holdout_plan,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_identifiability_audit import (
    audit_skhynix_product_profitability_identifiability,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay all SK hynix profitability-calibration evidence, reserve Q1 2026, "
            "and report the fail-closed structural-identifiability state."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--current-product-revenue-pointer",
        default=str(DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER),
    )
    parser.add_argument(
        "--profitability-support-pointer",
        default=str(DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER),
    )
    parser.add_argument(
        "--cycle-driver-pointer",
        default=str(DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER),
    )
    parser.add_argument(
        "--quarterly-company-profitability-pointer",
        default=str(DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER),
    )
    parser.add_argument(
        "--historical-product-revenue-pointer",
        default=str(DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evaluation_date = args.evaluation_date
    profitability_pointer = Path(args.profitability_support_pointer)
    historical_pointer = Path(args.historical_product_revenue_pointer)

    support = load_sec_product_profitability_support_evidence(
        profitability_pointer,
        evaluation_date=evaluation_date,
    )
    historical = load_historical_product_revenue_panel_evidence(
        historical_pointer,
        evaluation_date=evaluation_date,
    )
    inventory = build_skhynix_product_profitability_calibration_inventory(
        evaluation_date=evaluation_date,
        product_revenue_pointer=Path(args.current_product_revenue_pointer),
        profitability_support_pointer=profitability_pointer,
        cycle_driver_support_pointer=Path(args.cycle_driver_pointer),
        quarterly_company_profitability_pointer=Path(
            args.quarterly_company_profitability_pointer
        ),
        historical_product_revenue_pointer=historical_pointer,
        reserve_q1_2026_holdout=True,
    )
    holdout = build_skhynix_product_profitability_holdout_plan(support)
    audit = audit_skhynix_product_profitability_identifiability(inventory, holdout)

    summary = {
        "status": "skhynix_product_profitability_calibration_readiness",
        "evaluation_date": evaluation_date.isoformat(),
        "historical_product_revenue_successful_period_count": len(
            historical.successful_periods
        ),
        "historical_product_revenue_successful_periods": historical.successful_periods,
        "historical_product_revenue_failed_period_count": len(historical.failed_periods),
        "historical_product_revenue_failed_periods": historical.failed_periods,
        "historical_product_revenue_full_source_coverage_certified": (
            historical.full_source_coverage_certified
        ),
        "product_revenue_fit_period_count": len(
            inventory.historical_product_revenue_periods
        ),
        "company_profitability_fit_period_count": len(
            inventory.company_profitability_constraint_periods
        ),
        "cycle_driver_source_period_count": len(inventory.cycle_driver_history_periods),
        "holdout_periods": inventory.holdout_periods,
        "aligned_company_product_constraint_periods": (
            audit.aligned_company_product_constraint_periods
        ),
        "independent_training_constraint_count": audit.independent_training_constraint_count,
        "numeric_cycle_driver_periods": audit.numeric_cycle_driver_periods,
        "registered_parameter_count": audit.registered_parameter_count,
        "structurally_identifiable": audit.structurally_identifiable,
        "fit_attempt_allowed": audit.fit_attempt_allowed,
        "holdout_evaluation_allowed": audit.holdout_evaluation_allowed,
        "block_reason": audit.reason,
        "product_profitability_source_fact": audit.product_profitability_source_fact,
        "numeric_forecast_enabled": audit.numeric_forecast_enabled,
        "fair_value_estimate_enabled": audit.fair_value_estimate_enabled,
        "target_price_enabled": audit.target_price_enabled,
        "decision_score_enabled": audit.decision_score_enabled,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
