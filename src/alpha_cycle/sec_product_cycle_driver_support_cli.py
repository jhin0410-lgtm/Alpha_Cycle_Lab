from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_OUTPUT,
    capture_sec_product_cycle_driver_support,
)
from alpha_cycle.intelligence.sec_product_cycle_driver_support_verifier import (
    load_sec_product_cycle_driver_support_evidence,
)
from alpha_cycle.intelligence.sec_product_profitability_support import (
    DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay archived SK hynix SEC 424B4 bytes and capture 13-quarter "
            "DRAM/NAND bit-volume and ASP source bands without numeric conversion."
        )
    )
    parser.add_argument(
        "--profitability-support-pointer",
        default=str(DEFAULT_SEC_PRODUCT_PROFITABILITY_POINTER),
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--output", default=str(DEFAULT_SEC_PRODUCT_CYCLE_DRIVER_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = capture_sec_product_cycle_driver_support(
        profitability_support_pointer=Path(args.profitability_support_pointer),
        evaluation_date=args.evaluation_date,
        output=Path(args.output),
    )
    pointer = Path(args.output) / "latest_sec_product_cycle_driver_support.json"
    verified = load_sec_product_cycle_driver_support_evidence(
        pointer,
        evaluation_date=args.evaluation_date,
    )
    latest = verified.observations[-1]
    summary = {
        "status": result["status"],
        "evidence_id": verified.evidence_id,
        "source_profitability_support_evidence_id": (
            verified.source_profitability_support_evidence_id
        ),
        "observation_count": verified.observation_count,
        "first_period": verified.observations[0].period_id,
        "last_period": latest.period_id,
        "last_period_dram_bit_sales_volume_qoq_text": (
            latest.dram_bit_sales_volume_qoq_text
        ),
        "last_period_dram_asp_usd_qoq_text": latest.dram_asp_usd_qoq_text,
        "last_period_nand_bit_sales_volume_qoq_text": (
            latest.nand_bit_sales_volume_qoq_text
        ),
        "last_period_nand_asp_usd_qoq_text": latest.nand_asp_usd_qoq_text,
        "numeric_driver_values_available": verified.numeric_driver_values_available,
        "calibration_support_only": verified.calibration_support_only,
        "artifact_directory": result["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
