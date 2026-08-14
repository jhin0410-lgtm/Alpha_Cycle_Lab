from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_OUTPUT,
    DEFAULT_DISCOVERY_POINTER,
    capture_official_ir_attachment_discovery,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery_verifier import (
    load_official_ir_attachment_discovery_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover the exact SK hynix 2Q26 earnings PDF only from URLs explicitly present "
            "in issuer-controlled IR page or JavaScript bytes."
        )
    )
    parser.add_argument("--observed-date", required=True, type=date.fromisoformat)
    parser.add_argument("--output", default=str(DEFAULT_DISCOVERY_OUTPUT))
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    pointer = capture_official_ir_attachment_discovery(
        observed_date=args.observed_date,
        output=output,
        timeout_seconds=args.timeout_seconds,
    )
    evidence = load_official_ir_attachment_discovery_evidence(
        output / DEFAULT_DISCOVERY_POINTER.name,
        evaluation_date=args.observed_date,
    )
    summary = {
        "status": "skhynix_official_ir_attachment_discovery_reverified",
        "evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "script_count": len(evidence.script_resources),
        "candidate_count": len(evidence.candidates),
        "matching_candidate_count": sum(
            item.fingerprint_match for item in evidence.candidates
        ),
        "resolved": evidence.resolved,
        "resolved_url": evidence.resolved_url,
        "resolved_pdf_sha256": evidence.resolved_pdf_sha256,
        "candidates": [
            {
                "url": item.url,
                "discovered_from": list(item.discovered_from),
                "pdf_sha256": item.pdf_sha256,
                "pdf_bytes": item.pdf_bytes,
                "page_count": item.page_count,
                "fingerprint_match": item.fingerprint_match,
                "fingerprint_reason": item.fingerprint_reason,
            }
            for item in evidence.candidates
        ],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "artifact_directory": pointer["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
