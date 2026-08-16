from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    inventory_historical_product_revenue_failure_diagnostics,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT,
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_REGISTRY,
    capture_historical_product_revenue_panel,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Batch-capture SK hynix 2023Q1-2026Q1 Q1/Q2/Q3 direct product revenue "
            "from official OpenDART filings and preserve per-period parser failures."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_HISTORICAL_PRODUCT_REVENUE_REGISTRY),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    result = capture_historical_product_revenue_panel(
        OpenDartReadOnlyClient.from_env(),
        evaluation_date=args.evaluation_date,
        registry_path=Path(args.registry),
        output=output,
    )
    pointer = output / "latest_historical_product_revenue_panel.json"
    verified = load_historical_product_revenue_panel_evidence(
        pointer,
        evaluation_date=args.evaluation_date,
    )
    diagnostics = inventory_historical_product_revenue_failure_diagnostics(
        verified.failed_periods,
        output=output,
    )
    summary = {
        "status": result["status"],
        "evidence_id": verified.evidence_id,
        "successful_period_count": len(verified.successful_periods),
        "successful_periods": verified.successful_periods,
        "failed_period_count": len(verified.failed_periods),
        "failed_periods": verified.failed_periods,
        "failed_diagnostic_bundle_count": len(diagnostics.diagnostics),
        "failed_diagnostic_paths": diagnostics.diagnostic_paths,
        "failed_diagnostic_invalid_count": len(diagnostics.invalid_diagnostics),
        "failed_diagnostic_invalid_paths": diagnostics.invalid_diagnostic_paths,
        "failed_diagnostic_invalid_errors": diagnostics.invalid_diagnostic_errors,
        "failed_diagnostic_missing_periods": diagnostics.missing_diagnostic_periods,
        "failed_diagnostic_bundle_coverage_complete": (
            diagnostics.diagnostic_bundle_coverage_complete
        ),
        "failed_diagnostic_bundle_integrity_complete": (
            diagnostics.diagnostic_bundle_integrity_complete
        ),
        "full_source_coverage_certified": verified.full_source_coverage_certified,
        "product_profitability_source_fact": verified.product_profitability_source_fact,
        "numeric_forecast_enabled": verified.numeric_forecast_enabled,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
