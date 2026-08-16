from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    inventory_historical_product_revenue_failure_diagnostics,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_failure_layout import (
    build_failure_layout_signature,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_failure_replay import (
    replay_historical_product_revenue_failure,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_table_diagnostics import (
    build_failure_raw_table_signatures,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT,
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER,
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_REGISTRY,
    historical_period_id,
    load_historical_product_revenue_specs,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel_verifier import (
    load_historical_product_revenue_panel_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay preserved SK hynix historical product-revenue failures offline, "
            "re-run current parsers, and print bounded text/raw-table signatures."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--pointer",
        default=str(DEFAULT_HISTORICAL_PRODUCT_REVENUE_POINTER),
    )
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
    panel = load_historical_product_revenue_panel_evidence(
        Path(args.pointer),
        evaluation_date=args.evaluation_date,
    )
    inventory = inventory_historical_product_revenue_failure_diagnostics(
        panel.failed_periods,
        output=Path(args.output),
    )
    specs = {
        historical_period_id(spec): spec
        for spec in load_historical_product_revenue_specs(Path(args.registry))
    }
    signatures = [
        build_failure_layout_signature(item, specs[item.period_id]).as_dict()
        for item in inventory.diagnostics
    ]
    raw_table_signatures = {
        item.period_id: [
            signature.as_dict()
            for signature in build_failure_raw_table_signatures(
                item,
                specs[item.period_id],
            )
        ]
        for item in inventory.diagnostics
    }
    replays = [
        replay_historical_product_revenue_failure(
            item,
            specs[item.period_id],
        )
        for item in inventory.diagnostics
    ]
    payload = {
        "status": "skhynix_historical_product_revenue_failure_diagnostics",
        "evaluation_date": args.evaluation_date.isoformat(),
        "failed_periods": panel.failed_periods,
        "verified_diagnostic_periods": tuple(
            item.period_id for item in inventory.diagnostics
        ),
        "missing_diagnostic_periods": inventory.missing_diagnostic_periods,
        "invalid_diagnostic_periods": tuple(
            item.period_id for item in inventory.invalid_diagnostics
        ),
        "diagnostic_bundle_coverage_complete": inventory.diagnostic_bundle_coverage_complete,
        "diagnostic_bundle_integrity_complete": inventory.diagnostic_bundle_integrity_complete,
        "replay_recoverable_periods": tuple(
            item.period_id for item in replays if item.replay_recoverable
        ),
        "replay_unresolved_periods": tuple(
            item.period_id for item in replays if not item.replay_recoverable
        ),
        "parser_replays": [item.as_dict() for item in replays],
        "signatures": signatures,
        "raw_table_signatures": raw_table_signatures,
        "network_requested": False,
        "source_fact_promoted": False,
        "certification_created": False,
        "numeric_forecast_enabled": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
