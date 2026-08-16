from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_METHOD_PATH,
    DEFAULT_STRUCTURAL_RANK_PROBE_OUTPUT,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_rank_probe_report import (
    capture_structural_rank_probe_report,
    load_structural_rank_probe_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a direction-only structural design for SK hynix DRAM/NAND latent "
            "profitability, certify matrix rank, and keep estimation disabled."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--method", default=str(DEFAULT_STRUCTURAL_METHOD_PATH))
    parser.add_argument(
        "--historical-product-revenue-pointer",
        default=str(DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER),
    )
    parser.add_argument(
        "--company-profitability-pointer",
        default=str(DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER),
    )
    parser.add_argument(
        "--cycle-driver-pointer",
        default=str(DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER),
    )
    parser.add_argument("--output", default=str(DEFAULT_STRUCTURAL_RANK_PROBE_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    captured = capture_structural_rank_probe_report(
        evaluation_date=args.evaluation_date,
        method_path=Path(args.method),
        historical_product_revenue_pointer=Path(args.historical_product_revenue_pointer),
        company_profitability_pointer=Path(args.company_profitability_pointer),
        cycle_driver_pointer=Path(args.cycle_driver_pointer),
        output=output,
    )
    verified = load_structural_rank_probe_report(
        output / "latest_structural_rank_probe.json",
        evaluation_date=args.evaluation_date,
    )
    summary = {
        "status": captured["status"],
        "evidence_id": verified.evidence_id,
        "method_id": verified.method_id,
        "method_version": verified.method_version,
        "method_manifest_sha256": verified.method_manifest_sha256,
        "candidate_aligned_periods": verified.candidate_aligned_periods,
        "training_periods": verified.training_periods,
        "holdout_excluded_periods": verified.holdout_excluded_periods,
        "reconciliation_failed_periods": verified.reconciliation_failed_periods,
        "row_count": verified.row_count,
        "parameter_count": verified.parameter_count,
        "design_rank": verified.design_rank,
        "full_column_rank": verified.full_column_rank,
        "normalized_condition_number": verified.normalized_condition_number,
        "company_product_revenue_reconciliation_certified": (
            verified.company_product_revenue_reconciliation_certified
        ),
        "rank_probe_ready": verified.rank_probe_ready,
        "fit_attempt_allowed": verified.fit_attempt_allowed,
        "holdout_evaluation_allowed": verified.holdout_evaluation_allowed,
        "block_reason": verified.block_reason,
        "direction_encoding_numeric_source_fact": (
            verified.direction_encoding_numeric_source_fact
        ),
        "numeric_magnitude_assumed": verified.numeric_magnitude_assumed,
        "product_profitability_source_fact": verified.product_profitability_source_fact,
        "numeric_forecast_enabled": verified.numeric_forecast_enabled,
        "fair_value_estimate_enabled": verified.fair_value_estimate_enabled,
        "target_price_enabled": verified.target_price_enabled,
        "decision_score_enabled": verified.decision_score_enabled,
        "artifact_directory": captured["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
