"""CLI for live SK hynix 2Q26 OpenDART direct product-revenue certification."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_assignment_certification import (
    DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_assignment_certification_verifier import (
    load_q2_product_assignment_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT,
    capture_periodic_product_revenue_certification,
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_q2_product_revenue_ir_crosscheck import (
    build_product_revenue_ir_crosscheck,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient

DEFAULT_DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover the exact SK hynix 2026 half-year OpenDART filing, archive its raw ZIP, "
            "certify direct Q2 DRAM/NAND/Other revenue, and cross-check official IR shares."
        )
    )
    parser.add_argument("--document-id", default=DEFAULT_DOCUMENT_ID)
    parser.add_argument(
        "--registry",
        default="config/semiconductor_periodic_product_revenue.yaml",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT),
    )
    parser.add_argument(
        "--ir-assignment-pointer",
        default=str(DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER),
    )
    parser.add_argument("--evaluation-date", default=date.today().isoformat())
    return parser


def main() -> int:
    args = _parser().parse_args()
    evaluation_date = date.fromisoformat(args.evaluation_date)
    specs = load_periodic_product_revenue_registry(args.registry)
    if args.document_id not in specs:
        raise SystemExit(f"unknown document-id: {args.document_id}")
    pointer = capture_periodic_product_revenue_certification(
        OpenDartReadOnlyClient.from_env(),
        specs[args.document_id],
        evaluation_date=evaluation_date,
        output=args.output,
    )
    certification = load_periodic_product_revenue_certification(
        Path(args.output) / "latest_certification.json",
        evaluation_date=evaluation_date,
    )

    crosscheck_payload: dict[str, object]
    ir_pointer = Path(args.ir_assignment_pointer)
    if ir_pointer.is_file():
        assignment = load_q2_product_assignment_certification(
            ir_pointer,
            evaluation_date=evaluation_date,
        )
        crosscheck = build_product_revenue_ir_crosscheck(certification, assignment)
        crosscheck_payload = asdict(crosscheck)
    else:
        crosscheck_payload = {
            "crosscheck_certified": False,
            "product_revenue_promotion_ready": False,
            "reason": "official_ir_product_assignment_evidence_missing",
            "allocation_resolver_registered": False,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
        }

    readiness = {
        "status": "skhynix_q2_direct_product_revenue_readiness",
        "evaluation_date": evaluation_date.isoformat(),
        "product_revenue_evidence_id": certification.evidence_id,
        "rcept_no": certification.rcept_no,
        "report_name": certification.report_name,
        "source_url": certification.source_url,
        "dram_revenue_krw_million": certification.metrics.dram_total,
        "nand_revenue_krw_million": certification.metrics.nand_and_solutions,
        "other_revenue_krw_million": certification.metrics.other_products_services,
        "reported_company_revenue_krw_million": (
            certification.metrics.reported_company_revenue
        ),
        "company_revenue_reconciliation_certified": (
            certification.company_revenue_reconciliation_certified
        ),
        "product_revenue_baseline_eligible": certification.product_revenue_baseline_eligible,
        "product_profitability_certified": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "ir_crosscheck": crosscheck_payload,
        "certification_pointer": pointer,
    }
    readiness_path = Path(args.output) / "latest_product_revenue_readiness.json"
    temporary = Path(args.output) / ".latest_product_revenue_readiness.json.tmp"
    temporary.write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(readiness_path)
    print(json.dumps(readiness, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
