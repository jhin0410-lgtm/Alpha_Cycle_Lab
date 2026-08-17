from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .intelligence.sk_hynix_product_profitability_regime_post_validation_audit import (
    build_regime_v1_post_validation_audit,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit frozen SK hynix regime-v1 structural plausibility and, only when the "
            "predictive holdout passed but literal margin interpretation fails, acquire the "
            "pre-registered 2017Q1-2018Q3 exact-numeric v2 identification frontier."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--third-wave-frontier", default=str(DEFAULT_THIRD_WAVE_FRONTIER))
    parser.add_argument(
        "--third-wave-product-output",
        default=str(DEFAULT_THIRD_WAVE_PRODUCT_OUTPUT),
    )
    parser.add_argument(
        "--third-wave-company-output",
        default=str(DEFAULT_THIRD_WAVE_COMPANY_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    audit = build_regime_v1_post_validation_audit()
    third_wave = None
    acquisition_error = None

    should_expand = (
        audit.predictive_validation_passed
        and not audit.structural_margin_interpretation_passed
    )
    if should_expand:
        try:
            frontier = load_third_wave_frontier(Path(args.third_wave_frontier))
            third_wave = run_third_wave_closeout(
                OpenDartReadOnlyClient.from_env(),
                frontier,
                evaluation_date=args.evaluation_date,
                product_output=Path(args.third_wave_product_output),
                company_output=Path(args.third_wave_company_output),
            )
        except ValueError as exc:
            acquisition_error = str(exc)

    period_details = None
    if third_wave is not None:
        period_details = [
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
            for item in third_wave.source.periods
        ]

    if third_wave is not None and third_wave.all_six_source_layers_complete:
        next_action = (
            "build_21_row_v2_identification_preflight_then_choose_structural_or_"
            "predictive_only_v2_without_reusing_2026q1_as_unseen"
        )
    elif third_wave is not None:
        next_action = "resolve_only_failed_2017_2018_source_layers_then_replay_same_command"
    elif acquisition_error is not None:
        next_action = "repair_third_wave_acquisition_integrity_without_refitting_v1"
    elif audit.forward_forecast_contract_review_allowed:
        next_action = "review_forward_input_contract_without_refitting_v1"
    else:
        next_action = "preserve_v1_validation_evidence_and_stop_forward_use"

    payload = {
        "status": "skhynix_product_profitability_post_validation_research_completed",
        "evaluation_date": args.evaluation_date.isoformat(),
        "v1_audit": {
            "evidence_id": audit.evidence_id,
            "model_status": audit.model_status,
            "predictive_validation_passed": audit.predictive_validation_passed,
            "structural_margin_interpretation_passed": (
                audit.structural_margin_interpretation_passed
            ),
            "forward_forecast_contract_review_allowed": (
                audit.forward_forecast_contract_review_allowed
            ),
            "dram_margin_envelope": asdict(audit.dram_margin_envelope),
            "nand_margin_envelope": asdict(audit.nand_margin_envelope),
            "other_margin_constant": audit.other_margin_constant,
            "other_margin_absolute_value_gt_one_report_only": (
                audit.other_margin_absolute_value_gt_one_report_only
            ),
            "max_leverage_report_only": audit.max_leverage_report_only,
            "max_cooks_distance_report_only": audit.max_cooks_distance_report_only,
        },
        "third_wave_acquisition_attempted": should_expand,
        "third_wave_acquisition_error": acquisition_error,
        "third_wave": (
            None
            if third_wave is None
            else {
                "driver_numeric_source_certified_count": (
                    third_wave.source.driver_numeric_source_certified_count
                ),
                "company_profitability_verified_count": (
                    third_wave.source.company_profitability_verified_count
                ),
                "product_revenue_certified_count": (
                    third_wave.source.product_revenue_certified_count
                ),
                "source_layer_complete_count": third_wave.source_layer_complete_count,
                "all_six_source_layers_complete": (
                    third_wave.source.all_six_source_layers_complete
                ),
                "projected_v2_training_rows_if_all_promoted": (
                    third_wave.projected_v2_training_rows_if_all_promoted
                ),
                "periods": period_details,
            }
        ),
        "v1_refit_enabled": False,
        "v2_fit_enabled": False,
        "reuse_2026q1_as_unseen_holdout_for_v2_allowed": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "next_action": next_action,
    }
    output = Path(args.third_wave_company_output) / "latest_post_validation_research.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    payload["report_path"] = str(output.resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
