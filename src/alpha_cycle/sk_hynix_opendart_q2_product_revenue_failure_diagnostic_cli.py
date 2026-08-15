"""CLI for inspecting the latest preserved SK hynix OpenDART product-revenue failure."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_failure_diagnostic import (
    latest_failure_diagnostic,
    write_failure_diagnostic_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect preserved OpenDART failure evidence offline"
    )
    parser.add_argument("--root", default=str(DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT))
    parser.add_argument("--diagnostic", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    path = (
        Path(args.diagnostic)
        if args.diagnostic
        else latest_failure_diagnostic(args.root)
    )
    report, output = write_failure_diagnostic_report(path)
    payload = asdict(report)
    payload["report_path"] = str(output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
