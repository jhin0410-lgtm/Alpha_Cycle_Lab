from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_frontier import (
    DEFAULT_HISTORICAL_EXPANSION_FRONTIER,
    audit_historical_expansion_frontier,
    load_historical_expansion_frontier,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit pre-2023 SK hynix training-row acquisition candidates without promoting "
            "issuer releases, untested OpenDART layouts, or qualitative commentary into fit evidence."
        )
    )
    parser.add_argument("--frontier", default=str(DEFAULT_HISTORICAL_EXPANSION_FRONTIER))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    frontier = load_historical_expansion_frontier(Path(args.frontier))
    audit = audit_historical_expansion_frontier(frontier)
    payload = {
        "frontier_id": frontier.frontier_id,
        "frontier_version": frontier.frontier_version,
        "frontier_evidence_id": frontier.evidence_id,
        "candidate_periods": [item.period_id for item in frontier.candidates],
        "candidate_count": audit.candidate_count,
        "target_additional_training_rows": audit.target_additional_training_rows,
        "issuer_release_verified_count": audit.issuer_release_verified_count,
        "product_revenue_certified_count": audit.product_revenue_certified_count,
        "company_profitability_certified_count": audit.company_profitability_certified_count,
        "cycle_driver_certified_count": audit.cycle_driver_certified_count,
        "source_layer_complete_count": audit.source_layer_complete_count,
        "training_row_certified_count": audit.training_row_certified_count,
        "remaining_candidate_rows": audit.remaining_candidate_rows,
        "q4_direct_quarter_derivation_allowed": frontier.q4_direct_quarter_derivation_allowed,
        "candidate_registration_enables_fit": frontier.candidate_registration_enables_fit,
        "candidate_registration_enables_holdout": frontier.candidate_registration_enables_holdout,
        "fit_enabled": audit.fit_enabled,
        "holdout_evaluation_enabled": audit.holdout_evaluation_enabled,
        "next_action": (
            "attempt_opendart_product_revenue_and_company_profitability_capture_then_"
            "separately_certify_four_field_cycle_drivers"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
