from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_board_api_pipeline import (
    DEFAULT_BOARD_API_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    DEFAULT_Q2_ATTACHMENT_OUTPUT,
    DEFAULT_Q2_ATTACHMENT_POINTER,
    capture_q2_attachment,
    load_q2_attachment_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the SK hynix official 2Q26 Earnings Release PDF only from the "
            "reverified board API row and returned CDN/fileUrl2 fields."
        )
    )
    parser.add_argument("--observed-date", type=date.fromisoformat, required=True)
    parser.add_argument("--board-pointer", type=Path, default=DEFAULT_BOARD_API_POINTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_Q2_ATTACHMENT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    pointer = capture_q2_attachment(
        args.board_pointer,
        evaluation_date=args.observed_date,
        output=args.output,
        timeout_seconds=args.timeout,
    )
    evidence = load_q2_attachment_evidence(
        args.output / DEFAULT_Q2_ATTACHMENT_POINTER.name,
        evaluation_date=args.observed_date,
    )
    fingerprint = evidence.fingerprint
    result = {
        **pointer,
        "document_identity_verified": fingerprint.document_identity_verified,
        "page_count": fingerprint.page_count,
        "text_chars": fingerprint.text_chars,
        "sk_hynix_anchor": fingerprint.sk_hynix_anchor,
        "q2_2026_anchor": fingerprint.q2_2026_anchor,
        "revenue_by_product_anchor": fingerprint.revenue_by_product_anchor,
        "dram_anchor": fingerprint.dram_anchor,
        "nand_anchor": fingerprint.nand_anchor,
        "product_mix_contexts": [
            {
                "page_number": item.page_number,
                "anchor": item.anchor,
                "context": item.context,
            }
            for item in fingerprint.product_mix_contexts
        ],
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
