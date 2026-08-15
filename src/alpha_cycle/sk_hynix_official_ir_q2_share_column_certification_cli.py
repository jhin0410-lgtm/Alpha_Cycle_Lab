from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_geometry import (
    DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_share_column_certification import (
    DEFAULT_Q2_SHARE_COLUMN_OUTPUT,
    DEFAULT_Q2_SHARE_COLUMN_POINTER,
    capture_q2_share_column_certification,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_share_column_certification_verifier import (
    load_q2_share_column_certification,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify SK hynix 2Q26 product-page geometry and certify only the three "
            "period columns and the raw 73%/27% current-column tokens. Product-series "
            "assignment and Other=0 remain uncertified."
        )
    )
    parser.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--geometry-pointer",
        type=Path,
        default=DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_Q2_SHARE_COLUMN_OUTPUT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    pointer = capture_q2_share_column_certification(
        args.geometry_pointer,
        evaluation_date=args.evaluation_date,
        output=args.output,
    )
    item = load_q2_share_column_certification(
        args.output / DEFAULT_Q2_SHARE_COLUMN_POINTER.name,
        evaluation_date=args.evaluation_date,
    )
    result = {
        "status": "skhynix_official_ir_q2_share_column_reverified",
        "evidence_id": item.evidence_id,
        "geometry_evidence_id": item.geometry_evidence_id,
        "source_certification_evidence_id": item.source_certification_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "pdf_sha256": item.pdf_sha256,
        "page_number": item.page_number,
        "quarter_labels": list(item.quarter_labels),
        "columns": [
            {
                "period_label": column.period_label,
                "x_center": column.x_center,
                "percentage_tokens": list(column.percentage_tokens),
                "percentage_sum": column.percentage_sum,
            }
            for column in item.columns
        ],
        "current_period_label": item.current_period_label,
        "current_period_start": item.current_period_start,
        "current_period_end": item.current_period_end,
        "current_column_percentage_tokens": list(item.current_column_percentage_tokens),
        "current_column_percentage_sum": item.current_column_percentage_sum,
        "product_legend_labels": list(item.product_legend_labels),
        "footnote_verified": item.footnote_verified,
        "period_column_semantics_certified": True,
        "product_assignment_certified": False,
        "other_zero_certified": False,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "artifact_directory": pointer["artifact_directory"],
        "report_path": pointer["report_path"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
