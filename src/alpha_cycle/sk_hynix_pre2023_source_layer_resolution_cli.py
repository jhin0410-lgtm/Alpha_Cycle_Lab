from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence import (
    sk_hynix_product_profitability_historical_expansion_company_probe as company_probe,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_source_layer_resolution import (
    build_pre2023_source_layer_resolution,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

DEFAULT_SOURCE_LAYER_RESOLUTION_OUTPUT = Path(
    "data/private/research/skhynix-pre2023-source-layer-resolution"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve 2021-2022 SK hynix company profitability, certified product revenue, "
            "and cycle-driver source layers without promoting training rows."
        )
    )
    parser.add_argument(
        "--product-probe-output",
        default=str(DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT),
    )
    parser.add_argument(
        "--company-probe-output",
        default=str(company_probe.DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT),
    )
    parser.add_argument("--output", default=str(DEFAULT_SOURCE_LAYER_RESOLUTION_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    resolution, company = build_pre2023_source_layer_resolution(
        product_probe_output=Path(args.product_probe_output),
        company_probe_output=Path(args.company_probe_output),
    )
    captured_at = datetime.now(UTC)
    report = {
        "status": "skhynix_pre2023_source_layer_resolution_completed",
        "captured_at": captured_at.isoformat(),
        "resolution": asdict(resolution),
        "direct_product_revenue_certified_count": (
            resolution.direct_product_revenue_certified_count
        ),
        "company_constraints": {
            period_id: asdict(item) for period_id, item in sorted(company.items())
        },
        "existing_product_profitability_training_row_eligible": False,
        "synthetic_product_allocation_allowed": False,
        "numeric_driver_point_imputation_allowed": False,
        "alternative_model_fit_allowed": False,
        "holdout_evaluation_allowed": False,
    }
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__source_layer_resolution.json"
    )
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = {
        "status": report["status"],
        "evidence_id": resolution.evidence_id,
        "company_constraint_verified_count": resolution.company_constraint_verified_count,
        "direct_product_revenue_certified_count": (
            resolution.direct_product_revenue_certified_count
        ),
        "aggregate_only_product_revenue_count": (
            resolution.aggregate_only_product_revenue_count
        ),
        "direct_product_revenue_candidate_count": (
            resolution.direct_product_revenue_candidate_count
        ),
        "four_field_source_language_count": resolution.four_field_source_language_count,
        "current_model_training_row_eligible_count": (
            resolution.current_model_training_row_eligible_count
        ),
        "periods": [asdict(item) for item in resolution.periods],
        "report_path": str(path.resolve()),
        "synthetic_product_allocation_allowed": False,
        "numeric_driver_point_imputation_allowed": False,
        "alternative_model_fit_allowed": False,
        "holdout_evaluation_allowed": False,
        "next_action": "run_2019_2020_second_wave_six_row_acquisition_frontier",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
