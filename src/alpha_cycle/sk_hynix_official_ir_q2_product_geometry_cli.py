from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_geometry import (
    DEFAULT_Q2_PRODUCT_GEOMETRY_OUTPUT,
    DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER,
    capture_q2_product_geometry,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_geometry_verifier import (
    load_q2_product_geometry,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_source_certification import (
    DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify the archived official SK hynix 2Q26 PDF and capture text-fragment "
            "geometry for Revenue by Product pages without certifying numeric semantics."
        )
    )
    parser.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--certification-pointer",
        type=Path,
        default=DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_Q2_PRODUCT_GEOMETRY_OUTPUT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    pointer = capture_q2_product_geometry(
        args.certification_pointer,
        evaluation_date=args.evaluation_date,
        output=args.output,
    )
    geometry = load_q2_product_geometry(
        args.output / DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER.name,
        evaluation_date=args.evaluation_date,
    )
    pages: list[dict[str, object]] = []
    for page in geometry.pages:
        pages.append(
            {
                "page_number": page.page_number,
                "width": page.width,
                "height": page.height,
                "fragment_count": len(page.fragments),
                "focus_fragment_count": len(page.focus_fragments),
                "focus_fragments": [
                    {
                        "text": item.text,
                        "text_x": item.text_x,
                        "text_y": item.text_y,
                        "font_size": item.font_size,
                        "text_matrix": list(item.text_matrix),
                        "current_matrix": list(item.current_matrix),
                    }
                    for item in page.focus_fragments
                ],
            }
        )
    result = {
        "status": "skhynix_official_ir_q2_product_geometry_reverified",
        "evidence_id": geometry.evidence_id,
        "source_certification_evidence_id": geometry.source_certification_evidence_id,
        "observed_date": geometry.observed_date.isoformat(),
        "source_url": geometry.source_url,
        "pdf_sha256": geometry.pdf_sha256,
        "readiness_status": geometry.readiness_status,
        "pages": pages,
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
