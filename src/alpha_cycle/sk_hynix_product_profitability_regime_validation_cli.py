from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import cast

from .intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from .intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from .intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from .intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    DEFAULT_REGIME_ESTIMATION_METHOD,
    load_frozen_regime_estimation_method,
)
from .intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_VALIDATION_OUTPUT,
    spend_regime_holdout_once,
)
from .intelligence.sk_hynix_product_profitability_regime_training_fit import (
    build_regime_training_fit,
)
from .intelligence.sk_hynix_product_profitability_regime_validation_protocol import (
    load_regime_validation_protocol,
)
from .intelligence.sk_hynix_product_profitability_second_wave_acquisition import (
    DEFAULT_SECOND_WAVE_COMPANY_OUTPUT,
    DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT,
)
from .intelligence.sk_hynix_product_profitability_second_wave_closeout import (
    run_second_wave_closeout,
)
from .intelligence.sk_hynix_product_profitability_second_wave_frontier import (
    DEFAULT_SECOND_WAVE_FRONTIER,
    load_second_wave_frontier,
)
from .intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_RANK_PROBE_POINTER,
)
from .intelligence.sk_hynix_product_profitability_structural_rank_probe_report import (
    load_structural_rank_probe_report,
)
from .providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen SK hynix 15-row direction-regime OLS training diagnostics. "
            "If and only if the pre-registered training gate passes, score the 2026Q1 "
            "holdout once and persist an immutable result."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--method", default=str(DEFAULT_REGIME_ESTIMATION_METHOD))
    parser.add_argument("--frontier", default=str(DEFAULT_SECOND_WAVE_FRONTIER))
    parser.add_argument("--product-output", default=str(DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT))
    parser.add_argument("--company-output", default=str(DEFAULT_SECOND_WAVE_COMPANY_OUTPUT))
    parser.add_argument("--rank-probe-pointer", default=str(DEFAULT_STRUCTURAL_RANK_PROBE_POINTER))
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
    parser.add_argument("--output", default=str(DEFAULT_REGIME_VALIDATION_OUTPUT))
    return parser


def _pointer_evaluation_date(path: Path) -> date:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Structural rank-probe pointer is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Structural rank-probe pointer is invalid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("Structural rank-probe pointer must be an object")
    payload = {str(key): value for key, value in cast(dict[object, object], raw).items()}
    return date.fromisoformat(str(payload.get("evaluation_date", "")))


