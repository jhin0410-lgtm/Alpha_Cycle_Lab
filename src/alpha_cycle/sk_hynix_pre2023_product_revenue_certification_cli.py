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
from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_certification import (
    certify_pre2023_product_revenues,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_source_closure import (
    audit_pre2023_product_revenue_sources,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_source_layer_resolution import (
    build_pre2023_source_layer_resolution,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

DEFAULT_PRODUCT_REVENUE_CERTIFICATION_OUTPUT = Path(
    "data/private/research/skhynix-pre2023-product-revenue-certification"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Certify pre-2023 SK hynix direct-quarter DRAM/NAND revenue by exact "
            "reconciliation to verified consolidated company revenue."
        )
    )
    parser.add_argument("--product-probe-output", default=str(DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT))
    parser.add_argument(
        "--company-probe-output",
        default=str(company_probe.DEFAULT_EXPANSION_COMPANY_PROBE_OUTPUT),
    )
    parser.add_argument("--output", default=str(DEFAULT_PRODUCT_REVENUE_CERTIFICATION_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    product_probe_output = Path(args.product_probe_output)
    company_probe_output = Path(args.company_probe_output)
    _resolution, company = build_pre2023_source_layer_resolution(
        product_probe_output=product_probe_output,
        company_probe_output=company_probe_output,
    )
    closures = audit_pre2023_product_revenue_sources(output=product_probe_output)
    results = certify_pre2023_product_revenues(closures, company)

    captured_at = datetime.now(UTC)
    report = {
        "status": "skhynix_pre2023_product_revenue_certification_completed",
        "captured_at": captured_at.isoformat(),
        "results": [asdict(item) for item in results],
        "certified_period_count": sum(item.certified for item in results),
        "training_row_promoted": False,
        "fit_enabled": False,
        "holdout_evaluation_allowed": False,
    }
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__product_revenue_certification.json"
    )
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = {
        "status": report["status"],
        "certified_period_count": report["certified_period_count"],
        "certified_periods": [item.period_id for item in results if item.certified],
        "failed_periods": [item.period_id for item in results if not item.certified],
        "results": [
            {
                "period_id": item.period_id,
                "certified": item.certified,
                "error": item.error,
                "observation": (
                    asdict(item.observation) if item.observation is not None else None
                ),
                "candidate_reviews": [asdict(review) for review in item.candidate_reviews],
            }
            for item in results
        ],
        "report_path": str(path.resolve()),
        "training_row_promoted": False,
        "fit_enabled": False,
        "holdout_evaluation_allowed": False,
        "next_action": (
            "if_all_six_certify_promote_product_revenue_source_layer_then_resolve_"
            "historical_cycle_driver_gap"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
