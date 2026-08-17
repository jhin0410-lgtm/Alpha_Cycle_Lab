from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    DEFAULT_REGIME_ESTIMATION_METHOD,
)
from .intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
)
from .intelligence.sk_hynix_product_profitability_regime_post_validation_audit import (
    DEFAULT_POST_VALIDATION_AUDIT_OUTPUT,
    DEFAULT_POST_VALIDATION_AUDIT_POLICY,
    DEFAULT_REGIME_TRAINING_FIT_POINTER,
    build_regime_v1_post_validation_audit,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the already-spent SK hynix regime-v1 validation result for structural "
            "gross-margin plausibility without refitting v1 or re-scoring the holdout."
        )
    )
    parser.add_argument("--method", default=str(DEFAULT_REGIME_ESTIMATION_METHOD))
    parser.add_argument("--policy", default=str(DEFAULT_POST_VALIDATION_AUDIT_POLICY))
    parser.add_argument("--training-fit", default=str(DEFAULT_REGIME_TRAINING_FIT_POINTER))
    parser.add_argument("--holdout", default=str(DEFAULT_REGIME_HOLDOUT_POINTER))
    parser.add_argument("--output", default=str(DEFAULT_POST_VALIDATION_AUDIT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = build_regime_v1_post_validation_audit(
        method_path=Path(args.method),
        policy_path=Path(args.policy),
        training_fit_path=Path(args.training_fit),
        holdout_path=Path(args.holdout),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_regime_v1_post_validation_audited",
        "result": asdict(result),
        "refit_v1_after_holdout_allowed": False,
        "reuse_2026q1_as_unseen_holdout_for_v2_allowed": False,
    }
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(wrapper, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(output)

    if result.predictive_validation_passed and not result.structural_margin_interpretation_passed:
        next_action = (
            "preserve_v1_as_predictive_validation_evidence_only_then_open_v2_"
            "identification_frontier_without_refitting_v1"
        )
    elif result.forward_forecast_contract_review_allowed:
        next_action = "review_forward_input_contract_without_enabling_target_price"
    else:
        next_action = "stop_v1_forward_use_and_preserve_immutable_validation_evidence"

    summary = {
        "status": wrapper["status"],
        "evidence_id": result.evidence_id,
        "model_status": result.model_status,
        "predictive_validation_passed": result.predictive_validation_passed,
        "structural_margin_interpretation_passed": (
            result.structural_margin_interpretation_passed
        ),
        "forward_forecast_contract_review_allowed": (
            result.forward_forecast_contract_review_allowed
        ),
        "dram": {
            "minimum_implied_margin_ratio": (
                result.dram_margin_envelope.minimum_implied_margin_ratio
            ),
            "maximum_implied_margin_ratio": (
                result.dram_margin_envelope.maximum_implied_margin_ratio
            ),
            "upper_bound_violation_count": (
                result.dram_margin_envelope.upper_bound_violation_count
            ),
            "upper_bound_violation_regimes": (
                result.dram_margin_envelope.upper_bound_violation_regimes
            ),
            "observed_upper_bound_violation_periods": (
                result.dram_margin_envelope.observed_upper_bound_violation_periods
            ),
        },
        "nand": {
            "minimum_implied_margin_ratio": (
                result.nand_margin_envelope.minimum_implied_margin_ratio
            ),
            "maximum_implied_margin_ratio": (
                result.nand_margin_envelope.maximum_implied_margin_ratio
            ),
            "upper_bound_violation_count": (
                result.nand_margin_envelope.upper_bound_violation_count
            ),
            "upper_bound_violation_regimes": (
                result.nand_margin_envelope.upper_bound_violation_regimes
            ),
            "observed_upper_bound_violation_periods": (
                result.nand_margin_envelope.observed_upper_bound_violation_periods
            ),
        },
        "other_margin_constant": result.other_margin_constant,
        "other_margin_absolute_value_gt_one_report_only": (
            result.other_margin_absolute_value_gt_one_report_only
        ),
        "max_leverage_report_only": result.max_leverage_report_only,
        "max_cooks_distance_report_only": result.max_cooks_distance_report_only,
        "coefficient_jackknife_report_only": result.coefficient_jackknife_report_only,
        "refit_v1_after_holdout_allowed": False,
        "reuse_2026q1_as_unseen_holdout_for_v2_allowed": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "audit_report_path": str(output.resolve()),
        "next_action": next_action,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
