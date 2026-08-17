from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_product_profitability_promotion_readiness import (
    DEFAULT_PROMOTION_READINESS_OUTPUT,
    DEFAULT_PROMOTION_READINESS_POLICY,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_promotion_readiness_report import (
    capture_promotion_readiness_report,
    load_promotion_readiness_report,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_METHOD_PATH,
    DEFAULT_STRUCTURAL_RANK_PROBE_POINTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit SK hynix latent product-profitability promotion readiness without "
            "fitting a model, opening the holdout, forecasting, or valuing the issuer."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--rank-probe-pointer",
        default=str(DEFAULT_STRUCTURAL_RANK_PROBE_POINTER),
    )
    parser.add_argument("--policy", default=str(DEFAULT_PROMOTION_READINESS_POLICY))
    parser.add_argument("--method", default=str(DEFAULT_STRUCTURAL_METHOD_PATH))
    parser.add_argument("--output", default=str(DEFAULT_PROMOTION_READINESS_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    captured = capture_promotion_readiness_report(
        evaluation_date=args.evaluation_date,
        rank_probe_pointer=Path(args.rank_probe_pointer),
        policy_path=Path(args.policy),
        method_path=Path(args.method),
        output=output,
    )
    verified = load_promotion_readiness_report(
        output / "latest_promotion_readiness.json",
        evaluation_date=args.evaluation_date,
    )
    summary = {
        "status": captured["status"],
        "evidence_id": verified.evidence_id,
        "policy_id": verified.policy_id,
        "policy_version": verified.policy_version,
        "rank_probe_evidence_id": verified.rank_probe_evidence_id,
        "row_count": verified.row_count,
        "parameter_count": verified.parameter_count,
        "required_training_rows": verified.required_training_rows,
        "additional_training_rows_required": verified.additional_training_rows_required,
        "residual_degrees_of_freedom": verified.residual_degrees_of_freedom,
        "sample_depth_gate_passed": verified.sample_depth_gate_passed,
        "rank_probe_ready": verified.rank_probe_ready,
        "company_product_revenue_reconciliation_certified": (
            verified.company_product_revenue_reconciliation_certified
        ),
        "interval_driver_count": verified.interval_driver_count,
        "closed_interval_driver_count": verified.closed_interval_driver_count,
        "open_interval_source_texts": verified.open_interval_source_texts,
        "closed_interval_sensitivity_coverage_complete": (
            verified.closed_interval_sensitivity_coverage_complete
        ),
        "interval_sensitivity_design_full_rank": (
            verified.interval_sensitivity_design_full_rank
        ),
        "estimation_driver_input_ready": verified.estimation_driver_input_ready,
        "method_version_frozen": verified.method_version_frozen,
        "holdout_period": verified.holdout_period,
        "holdout_sealed": verified.holdout_sealed,
        "promotion_to_frozen_estimation_candidate_allowed": (
            verified.promotion_to_frozen_estimation_candidate_allowed
        ),
        "fit_attempt_allowed": verified.fit_attempt_allowed,
        "holdout_evaluation_allowed": verified.holdout_evaluation_allowed,
        "block_reasons": verified.block_reasons,
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
