from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_historical_evaluation import (
    DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION,
    DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT,
    run_first_historical_evaluation,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Perform the first SK hynix exact-20-period historical target join and the "
            "preregistered 12-to-8 chronological backtest. Protected 2026Q3 is not read."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--execution",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_EXECUTION),
    )
    parser.add_argument(
        "--scope",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE),
    )
    parser.add_argument(
        "--bundle",
        default=str(DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE),
    )
    parser.add_argument(
        "--estimator-freeze",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_HISTORICAL_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    join, result, reused = run_first_historical_evaluation(
        OpenDartReadOnlyClient.from_env(),
        evaluation_date=args.evaluation_date,
        execution_path=Path(args.execution),
        scope_path=Path(args.scope),
        bundle_path=Path(args.bundle),
        estimator_path=Path(args.estimator_freeze),
        output=Path(args.output),
    )
    candidates = []
    for candidate in result.candidates:
        candidates.append(
            {
                "candidate_id": candidate.candidate_id,
                "parameter_count": candidate.parameter_count,
                "predictors": list(candidate.predictors),
                "every_fold_valid": candidate.every_fold_valid,
                "aggregate_mae_krw_million": candidate.aggregate_mae_krw_million,
                "strictly_beats_benchmark": candidate.strictly_beats_benchmark,
                "max_standardized_coefficient_delta_l2": (
                    candidate.max_standardized_coefficient_delta_l2
                ),
                "folds": [
                    {
                        "fold_number": fold.fold_number,
                        "score_period": fold.score_period,
                        "training_row_count": fold.training_row_count,
                        "prediction_krw_million": fold.prediction_krw_million,
                        "absolute_error_krw_million": fold.absolute_error_krw_million,
                        "design_rank": fold.design_rank,
                        "residual_degrees_of_freedom": (
                            fold.residual_degrees_of_freedom
                        ),
                        "condition_number": fold.condition_number,
                        "valid": fold.valid,
                        "failure_reason": fold.failure_reason,
                    }
                    for fold in candidate.folds
                ],
            }
        )
    next_action = (
        "freeze_selected_estimator_on_full_twenty_row_scope_before_prospective_forecast"
        if result.selected_candidate_id is not None
        else "keep_forward_forecast_disabled_and_start_only_a_new_preregistered_research_round"
    )
    payload = {
        "status": result.status,
        "target_join_status": join.status,
        "target_join_evidence_id": join.evidence_id,
        "target_source_evidence_id": join.target_source_evidence_id,
        "backtest_evidence_id": result.evidence_id,
        "execution_evidence_id": result.execution_evidence_id,
        "scope_evidence_id": result.scope_evidence_id,
        "estimator_freeze_evidence_id": result.estimator_freeze_evidence_id,
        "evaluation_date": join.evaluation_date.isoformat(),
        "locked_target_reused": reused,
        "target_period_count": len(join.target_periods),
        "target_periods": list(join.target_periods),
        "target_receipts": {
            item.period_id: item.receipt_no for item in join.target_observations
        },
        "historical_target_values_read": result.historical_target_values_read,
        "target_join_run": result.target_join_run,
        "estimator_fit_run": result.estimator_fit_run,
        "historical_backtest_run": result.historical_backtest_run,
        "benchmark_id": result.benchmark_id,
        "benchmark_mae_krw_million": result.benchmark_mae_krw_million,
        "benchmark_folds": [
            {
                "fold_number": fold.fold_number,
                "score_period": fold.score_period,
                "training_row_count": fold.training_row_count,
                "actual_krw_million": fold.actual_krw_million,
                "prediction_krw_million": fold.prediction_krw_million,
                "absolute_error_krw_million": fold.absolute_error_krw_million,
            }
            for fold in result.benchmark_folds
        ],
        "candidates": candidates,
        "selected_candidate_id": result.selected_candidate_id,
        "selection_status": result.selection_status,
        "final_estimator_selected": result.final_estimator_selected,
        "2026q1_used_for_selection": result.q1_used_for_selection,
        "2026q3_target_read": result.q3_target_read,
        "2026q3_source_outcome_loaded": result.q3_source_outcome_loaded,
        "2026q3_evaluated": result.q3_evaluated,
        "numeric_forward_forecast_enabled": result.numeric_forward_forecast_enabled,
        "next_action": next_action,
        "output": str(Path(args.output)),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
