from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    DEFAULT_Q2_ATTACHMENT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_parser_readiness import (
    DEFAULT_Q2_PARSER_READINESS_OUTPUT,
    DEFAULT_Q2_PARSER_READINESS_POINTER,
    capture_q2_parser_readiness,
    load_q2_parser_readiness,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify the official SK hynix 2Q26 PDF and emit parser-contract review context "
            "without certifying any numeric semantics."
        )
    )
    parser.add_argument("--observed-date", type=date.fromisoformat, required=True)
    parser.add_argument("--attachment-pointer", type=Path, default=DEFAULT_Q2_ATTACHMENT_POINTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_Q2_PARSER_READINESS_OUTPUT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    pointer = capture_q2_parser_readiness(
        args.attachment_pointer,
        evaluation_date=args.observed_date,
        output=args.output,
    )
    readiness = load_q2_parser_readiness(
        args.output / DEFAULT_Q2_PARSER_READINESS_POINTER.name,
        evaluation_date=args.observed_date,
    )
    result = {
        **pointer,
        "readiness_status": readiness.readiness_status,
        "source_url": readiness.source_url,
        "source_published_date": readiness.source_published_date,
        "expected_page_count": readiness.expected_page_count,
        "parser_id_candidate": readiness.parser_id_candidate,
        "percentage_tokens": list(readiness.percentage_tokens),
        "comma_number_tokens": list(readiness.comma_number_tokens),
        "contexts": [
            {
                "page_number": item.page_number,
                "context": item.context,
                "relevant_lines": list(item.relevant_lines),
                "percentage_tokens": list(item.percentage_tokens),
                "comma_number_tokens": list(item.comma_number_tokens),
                "dram_anchor": item.dram_anchor,
                "nand_anchor": item.nand_anchor,
            }
            for item in readiness.contexts
        ],
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
