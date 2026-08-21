from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_selected_estimator_freeze import (
    DEFAULT_SELECTED_ESTIMATOR_FULL_FIT_CONTRACT,
    DEFAULT_SELECTED_ESTIMATOR_OUTPUT,
    freeze_selected_estimator_from_locked_artifacts,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze the historically selected SK hynix company-GP estimator on the exact "
            "twenty locked historical rows without reading protected 2026Q3 outcomes."
        )
    )
    parser.add_argument(
        "--contract",
        default=str(DEFAULT_SELECTED_ESTIMATOR_FULL_FIT_CONTRACT),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SELECTED_ESTIMATOR_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    item, pointer, reused = freeze_selected_estimator_from_locked_artifacts(
        contract_path=Path(args.contract),
        output=Path(args.output),
    )
    payload = {
        "status": item.status,
        "selected_estimator_evidence_id": item.evidence_id,
        "contract_evidence_id": item.contract_evidence_id,
        "execution_evidence_id": item.execution_evidence_id,
        "scope_evidence_id": item.scope_evidence_id,
        "combined_bundle_evidence_id": item.combined_bundle_evidence_id,
        "target_join_evidence_id": item.target_join_evidence_id,
        "target_source_evidence_id": item.target_source_evidence_id,
        "raw_target_capture_evidence_id": item.raw_target_capture_evidence_id,
        "backtest_evidence_id": item.backtest_evidence_id,
        "estimator_freeze_evidence_id": item.estimator_freeze_evidence_id,
        "selected_candidate_id": item.selected_candidate_id,
        "estimator": item.estimator,
        "parameter_count": item.parameter_count,
        "predictors": list(item.predictors),
        "training_row_count": item.training_row_count,
        "training_periods": list(item.training_periods),
        "scaling_ddof": item.scaling_ddof,
        "predictor_means": list(item.predictor_means),
        "predictor_scales": list(item.predictor_scales),
        "standardized_coefficients": list(item.standardized_coefficients),
        "raw_unit_intercept": item.raw_unit_intercept,
        "raw_unit_coefficients": list(item.raw_unit_coefficients),
        "design_rank": item.design_rank,
        "residual_degrees_of_freedom": item.residual_degrees_of_freedom,
        "condition_number": item.condition_number,
        "training_mae_krw_million": item.training_mae_krw_million,
        "training_rmse_krw_million": item.training_rmse_krw_million,
        "historical_benchmark_mae_krw_million": (
            item.historical_benchmark_mae_krw_million
        ),
        "historical_selected_candidate_mae_krw_million": (
            item.historical_selected_candidate_mae_krw_million
        ),
        "historical_relative_mae_improvement": (
            item.historical_relative_mae_improvement
        ),
        "artifact_reused": reused,
        "prospective_feature_vector_frozen": item.prospective_feature_vector_frozen,
        "prospective_forecast_run": item.prospective_forecast_run,
        "2026q1_used_for_selection": item.q1_used_for_selection,
        "2026q3_target_read": item.q3_target_read,
        "2026q3_source_outcome_loaded": item.q3_source_outcome_loaded,
        "2026q3_evaluated": item.q3_evaluated,
        "numeric_forward_forecast_enabled": item.numeric_forward_forecast_enabled,
        "next_action": (
            "freeze_2026q3_prospective_feature_vector_without_reading_2026q3_outcome"
        ),
        "output": str(pointer),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
