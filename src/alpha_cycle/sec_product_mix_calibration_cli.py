from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_product_mix_calibration import (
    DEFAULT_SEC_PRODUCT_MIX_OUTPUT,
    DEFAULT_SEC_PRODUCT_MIX_REGISTRY,
    capture_sec_product_mix_calibration,
    load_sec_product_mix_registry,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture historical SK hynix product-mix calibration from official SEC bytes."
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--observed-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_SEC_PRODUCT_MIX_REGISTRY),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SEC_PRODUCT_MIX_OUTPUT),
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit(
            "SEC_EDGAR_USER_AGENT is required and must identify the application plus contact email"
        )
    specs = load_sec_product_mix_registry(Path(args.registry))
    spec = specs.get(str(args.document_id))
    if spec is None:
        raise SystemExit(f"SEC product-mix document is not registered: {args.document_id}")
    result = capture_sec_product_mix_calibration(
        spec,
        observed_date=args.observed_date,
        user_agent=user_agent,
        output=Path(args.output),
        timeout_seconds=args.timeout_seconds,
    )
    summary = {
        "status": result["status"],
        "evidence_id": result["evidence_id"],
        "calibration_evidence_id": result["calibration_evidence_id"],
        "document_id": result["document_id"],
        "period_end": result["period_end"],
        "direct_share_method_calibrated": result["direct_share_method_calibrated"],
        "share_only_company_reconciliation_eligible": result[
            "share_only_company_reconciliation_eligible"
        ],
        "artifact_directory": result["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
