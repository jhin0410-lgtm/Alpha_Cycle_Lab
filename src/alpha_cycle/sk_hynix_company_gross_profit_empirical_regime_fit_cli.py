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
from .intelligence.sk_hynix_company_gross_profit_empirical_regime_fit import (
    build_company_gp_empirical_fit,
    build_empirical_prefit_identification,
    load_company_gp_empirical_rows,
)
from .intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
    load_frozen_company_gp_empirical_method,
)
from .intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
)
from .intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_POINTER,
)
from .intelligence.sk_hynix_product_profitability_expanded_logit_margin_method import (
    DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD,
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

DEFAULT_COMPANY_GP_EMPIRICAL_FIT_OUTPUT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v5_company_gp_empirical_regime_fit.json"
)
DEFAULT_V4_FIT_REPORT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v4_reduced_identifiable_fit.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fit frozen SK hynix V5 empirical company-GP regime OLS on the clean 21-row "
            "panel. Product-margin structural interpretation is closed; 2026Q3 is sealed."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--method", default=str(DEFAULT_COMPANY_GP_EMPIRICAL_METHOD))
    parser.add_argument("--v3-method", default=str(DEFAULT_EXPANDED_LOGIT_MARGIN_METHOD))
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
    parser.add_argument("--v4-fit-report", default=str(DEFAULT_V4_FIT_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_COMPANY_GP_EMPIRICAL_FIT_OUTPUT))
    return parser


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _v4_comparison(path: Path, v5_mae: float) -> dict[str, object] | None:
    if not path.exists():
        return None
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("V4 comparison report must be an object")
    root = {str(key): value for key, value in cast(dict[object, object], raw).items()}
    result = root.get("result")
    if not isinstance(result, dict):
        raise ValueError("V4 comparison report lacks result object")
    item = {str(key): value for key, value in cast(dict[object, object], result).items()}
    v4_mae = float(str(item.get("loocv_mae_krw_million", "nan")))
    return {
        "v4_method_version": "4.0-frozen-pre-fit",
        "v4_loocv_mae_krw_million": v4_mae,
        "v5_loocv_mae_krw_million": v5_mae,
        "v5_minus_v4_loocv_mae_krw_million": v5_mae - v4_mae,
        "used_for_v5_gate": False,
        "report_only": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    method = load_frozen_company_gp_empirical_method(Path(args.method))
    frontier = load_third_wave_frontier(Path(args.frontier))
    closeout = run_third_wave_closeout(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=args.evaluation_date,
        product_output=Path(args.product_output),
        company_output=Path(args.company_output),
    )
    rows, contaminated_q1 = load_company_gp_empirical_rows(
        method,
        closeout,
        frontier,
        v3_method_path=Path(args.v3_method),
        v2_method_path=Path(args.v2_method),
        v1_training_pointer=Path(args.v1_training),
        v1_holdout_pointer=Path(args.v1_holdout),
        historical_product_revenue_pointer=Path(args.historical_product_revenue_pointer),
        company_profitability_pointer=Path(args.company_profitability_pointer),
        cycle_driver_pointer=Path(args.cycle_driver_pointer),
    )
    prefit = build_empirical_prefit_identification(method, rows)
    output = Path(args.output)
    if not prefit.prefit_gate_passed:
        payload: dict[str, object] = {
            "schema_version": 1,
            "status": "skhynix_company_gp_empirical_v5_prefit_gate_failed",
            "method_version": method.method_version,
            "method_evidence_id": method.evidence_id,
            "prefit_identification": asdict(prefit),
            "fit_attempted": False,
            "product_margin_structural_interpretation_allowed": False,
            "product_margin_output_enabled": False,
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

    result = build_company_gp_empirical_fit(
        method,
        rows,
        contaminated_q1,
        evaluation_date=args.evaluation_date,
    )
    comparison = _v4_comparison(Path(args.v4_fit_report), result.loocv_mae_krw_million)
    payload = {
        "schema_version": 1,
        "status": "skhynix_company_gp_empirical_v5_fit_completed",
        "method_evidence_id": method.evidence_id,
        "result": asdict(result),
        "v4_performance_comparison_report_only": comparison,
        "fit_attempted": True,
        "2026q1_is_contaminated_stress_only": True,
        "2026q1_used_for_fit": False,
        "2026q1_used_for_model_selection_gate": False,
        "2026q1_claimed_as_independent_holdout": False,
        "2026q3_reserved_as_future_untouched_holdout": True,
        "2026q3_loaded": False,
        "2026q3_evaluated": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "product_margin_structural_interpretation_allowed": False,
        "product_margin_output_enabled": False,
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
        "design_rank": result.design_rank,
        "full_design_column_rank": result.full_design_column_rank,
        "normalized_condition_number_report_only": (
            result.normalized_condition_number_report_only
        ),
        "coefficients": {
            name: value
            for name, value in zip(method.parameters, result.coefficients, strict=True)
        },
        "coefficient_interpretation": result.coefficient_interpretation,
        "in_sample_mae_krw_million": result.in_sample_mae_krw_million,
        "in_sample_rmse_krw_million": result.in_sample_rmse_krw_million,
        "in_sample_r_squared_report_only": result.in_sample_r_squared_report_only,
        "all_loocv_designs_full_rank": result.all_loocv_designs_full_rank,
        "loocv_mae_krw_million": result.loocv_mae_krw_million,
        "benchmark_loocv_mae_krw_million": result.benchmark_loocv_mae_krw_million,
        "loocv_beats_benchmark": result.loocv_beats_benchmark,
        "parameter_jackknife_report_only": [
            asdict(item) for item in result.parameter_jackknife_report_only
        ],
        "contaminated_2026q1_stress_report_only": asdict(
            result.contaminated_q1_stress_report_only
        ),
        "v4_performance_comparison_report_only": comparison,
        "development_gate_passed": result.development_gate_passed,
        "product_margin_structural_interpretation_allowed": False,
        "product_margin_output_enabled": False,
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
