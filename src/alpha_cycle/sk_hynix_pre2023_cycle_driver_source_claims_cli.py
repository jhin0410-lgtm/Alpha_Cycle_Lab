from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_pre2023_cycle_driver_source_claims import (
    profile_pre2023_cycle_driver_sources,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_historical_expansion_probe import (
    DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT,
)

DEFAULT_CYCLE_DRIVER_SOURCE_OUTPUT = Path(
    "data/private/research/skhynix-pre2023-cycle-driver-source-claims"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract exact issuer ASP/shipment language from preserved 2021-2022 SK hynix "
            "DART filings without creating numeric point estimates."
        )
    )
    parser.add_argument("--probe-output", default=str(DEFAULT_PRODUCT_REVENUE_PROBE_OUTPUT))
    parser.add_argument("--output", default=str(DEFAULT_CYCLE_DRIVER_SOURCE_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    profiles = profile_pre2023_cycle_driver_sources(output=Path(args.probe_output))
    captured_at = datetime.now(UTC)
    report = {
        "status": "skhynix_pre2023_cycle_driver_source_claims_completed",
        "captured_at": captured_at.isoformat(),
        "profiles": [asdict(item) for item in profiles],
        "numeric_point_source_fact": False,
        "estimation_input_ready": False,
        "four_field_driver_certified": False,
        "fit_enabled": False,
    }
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + "__cycle_driver_claims.json"
    )
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary = {
        "status": report["status"],
        "period_count": len(profiles),
        "four_field_source_language_periods": [
            item.period_id for item in profiles if item.source_language_four_field_coverage
        ],
        "profiles": [
            {
                "period_id": item.period_id,
                "rcept_no": item.rcept_no,
                "source_excerpt_count": item.source_excerpt_count,
                "claim_count": item.claim_count,
                "dram_asp_claim_count": item.dram_asp_claim_count,
                "dram_bit_volume_claim_count": item.dram_bit_volume_claim_count,
                "nand_asp_claim_count": item.nand_asp_claim_count,
                "nand_bit_volume_claim_count": item.nand_bit_volume_claim_count,
                "source_language_four_field_coverage": (
                    item.source_language_four_field_coverage
                ),
                "claims": [asdict(claim) for claim in item.claims],
                "four_field_driver_certified": False,
                "estimation_input_ready": False,
                "fit_enabled": False,
            }
            for item in profiles
        ],
        "report_path": str(path.resolve()),
        "numeric_point_source_fact": False,
        "estimation_input_ready": False,
        "four_field_driver_certified": False,
        "fit_enabled": False,
        "next_action": (
            "review_basis_specific_source_claims_then_define_interval_only_driver_contract"
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
