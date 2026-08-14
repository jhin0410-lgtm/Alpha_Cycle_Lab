from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_post_earnings_all_form_inventory import (
    DEFAULT_ALL_FORM_AFTER_DATE,
    DEFAULT_SEC_ALL_FORM_INVENTORY_OUTPUT,
    capture_post_earnings_all_form_inventory,
)
from alpha_cycle.intelligence.sec_post_earnings_all_form_inventory_verifier import (
    load_post_earnings_all_form_inventory_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover, archive, and verify post-earnings SK hynix SEC primary HTML filings "
            "across all forms."
        )
    )
    parser.add_argument("--observed-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--after-date",
        type=date.fromisoformat,
        default=DEFAULT_ALL_FORM_AFTER_DATE,
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SEC_ALL_FORM_INVENTORY_OUTPUT),
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
    pointer = capture_post_earnings_all_form_inventory(
        observed_date=args.observed_date,
        after_date=args.after_date,
        user_agent=user_agent,
        output=Path(args.output),
        timeout_seconds=args.timeout_seconds,
    )
    evidence = load_post_earnings_all_form_inventory_evidence(
        Path(str(pointer["artifact_directory"]))
        / ".."
        / "latest_sec_post_earnings_all_form_inventory.json",
        evaluation_date=args.observed_date,
    )
    classification_counts: dict[str, int] = {}
    form_counts: dict[str, int] = {}
    filing_summaries: list[dict[str, object]] = []
    for result in evidence.results:
        classification_counts[result.classification] = (
            classification_counts.get(result.classification, 0) + 1
        )
        form_counts[result.form] = form_counts.get(result.form, 0) + 1
        filing_summaries.append(
            {
                "accession_number": result.accession_number,
                "filing_date": result.filing_date.isoformat(),
                "form": result.form,
                "primary_document": result.primary_document,
                "classification": result.classification,
                "q2_period_anchor": result.q2_period_anchor,
                "dram_anchor": result.dram_anchor,
                "nand_anchor": result.nand_anchor,
                "other_products_anchor": result.other_products_anchor,
                "revenue_anchor": result.revenue_anchor,
                "candidate_for_manual_parser_review": result.candidate_for_manual_parser_review,
            }
        )
    summary = {
        "status": "sec_post_earnings_all_form_inventory_reverified",
        "evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "after_date": evidence.after_date.isoformat(),
        "filing_count": len(evidence.results),
        "non_6k_filing_count": sum(item.form != "6-K" for item in evidence.results),
        "form_counts": dict(sorted(form_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "candidate_count": sum(
            item.candidate_for_manual_parser_review for item in evidence.results
        ),
        "candidate_accessions": [
            item.accession_number
            for item in evidence.results
            if item.candidate_for_manual_parser_review
        ],
        "filing_summaries": filing_summaries,
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
