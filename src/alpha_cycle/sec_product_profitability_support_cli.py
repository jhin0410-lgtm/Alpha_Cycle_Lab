from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_product_profitability_support import (
    DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT,
    DEFAULT_SEC_PRODUCT_PROFITABILITY_REGISTRY,
    capture_sec_product_profitability_support,
    load_sec_product_profitability_registry,
)
from alpha_cycle.intelligence.sec_product_profitability_support_verifier import (
    load_sec_product_profitability_support_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture historical SK hynix product-revenue/company-profitability "
            "calibration support from official SEC bytes."
        )
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--observed-date", required=True, type=date.fromisoformat)
    parser.add_argument("--registry", default=str(DEFAULT_SEC_PRODUCT_PROFITABILITY_REGISTRY))
    parser.add_argument("--output", default=str(DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT))
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit(
            "SEC_EDGAR_USER_AGENT is required and must identify the application plus contact email"
        )
    specs = load_sec_product_profitability_registry(Path(args.registry))
    document_id = str(args.document_id)
    spec = specs.get(document_id)
    if spec is None:
        raise SystemExit(f"SEC product-profitability document is not registered: {document_id}")
    result = capture_sec_product_profitability_support(
        spec,
        observed_date=args.observed_date,
        user_agent=user_agent,
        output=Path(args.output),
        timeout_seconds=args.timeout_seconds,
    )
    pointer = Path(args.output) / "latest_sec_product_profitability_support.json"
    verified = load_sec_product_profitability_support_evidence(
        pointer,
        evaluation_date=args.observed_date,
        registry_path=Path(args.registry),
    )
    summary = {
        "status": result["status"],
        "evidence_id": verified.evidence_id,
        "document_id": verified.document_id,
        "observation_count": verified.observation_count,
        "independent_non_overlapping_period_count": (
            verified.independent_non_overlapping_period_count
        ),
        "overlapping_periods_present": verified.overlapping_periods_present,
        "direct_product_profitability_observations": (
            verified.direct_product_profitability_observations
        ),
        "product_profitability_source_fact": verified.product_profitability_source_fact,
        "calibration_support_only": verified.calibration_support_only,
        "artifact_directory": result["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
