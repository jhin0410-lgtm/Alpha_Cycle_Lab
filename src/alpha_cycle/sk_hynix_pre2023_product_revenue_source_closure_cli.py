from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_source_closure import (
    ProductRevenueSourceClosurePeriod,
    audit_pre2023_product_revenue_sources,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

DEFAULT_SOURCE_CLOSURE_OUTPUT = Path(
    "data/private/research/skhynix-pre2023-product-revenue-source-closure"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exhaustively scan preserved 2021-2022 SK hynix OpenDART XML tables for "
            "directly separable DRAM/NAND revenue versus aggregate product buckets."
        )
    )
    parser.add_argument("--probe-output", default=str(DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT))
    parser.add_argument("--output", default=str(DEFAULT_SOURCE_CLOSURE_OUTPUT))
    return parser


def _summary(item: ProductRevenueSourceClosurePeriod) -> dict[str, object]:
    return {
        "period_id": item.period_id,
        "evidence_id": item.evidence_id,
        "rcept_no": item.rcept_no,
        "member_count": item.member_count,
        "table_count": item.table_count,
        "aggregate_bucket_witness_count": item.aggregate_bucket_witness_count,
        "direct_separable_candidate_count": item.direct_separable_candidate_count,
        "aggregate_only_observed": item.aggregate_only_observed,
        "aggregate_bucket_witnesses": [
            {
                "member_name": witness.member_name,
                "table_index": witness.table_index,
                "combined_bucket_cells": witness.combined_bucket_cells,
                "unit_markers": witness.unit_markers,
                "prefix_tail": witness.prefix_tail,
                "rows": witness.rows,
            }
            for witness in item.aggregate_bucket_witnesses[:4]
        ],
        "direct_separable_candidates": [
            {
                "member_name": witness.member_name,
                "table_index": witness.table_index,
                "dram_label_rows": witness.dram_label_rows,
                "nand_label_rows": witness.nand_label_rows,
                "direct_labeled_amount_row_count": witness.direct_labeled_amount_row_count,
                "unit_markers": witness.unit_markers,
                "prefix_tail": witness.prefix_tail,
                "rows": witness.rows,
            }
            for witness in item.direct_separable_candidates[:4]
        ],
        "direct_product_revenue_certified": False,
        "synthetic_product_allocation_allowed": False,
        "training_row_promoted": False,
        "fit_enabled": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    results = audit_pre2023_product_revenue_sources(output=Path(args.probe_output))
    captured_at = datetime.now(UTC)
    report = {
        "status": "skhynix_pre2023_product_revenue_source_closure_completed",
        "captured_at": captured_at.isoformat(),
        "periods": [asdict(item) for item in results],
        "exhaustive_preserved_archive_scan_complete": True,
        "direct_product_revenue_certified": False,
        "synthetic_product_allocation_allowed": False,
        "training_row_promoted": False,
        "fit_enabled": False,
    }
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__source_closure.json"
    )
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = {
        "status": report["status"],
        "period_count": len(results),
        "aggregate_only_periods": [
            item.period_id for item in results if item.aggregate_only_observed
        ],
        "direct_candidate_periods": [
            item.period_id for item in results if item.direct_separable_candidate_count > 0
        ],
        "periods": [_summary(item) for item in results],
        "report_path": str(path.resolve()),
        "direct_product_revenue_certified": False,
        "synthetic_product_allocation_allowed": False,
        "training_row_promoted": False,
        "fit_enabled": False,
        "next_action": (
            "review_any_direct_candidates_or_close_direct_product_revenue_source_layer_"
            "without_synthetic_allocation"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
