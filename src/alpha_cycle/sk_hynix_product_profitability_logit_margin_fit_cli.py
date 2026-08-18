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
from .intelligence.sk_hynix_product_profitability_logit_margin_fit import (
    build_logit_margin_fit,
    load_logit_margin_training_rows,
)
from .intelligence.sk_hynix_product_profitability_logit_margin_method import (
    DEFAULT_LOGIT_MARGIN_METHOD,
    load_frozen_logit_margin_method,
)
from .intelligence.sk_hynix_product_profitability_regime_economic_audit import (
    DEFAULT_REGIME_TRAINING_FIT_POINTER,
)
from .intelligence.sk_hynix_product_profitability_regime_holdout import (
    DEFAULT_REGIME_HOLDOUT_POINTER,
    DEFAULT_REGIME_VALIDATION_OUTPUT,
)

DEFAULT_LOGIT_MARGIN_FIT_OUTPUT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v2_logit_margin_fit.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fit the frozen SK hynix v2 bounded logit-margin model using 15 v1 training "
            "rows plus the explicitly contaminated 2026Q1 development row. 2026Q3 is "
            "not loaded or evaluated."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--method", default=str(DEFAULT_LOGIT_MARGIN_METHOD))
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
    parser.add_argument("--output", default=str(DEFAULT_LOGIT_MARGIN_FIT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    method = load_frozen_logit_margin_method(Path(args.method))
    rows = load_logit_margin_training_rows(
        method,
        v1_training_pointer=Path(args.v1_training),
        v1_holdout_pointer=Path(args.v1_holdout),
        historical_product_revenue_pointer=Path(args.historical_product_revenue_pointer),
        company_profitability_pointer=Path(args.company_profitability_pointer),
        cycle_driver_pointer=Path(args.cycle_driver_pointer),
    )
    result = build_logit_margin_fit(method, rows, evaluation_date=args.evaluation_date)
    payload = {
        "schema_version": 1,
        "status": "skhynix_product_profitability_v2_logit_margin_fit_completed",
        "method_evidence_id": method.evidence_id,
        "result": asdict(result),
        "2026q1_is_contaminated_development_data": True,
        "2026q2_claimed_as_untouched_holdout": False,
        "2026q3_reserved_as_future_untouched_holdout": True,
        "2026q3_loaded": False,
        "2026q3_evaluated": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(output)
    summary = {
        "status": payload["status"],
        "method_version": method.method_version,
        "method_evidence_id": method.evidence_id,
        "row_count": result.row_count,
        "parameter_count": result.parameter_count,
        "residual_degrees_of_freedom": result.residual_degrees_of_freedom,
        "optimizer_converged": result.optimizer_converged,
        "optimizer_iterations": result.optimizer_iterations,
        "jacobian_rank": result.jacobian_rank,
        "full_jacobian_column_rank": result.full_jacobian_column_rank,
        "normalized_jacobian_condition_number": (
            result.normalized_jacobian_condition_number
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
        "development_gate_passed": result.development_gate_passed,
        "future_holdout_period": result.untouched_holdout_period,
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
