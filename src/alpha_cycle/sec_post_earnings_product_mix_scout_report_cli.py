from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout import (
    DEFAULT_SEC_POST_EARNINGS_SCOUT_POINTER,
)
from alpha_cycle.intelligence.sec_post_earnings_product_mix_scout_verifier import (
    load_post_earnings_product_mix_scout_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify an archived SK hynix SEC post-earnings scout and print filing-level "
            "classification diagnostics without widening any model gate."
        )
    )
    parser.add_argument(
        "--pointer",
        default=str(DEFAULT_SEC_POST_EARNINGS_SCOUT_POINTER),
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evidence = load_post_earnings_product_mix_scout_evidence(
        Path(args.pointer),
        evaluation_date=args.evaluation_date,
    )
    classification_counts = Counter(item.classification for item in evidence.results)
    filing_summaries = []
    for filing, result in zip(evidence.filings, evidence.results, strict=True):
        filing_summaries.append(
            {
                "accession_number": filing.accession_number,
                "filing_date": filing.filing_date.isoformat(),
                "form": filing.form,
                "primary_document": filing.primary_document,
                "classification": result.classification,
                "candidate_for_manual_parser_review": (
                    result.candidate_for_manual_parser_review
                ),
                "q2_period_anchor": result.q2_period_anchor,
                "dram_anchor": result.dram_anchor,
                "nand_anchor": result.nand_anchor,
                "other_products_anchor": result.other_products_anchor,
                "revenue_anchor": result.revenue_anchor,
                "visible_text_chars": result.visible_text_chars,
                "filing_sha256": result.filing_sha256,
            }
        )
    candidate_accessions = [
        item.accession_number
        for item in evidence.results
        if item.candidate_for_manual_parser_review
    ]
    summary = {
        "status": "sec_post_earnings_product_mix_scout_reverified",
        "evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "after_date": evidence.after_date.isoformat(),
        "filing_count": len(evidence.filings),
        "classification_counts": dict(sorted(classification_counts.items())),
        "candidate_count": len(candidate_accessions),
        "candidate_accessions": candidate_accessions,
        "filing_summaries": filing_summaries,
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
