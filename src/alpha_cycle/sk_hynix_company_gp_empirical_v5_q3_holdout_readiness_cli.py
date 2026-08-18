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
from .intelligence.sk_hynix_company_gp_empirical_regime_fit import (
    load_company_gp_empirical_rows,
)
from .intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout import (
    DEFAULT_V5_Q3_HOLDOUT_BINDING,
    build_v5_q3_validation_binding,
    persist_v5_q3_validation_binding,
)
from .intelligence.sk_hynix_company_gp_empirical_v5_q3_holdout_protocol import (
    DEFAULT_V5_Q3_HOLDOUT_PROTOCOL,
    load_frozen_v5_q3_holdout_protocol,
)
from .intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    DEFAULT_COMPANY_GP_EMPIRICAL_METHOD,
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

DEFAULT_V5_FIT_REPORT = (
    DEFAULT_REGIME_VALIDATION_OUTPUT / "latest_v5_company_gp_empirical_regime_fit.json"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind the already-passed frozen SK hynix V5 development fit to the "
            "frozen 2026Q3 prospective holdout protocol without loading or "
            "evaluating any Q3 data."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--protocol", default=str(DEFAULT_V5_Q3_HOLDOUT_PROTOCOL))
    parser.add_argument("--method", default=str(DEFAULT_COMPANY_GP_EMPIRICAL_METHOD))
    parser.add_argument("--fit-report", default=str(DEFAULT_V5_FIT_REPORT))
    parser.add_argument("--binding-output", default=str(DEFAULT_V5_Q3_HOLDOUT_BINDING))
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    protocol, method = load_frozen_v5_q3_holdout_protocol(
        Path(args.protocol),
        method_path=Path(args.method),
    )
    if args.evaluation_date != protocol.bound_fit_evaluation_date:
        raise ValueError("V5 Q3 readiness must reproduce the frozen 2026-08-18 V5 fit")
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
        historical_product_revenue_pointer=Path(
            args.historical_product_revenue_pointer
        ),
        company_profitability_pointer=Path(args.company_profitability_pointer),
        cycle_driver_pointer=Path(args.cycle_driver_pointer),
    )
    binding = build_v5_q3_validation_binding(
        protocol,
        method,
        Path(args.fit_report),
        rows,
        contaminated_q1,
    )
    output = persist_v5_q3_validation_binding(
        binding,
        Path(args.binding_output),
    )
    summary = {
        "status": (
            "skhynix_v5_q3_holdout_readiness_bound_without_holdout_exposure"
        ),
        "protocol_version": protocol.protocol_version,
        "protocol_evidence_id": protocol.evidence_id,
        "method_evidence_id": method.evidence_id,
        "fit_evidence_id": binding.fit_evidence_id,
        "fit_evaluation_date": binding.fit_evaluation_date.isoformat(),
        "development_gate_passed": binding.development_gate_passed,
        "training_fit_reproduced_exactly": (
            binding.training_fit_reproduced_exactly
        ),
        "training_row_count": len(binding.training_periods),
        "training_mean_company_gross_margin_report_only": (
            binding.training_mean_company_gross_margin
        ),
        "training_snapshot_hash": binding.training_snapshot_hash,
        "binding_evidence_id": binding.evidence_id,
        "holdout_period": protocol.holdout_period,
        "2026q3_source_loaded": False,
        "2026q3_target_read": False,
        "2026q3_evaluated": False,
        "one_time_scoring_pre_authorized_after_certified_bundle": True,
        "requires_explicit_certified_source_bundle": True,
        "product_margin_structural_branch_closed": True,
        "product_margin_structural_interpretation_allowed": False,
        "validates_pre_earnings_forecastability": False,
        "ex_ante_forecasting_layer_still_required": True,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "binding_path": str(output.resolve()),
        "binding": asdict(binding),
    }
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
