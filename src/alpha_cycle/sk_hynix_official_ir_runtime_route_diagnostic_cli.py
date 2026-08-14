from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_runtime_route_diagnostic import (
    DEFAULT_RUNTIME_ROUTE_OUTPUT,
    DEFAULT_RUNTIME_ROUTE_POINTER,
    capture_runtime_route_diagnostic,
    load_runtime_route_diagnostic,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify archived SK hynix official IR page/JavaScript bytes and report literal "
            "runtime network-route signals without making any network request."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--source-pointer", default=str(DEFAULT_DISCOVERY_POINTER))
    parser.add_argument("--output", default=str(DEFAULT_RUNTIME_ROUTE_OUTPUT))
    return parser


def _signal(item: object) -> dict[str, object]:
    signal = item
    return {
        "source_file": signal.source_file,
        "source_url": signal.source_url,
        "kind": signal.kind,
        "token": signal.token,
        "literal": signal.literal,
        "context": signal.context,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    pointer = capture_runtime_route_diagnostic(
        args.source_pointer,
        evaluation_date=args.evaluation_date,
        output=output,
    )
    evidence = load_runtime_route_diagnostic(
        output / DEFAULT_RUNTIME_ROUTE_POINTER.name,
        evaluation_date=args.evaluation_date,
    )
    summary = {
        "status": "skhynix_official_ir_runtime_route_diagnostic_reverified",
        "evidence_id": evidence.evidence_id,
        "source_evidence_id": evidence.source_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "source_count": len(evidence.source_summaries),
        "network_call_site_count": len(evidence.network_call_sites),
        "route_literal_count": len(evidence.route_literals),
        "attachment_context_count": len(evidence.attachment_contexts),
        "source_summaries": [
            {
                "source_file": item.source_file,
                "source_url": item.source_url,
                "source_sha256": item.source_sha256,
                "source_bytes": item.source_bytes,
                "network_call_site_count": item.network_call_site_count,
                "route_literal_count": item.route_literal_count,
                "attachment_context_count": item.attachment_context_count,
            }
            for item in evidence.source_summaries
        ],
        "network_call_sites": [_signal(item) for item in evidence.network_call_sites],
        "route_literals": [_signal(item) for item in evidence.route_literals],
        "attachment_contexts": [_signal(item) for item in evidence.attachment_contexts],
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "artifact_directory": pointer["artifact_directory"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
