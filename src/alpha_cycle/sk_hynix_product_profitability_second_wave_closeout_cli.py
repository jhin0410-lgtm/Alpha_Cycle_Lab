from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import cast

from .intelligence.sk_hynix_product_profitability_promotion_readiness import (
    DEFAULT_PROMOTION_READINESS_POLICY,
    load_promotion_readiness_policy,
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
from .intelligence.sk_hynix_product_profitability_second_wave_readiness import (
    build_second_wave_readiness,
)
from .intelligence.sk_hynix_product_profitability_structural_method import (
    DEFAULT_STRUCTURAL_METHOD_PATH,
    DEFAULT_STRUCTURAL_RANK_PROBE_POINTER,
    load_structural_profitability_method,
)
from .intelligence.sk_hynix_product_profitability_structural_rank_probe_report import (
    load_structural_rank_probe_report,
)
from .providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Close the 2019Q1-2020Q3 SK hynix source frontier, recover legacy company "
            "taxonomy by exact account name when needed, re-run product tie-out, and "
            "evaluate the combined 15-row rank/sample-depth gate without fitting."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--frontier", default=str(DEFAULT_SECOND_WAVE_FRONTIER))
    parser.add_argument("--product-output", default=str(DEFAULT_SECOND_WAVE_PRODUCT_OUTPUT))
    parser.add_argument("--company-output", default=str(DEFAULT_SECOND_WAVE_COMPANY_OUTPUT))
    parser.add_argument("--rank-probe-pointer", default=str(DEFAULT_STRUCTURAL_RANK_PROBE_POINTER))
    parser.add_argument("--method", default=str(DEFAULT_STRUCTURAL_METHOD_PATH))
    parser.add_argument("--promotion-policy", default=str(DEFAULT_PROMOTION_READINESS_POLICY))
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


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evaluation_date = args.evaluation_date
    frontier = load_second_wave_frontier(Path(args.frontier))
    closeout = run_second_wave_closeout(
        OpenDartReadOnlyClient.from_env(),
        frontier,
        evaluation_date=evaluation_date,
        product_output=Path(args.product_output),
        company_output=Path(args.company_output),
    )

    readiness = None
    readiness_error = None
    if closeout.all_six_source_layers_complete:
        try:
            rank_pointer = Path(args.rank_probe_pointer)
            base_evaluation_date = _pointer_evaluation_date(rank_pointer)
            base_rank = load_structural_rank_probe_report(
                rank_pointer,
                evaluation_date=base_evaluation_date,
            )
            method = load_structural_profitability_method(Path(args.method))
            policy = load_promotion_readiness_policy(Path(args.promotion_policy))
            readiness = build_second_wave_readiness(
                evaluation_date=evaluation_date,
                closeout=closeout,
                frontier=frontier,
                base_rank_probe=base_rank,
                method=method,
                policy=policy,
            )
        except ValueError as exc:
            readiness_error = str(exc)

    periods = []
    for item in closeout.periods:
        periods.append(
            {
                "period_id": item.period_id,
                "source_layer_complete": item.source_layer_complete,
                "company_profitability_verified": item.company_profitability_verified,
                "company_recovery_used": item.company_recovery is not None,
                "company_recovery": (
                    None if item.company_recovery is None else asdict(item.company_recovery)
                ),
                "product_revenue_certified": item.product_revenue_certified,
                "product_recovery": (
                    None if item.product_recovery is None else asdict(item.product_recovery)
                ),
                "company_error": item.company_error,
                "product_error": item.product_error,
            }
        )

    if readiness is not None and readiness.method_freeze_review_ready:
        next_action = "preregister_mixed_driver_estimation_method_then_freeze_before_fit"
    elif closeout.all_six_source_layers_complete:
        next_action = "resolve_only_combined_readiness_blockers_before_method_freeze"
    else:
        next_action = "resolve_only_remaining_source_layer_failures"

    payload = {
        "status": "skhynix_product_profitability_second_wave_closeout_and_readiness_completed",
        "evaluation_date": evaluation_date.isoformat(),
        "frontier_evidence_id": frontier.evidence_id,
        "driver_numeric_source_certified_count": closeout.driver_numeric_source_certified_count,
        "company_profitability_verified_count": closeout.company_profitability_verified_count,
        "product_revenue_certified_count": closeout.product_revenue_certified_count,
        "source_layer_complete_count": closeout.source_layer_complete_count,
        "all_six_source_layers_complete": closeout.all_six_source_layers_complete,
        "periods": periods,
        "readiness": None if readiness is None else asdict(readiness),
        "readiness_error": readiness_error,
        "training_row_promoted": False,
        "fit_enabled": False,
        "holdout_period": frontier.holdout_period,
        "holdout_evaluation_allowed": False,
        "next_action": next_action,
    }
    output = Path(args.company_output) / "latest_second_wave_closeout_readiness.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    payload["report_path"] = str(output.resolve())
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
