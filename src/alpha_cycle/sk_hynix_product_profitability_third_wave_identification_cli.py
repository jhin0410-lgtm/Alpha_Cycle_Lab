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
from .intelligence.sk_hynix_product_profitability_third_wave_identification import (
    build_third_wave_identification_preflight,
)
from .providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire the SK hynix 2017Q1-2018Q3 exact-driver source frontier and, only when "
            "all six source layers are certified, run a 21-row clean / 22-row contaminated "
            "direction-design identification preflight. This command never fits a replacement "
            "estimator and never loads the reserved 2026Q3 holdout."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--frontier", default=str(DEFAULT_THIRD_WAVE_FRONTIER))
    parser.add_argument("--product-output", default=str(DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT))
    parser.add_argument("--company-output", default=str(DEFAULT_THIRD_WAVE_COMPANY_OUTPUT))
    parser.add_argument("--v2-method", default=str(DEFAULT_LOGIT_MARGIN_METHOD))
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
    evaluation_date = args.evaluation_date
    product_output = Path(args.product_output)
    company_output = Path(args.company_output)
    frontier = load_third_wave_frontier(Path(args.frontier))
    closeout = run_third_wave_closeout(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=evaluation_date,
        product_output=product_output,
        company_output=company_output,
    )

    preflight = None
    preflight_error = None
    if closeout.all_six_source_layers_complete:
        try:
            method = load_frozen_logit_margin_method(Path(args.v2_method))
            base_rows = load_logit_margin_training_rows(
                method,
                v1_training_pointer=Path(args.v1_training),
                v1_holdout_pointer=Path(args.v1_holdout),
                historical_product_revenue_pointer=Path(
                    args.historical_product_revenue_pointer
                ),
                company_profitability_pointer=Path(args.company_profitability_pointer),
                cycle_driver_pointer=Path(args.cycle_driver_pointer),
            )
            preflight = build_third_wave_identification_preflight(
                evaluation_date=evaluation_date,
                base_v2_rows=base_rows,
                closeout=closeout,
                frontier=frontier,
                product_output=product_output,
            )
        except ValueError as exc:
            preflight_error = str(exc)

    periods = [
        {
            "period_id": item.period_id,
            "driver_numeric_source_certified": item.driver_numeric_source_certified,
            "company_profitability_verified": item.company_profitability_verified,
            "company_recovery_used": item.company_recovery is not None,
            "product_revenue_certified": item.product_revenue_certified,
            "product_recovery_used": item.product_recovery is not None,
            "source_layer_complete": item.source_layer_complete,
            "company_error": item.company_error,
            "product_error": item.product_error,
        }
        for item in closeout.source.periods
    ]

    if not closeout.all_six_source_layers_complete:
        next_action = "resolve_only_failed_2017_2018_source_layers_then_replay_same_command"
    elif preflight_error is not None:
        next_action = "repair_identification_preflight_integrity_without_fitting_a_model"
    elif preflight is None:
        next_action = "inspect_missing_identification_preflight_result"
    elif preflight.preflight_ready_for_new_method_registration:
        next_action = (
            "preregister_replacement_estimator_on_expanded_panel_before_any_new_fit_"
            "while_keeping_2026q3_sealed"
        )
    else:
        next_action = (
            "reduce_or_reparameterize_structural_family_before_any_new_fit_"
            "while_keeping_2026q3_sealed"
        )

    payload = {
        "status": "skhynix_product_profitability_third_wave_identification_completed",
        "evaluation_date": evaluation_date.isoformat(),
        "frontier_evidence_id": frontier.evidence_id,
        "third_wave": {
            "driver_numeric_source_certified_count": (
                closeout.source.driver_numeric_source_certified_count
            ),
            "company_profitability_verified_count": (
                closeout.source.company_profitability_verified_count
            ),
            "product_revenue_certified_count": closeout.source.product_revenue_certified_count,
            "source_layer_complete_count": closeout.source_layer_complete_count,
            "all_six_source_layers_complete": closeout.all_six_source_layers_complete,
            "periods": periods,
        },
        "identification_preflight_error": preflight_error,
        "identification_preflight": None if preflight is None else asdict(preflight),
        "replacement_fit_enabled": False,
        "spent_2026q1_reused_as_unseen_holdout": False,
        "future_holdout_period": "2026Q3",
        "future_holdout_loaded": False,
        "future_holdout_evaluated": False,
        "numeric_forward_forecast_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "next_action": next_action,
    }
    company_output.mkdir(parents=True, exist_ok=True)
    output = company_output / "latest_third_wave_identification_preflight.json"
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    temporary.replace(output)
    payload["report_path"] = str(output.resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
