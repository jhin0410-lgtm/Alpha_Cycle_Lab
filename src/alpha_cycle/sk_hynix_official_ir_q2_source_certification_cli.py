from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    DEFAULT_Q2_ATTACHMENT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_source_certification import (
    DEFAULT_Q2_SOURCE_CERTIFICATION_OUTPUT,
    capture_q2_source_certification,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify the archived official SK hynix 2Q26 PDF, certify live period/date "
            "identity, and emit layout-preserving Revenue by Product page text without "
            "pairing numeric semantics."
        )
    )
    parser.add_argument("--evaluation-date", type=date.fromisoformat, required=True)
    parser.add_argument("--attachment-pointer", type=Path, default=DEFAULT_Q2_ATTACHMENT_POINTER)
    parser.add_argument("--output", type=Path, default=DEFAULT_Q2_SOURCE_CERTIFICATION_OUTPUT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = capture_q2_source_certification(
        args.attachment_pointer,
        evaluation_date=args.evaluation_date,
        output=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
