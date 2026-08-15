from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_product_assignment_certification as assignment,
)
from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_product_assignment_certification_verifier as verifier,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_share_column_certification import (
    DEFAULT_Q2_SHARE_COLUMN_POINTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify the SK hynix 2Q26 share-column chain and official PDF vectors, "
            "then bind 73% to DRAM and 27% to NAND through legend/segment colours. "
            "The visible Others segment remains numerically unresolved and all "
            "allocation/forecast/decision gates stay disabled."
        )
    )
    parser.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--share-column-pointer",
        type=Path,
        default=DEFAULT_Q2_SHARE_COLUMN_POINTER,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=assignment.DEFAULT_Q2_PRODUCT_ASSIGNMENT_OUTPUT,
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    pointer = assignment.capture_q2_product_assignment_certification(
        args.share_column_pointer,
        evaluation_date=args.evaluation_date,
        output=args.output,
    )
    item = verifier.load_q2_product_assignment_certification(
        args.output / assignment.DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER.name,
        evaluation_date=args.evaluation_date,
    )
    result = {
        "status": "skhynix_official_ir_q2_product_assignment_reverified",
        "evidence_id": item.evidence_id,
        "share_column_evidence_id": item.share_column_evidence_id,
        "geometry_evidence_id": item.geometry_evidence_id,
        "source_certification_evidence_id": item.source_certification_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "pdf_sha256": item.pdf_sha256,
        "page_number": item.page_number,
        "current_period_label": item.current_period_label,
        "dram_share_percent": item.dram_share_percent,
        "nand_share_percent": item.nand_share_percent,
        "other_share_percent": None,
        "legend_bindings": [
            {
                "product": binding.product,
                "fill": {
                    "color_space": binding.swatch.fill.color_space,
                    "components": list(binding.swatch.fill.components),
                },
            }
            for binding in item.legend_bindings
        ],
        "product_share_bindings": [
            {
                "product": binding.product,
                "percentage_token": binding.percentage_token,
                "percentage_value": binding.percentage_value,
                "token_x": binding.token_x,
                "token_y": binding.token_y,
            }
            for binding in item.product_share_bindings
        ],
        "others_segment_present": item.others_segment_present,
        "product_assignment_certified": item.product_assignment_certified,
        "dram_nand_share_semantics_certified": item.dram_nand_share_semantics_certified,
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
