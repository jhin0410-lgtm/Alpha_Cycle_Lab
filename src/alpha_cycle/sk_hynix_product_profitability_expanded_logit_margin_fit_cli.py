from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_POINTER,
)
from .intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from .intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from .intelligence.sk_hynix_product_profitability_expanded_logit_margin_fit import (
    build_expanded_logit_margin_fit,
    build_expanded_prefit_identification,
    load_expanded_logit_margin_rows,
)
from .intelligence.sk_hynix_product_profitability_expanded_logit_margin_method import (
    DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD,
    load_frozen_expanded_logit_margin_method,
)
from .intelligence.sk_hynix_product_profitability_logit_margin_method import (
    DEFAULT_LOGIT_MARGIN_METHOD,
)
from .intelligence.sk_hynix_product_profitability_regime_economic_audit import (
    DEFAULT_REGIME_TRAINING_FIT_POINTER,
)
from .intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
    DEFAULT_REGIME_VALIDATION_OUTPUT,
)
from .intelligence.sk_hynix_product_profitability_third_wave_closeout import (
    DEFAULT_THIRD_WAVE_COMPANY_OUTPUT,
    DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT,
    run_third_wave_closeout,
)
from .intelligence.sk_hynix_product_profitability_third_wave_frontier import (
    DEFAULT_THIRD_WAVE_FRONTIER,
    load_third_wave_frontier,
)
from .providers.opendart import OpenDartReadOnlyClient

DEFAULT_EXPANDED_LOGIT_MARGIN_FIT_OUTPUT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v3_expanded_logit_margin_fit.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fit the frozen SK hynix v3 bounded logit-margin model on the clean 21-row "
            "historical panel only. 2026Q1 is report-only contaminated stress data. "
            "2026Q3 is never loaded or evaluated."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--method", default=str(DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD))
    parser.add_argument("--v2-method", default=str(DEFAULT_LOGIT_MARGIN_METHOD))
    parser.add_argument("--frontier", default=str(DEFAULT_THIRD_WAVE_FRONTIER))
    parser.add_argument("--product-output", default=str(DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT))
    parser.add_argument("--company-output", default=str(DEFAULT_THIRD_WAVE_COMPANY_OUTPUT))
    parser.add_argument("--v1-training", default=str(DEFAULT_REGIME_TRAINING_FIT_POINTER))
    parser.add_argument("--v1-holdout", default=str(DEFAULT_REGIME_HOLDOUT_POINTER))
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
    parser.add_argument("--output", default=str(DEFAULT_EXPANDED_LOGIT_MARGIN_FIT_OUTPUT))
    return parser


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evaluation_date = args.evaluation_date
    method = load_frozen_expanded_logit_margin_method(Path(args.method))
    frontier = load_third_wave_frontier(Path(args.frontier))
    closeout = run_third_wave_closeout(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=evaluation_date,
        product_output=Path(args.product_output),
        company_output=Path(args.company_output),
    )
    rows, contaminated_q1 = load_expanded_logit_margin_rows(
        method,
        closeout,
        frontier,
        v2_method_path=Path(args.v2_method),
        v1_training_pointer=Path(args.v1_training),
        v1_holdout_pointer=Path(args.v1_holdout),
        historical_product_revenue_pointer=Path(args.historical_product_revenue_pointer),
        company_profitability_pointer=Path(args.company_profitability_pointer),
        cycle_driver_pointer=Path(args.cycle_driver_pointer),
    )
    prefit = build_expanded_prefit_identification(method, rows)
    output = Path(args.output)
    if not prefit.prefit_gate_passed:
        payload: dict[str, object] = {
            "schema_version": 1,
            "status": "skhynix_product_profitability_v3_prefit_gate_failed",
            "method_version": method.method_version,
            "method_evidence_id": method.evidence_id,
            "prefit_identification": asdict(prefit),
            "fit_attempted": False,
            "2026q1_used_for_fit": False,
            "2026q1_used_for_model_selection_gate": False,
            "2026q3_reserved_as_future_untouched_holdout": True,
            "2026q3_loaded": False,
            "2026q3_evaluated": False,
            "numeric_forward_forecast_enabled": False,
            "target_price_enabled": False,
            "decision_score_enabled": False,
        }
        _write(output, payload)
        payload["report_path"] = str(output.resolve())
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
        return 0

    result = build_expanded_logit_margin_fit(
        method,
        rows,
        contaminated_q1,
        evaluation_date=evaluation_date,
    )
    payload = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_v3_expanded_logit_margin_fit_completed",
        "method_evidence_id": method.evidence_id,
        "result": asdict(result),
        "fit_attempted": True,
        "2026q1_is_contaminated_stress_only": True,
        "2026q1_used_for_fit": False,
        "2026q1_used_for_model_selection_gate": False,
        "2026q1_claimed_as_independent_holdout": False,
        "2026q2_claimed_as_untouched_holdout": False,
        "2026q3_reserved_as_future_untouched_holdout": True,
        "2026q3_loaded": False,
        "2026q3_evaluated": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    _write(output, payload)
    summary = {
        "status": payload["status"],
        "method_version": method.method_version,
        "method_evidence_id": method.evidence_id,
        "row_count": result.row_count,
        "parameter_count": result.parameter_count,
        "residual_degrees_of_freedom": result.residual_degrees_of_freedom,
        "prefit_identification": asdict(result.prefit_identification),
        "optimizer_converged": result.optimizer_converged,
        "optimizer_iterations": result.optimizer_iterations,
        "jacobian_rank": result.jacobian_rank,
        "full_jacobian_column_rank": result.full_jacobian_column_rank,
        "normalized_jacobian_condition_number_report_only": (
            result.normalized_jacobian_condition_number_report_only
        ),
        "parameters": {
            name: value
            for name, value in zip(method.parameters, result.parameters, strict=True)
        },
        "in_sample_mae_krw_million": result.in_sample_mae_krw_million,
        "in_sample_rmse_krw_million": result.in_sample_rmse_krw_million,
        "all_loocv_folds_converged": result.all_loocv_folds_converged,
        "all_loocv_jacobians_full_rank": result.all_loocv_jacobians_full_rank,
        "loocv_mae_krw_million": result.loocv_mae_krw_million,
        "benchmark_loocv_mae_krw_million": result.benchmark_loocv_mae_krw_million,
        "loocv_beats_benchmark": result.loocv_beats_benchmark,
        "dram_margin_envelope": asdict(result.dram_margin_envelope),
        "nand_margin_envelope": asdict(result.nand_margin_envelope),
        "other_margin": result.other_margin,
        "all_component_margins_inside_unit_interval": (
            result.all_component_margins_inside_unit_interval
        ),
        "parameter_jackknife_report_only": [
            asdict(item) for item in result.parameter_jackknife_report_only
        ],
        "contaminated_2026q1_stress_report_only": asdict(
            result.contaminated_q1_stress_report_only
        ),
        "development_gate_passed": result.development_gate_passed,
        "future_holdout_period": result.future_holdout_period,
        "future_holdout_evaluation_allowed": result.future_holdout_evaluation_allowed,
        "2026q3_loaded": False,
        "2026q3_evaluated": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "report_path": str(output.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