def _write_training_fit(output: Path, payload: dict[str, object]) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / "latest_training_fit.json"
    temporary = output / ".latest_training_fit.json.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evaluation_date = args.evaluation_date
    method_path = Path(args.method)
    method = load_frozen_regime_estimation_method(method_path)
    protocol = load_regime_validation_protocol(method, method_path)
    frontier = load_second_wave_frontier(Path(args.frontier))
    closeout = run_second_wave_closeout(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=evaluation_date,
        product_output=Path(args.product_output),
        company_output=Path(args.company_output),
    )
    rank_pointer = Path(args.rank_probe_pointer)
    source_evaluation_date = _pointer_evaluation_date(rank_pointer)
    base_rank = load_structural_rank_probe_report(
        rank_pointer,
        evaluation_date=source_evaluation_date,
    )
    training = build_regime_training_fit(
        method,
        base_rank,
        closeout,
        frontier,
        evaluation_date=evaluation_date,
    )
    output = Path(args.output)
    training_payload = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_regime_training_fit_completed",
        "method_evidence_id": method.evidence_id,
        "method_version": method.method_version,
        "source_evaluation_date": source_evaluation_date.isoformat(),
        "result": asdict(training),
        "holdout_scored": False,
        "refit_after_holdout_allowed": False,
    }
    training_path = _write_training_fit(output, training_payload)

    holdout = None
    holdout_reused = False
    holdout_error = None
    if training.one_time_holdout_evaluation_ready:
        try:
            holdout, holdout_reused = spend_regime_holdout_once(
                method,
                protocol,
                training,
                source_evaluation_date=source_evaluation_date,
                historical_product_revenue_pointer=Path(
                    args.historical_product_revenue_pointer
                ),
                company_profitability_pointer=Path(args.company_profitability_pointer),
                cycle_driver_pointer=Path(args.cycle_driver_pointer),
                output=output,
            )
        except ValueError as exc:
            holdout_error = str(exc)

    coefficient_map = {
        parameter: value
        for parameter, value in zip(
            method.parameters,
            training.coefficients,
            strict=True,
        )
    }
    stability = {
        item.parameter: {
            "full_fit_value": item.full_fit_value,
            "leave_one_out_min": item.leave_one_out_min,
            "leave_one_out_max": item.leave_one_out_max,
            "sign_stability_ratio": item.sign_stability_ratio,
        }
        for item in training.coefficient_stability
    }
    holdout_summary = None
    if holdout is not None:
        holdout_summary = {
            "evidence_id": holdout.evidence_id,
            "period": holdout.holdout_period,
            "actual_gross_profit_krw_million": holdout.actual_gross_profit_krw_million,
            "model_prediction_krw_million": holdout.model_prediction_krw_million,
            "model_absolute_error_krw_million": holdout.model_absolute_error_krw_million,
            "benchmark_prediction_krw_million": holdout.benchmark_prediction_krw_million,
            "benchmark_absolute_error_krw_million": (
                holdout.benchmark_absolute_error_krw_million
            ),
            "model_beats_benchmark": holdout.model_beats_benchmark,
            "holdout_validation_passed": holdout.holdout_validation_passed,
            "reused_existing_immutable_result": holdout_reused,
            "refit_after_holdout_allowed": False,
        }

    if not training.training_gate_passed:
        next_action = "reject_frozen_v1_before_holdout_without_scoring_2026q1"
    elif holdout is None:
        next_action = "resolve_holdout_execution_integrity_error_without_refitting_v1"
    elif holdout.holdout_validation_passed:
        next_action = (
            "accept_frozen_v1_as_validated_regime_model_then_review_margin_plausibility_"
            "before_any_forward_forecast_contract"
        )
    else:
        next_action = "reject_frozen_v1_for_forward_use_without_refitting_to_2026q1"

    summary = {
        "status": "skhynix_product_profitability_regime_validation_completed",
        "method_id": method.method_id,
        "method_version": method.method_version,
        "method_evidence_id": method.evidence_id,
        "method_version_frozen": method.method_version_frozen,
        "driver_semantics": method.driver_encoding.semantics,
        "exact_numeric_second_wave_magnitude_used_for_fit": (
            method.driver_encoding.exact_numeric_second_wave_magnitude_used_for_fit
        ),
        "training": {
            "evidence_id": training.evidence_id,
            "row_count": training.row_count,
            "parameter_count": training.parameter_count,
            "residual_degrees_of_freedom": training.residual_degrees_of_freedom,
            "design_rank": training.design_rank,
            "full_column_rank": training.full_column_rank,
            "normalized_condition_number": training.normalized_condition_number,
            "coefficients": coefficient_map,
            "in_sample_mae_krw_million": training.in_sample_mae_krw_million,
            "in_sample_rmse_krw_million": training.in_sample_rmse_krw_million,
            "in_sample_r2": training.in_sample_r2,
            "loocv_mae_krw_million": training.loocv_mae_krw_million,
            "benchmark_loocv_mae_krw_million": training.benchmark_loocv_mae_krw_million,
            "loocv_beats_benchmark": training.loocv_beats_benchmark,
            "all_loocv_folds_full_rank": training.all_loocv_folds_full_rank,
            "max_leverage": training.max_leverage,
            "max_cooks_distance": training.max_cooks_distance,
            "coefficient_stability": stability,
            "training_gate_passed": training.training_gate_passed,
            "one_time_holdout_evaluation_ready": (
                training.one_time_holdout_evaluation_ready
            ),
            "holdout_loaded_by_training_fit": training.holdout_loaded,
            "holdout_evaluated_by_training_fit": training.holdout_evaluated,
        },
        "holdout": holdout_summary,
        "holdout_error": holdout_error,
        "training_fit_report_path": str(training_path.resolve()),
        "refit_after_holdout_allowed": False,
        "product_profitability_is_direct_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "next_action": next_action,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
