"""Offline replay of a preserved SK hynix OpenDART product-revenue failure bundle."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_REGISTRY,
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_expected_replay import (
    parse_periodic_product_revenue_archive,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_layout import (
    parse_periodic_product_revenue_text,
)

_DEFAULT_DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a preserved SK hynix OpenDART ZIP and normalized text without any "
            "network request before attempting a new live capture."
        )
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--normalized-text", required=True)
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_PERIODIC_PRODUCT_REVENUE_REGISTRY),
    )
    parser.add_argument("--document-id", default=_DEFAULT_DOCUMENT_ID)
    return parser


def main() -> int:
    args = _parser().parse_args()
    specs = load_periodic_product_revenue_registry(args.registry)
    if args.document_id not in specs:
        raise ValueError(f"Periodic product revenue document is not registered: {args.document_id}")
    spec = specs[args.document_id]

    archive_path = Path(args.archive)
    text_path = Path(args.normalized_text)
    archive_bytes = archive_path.read_bytes()
    normalized_text = text_path.read_text(encoding="utf-8")

    raw_metrics = parse_periodic_product_revenue_archive(spec, archive_bytes)
    text_metrics = parse_periodic_product_revenue_text(spec, normalized_text)
    if raw_metrics != text_metrics:
        raise ValueError(
            "Offline OpenDART raw-source and normalized-text product revenue disagree: "
            f"raw={raw_metrics} text={text_metrics}"
        )

    print(
        json.dumps(
            {
                "status": "skhynix_opendart_q2_product_revenue_offline_preflight_passed",
                "archive_path": str(archive_path),
                "normalized_text_path": str(text_path),
                "metrics": asdict(raw_metrics),
                "network_requested": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
