from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability import (
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_OUTPUT,
    DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY,
    capture_quarterly_company_profitability,
    load_quarterly_company_profitability_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_quarterly_company_profitability_verifier import (
    load_quarterly_company_profitability_evidence,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture and offline-verify SK hynix direct quarterly company profitability "
            "from official OpenDART all-accounts responses."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_REGISTRY),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_QUARTERLY_COMPANY_PROFITABILITY_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    registry_path = Path(args.registry)
    output = Path(args.output)
    registry = load_quarterly_company_profitability_registry(registry_path)
    result = capture_quarterly_company_profitability(
        OpenDartReadOnlyClient.from_env(),
        registry,
        evaluation_date=args.evaluation_date,
        output=output,
    )
    pointer = output / "latest_quarterly_company_profitability.json"
    verified = load_quarterly_company_profitability_evidence(
        pointer,
        evaluation_date=args.evaluation_date,
        registry_path=registry_path,
    )
    latest = verified.observations[-1]
    summary = {
        "status": result["status"],
        "evidence_id": verified.evidence_id,
        "observation_count": verified.observation_count,
        "first_period": verified.observations[0].period_id,
        "last_period": latest.period_id,
        "last_period_revenue_krw": latest.revenue_krw,
        "last_period_cost_of_sales_krw": latest.cost_of_sales_krw,
        "last_period_gross_profit_krw": latest.gross_profit_krw,
        "last_period_gross_margin_percent": latest.gross_margin_percent,
        "historical_vintage_certified": verified.historical_vintage_certified,
        "point_in_time_backtest_eligible": verified.point_in_time_backtest_eligible,
        "product_profitability_source_fact": verified.product_profitability_source_fact,
        "artifact_directory": result["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
