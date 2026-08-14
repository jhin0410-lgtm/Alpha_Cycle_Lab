from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_board_api_pipeline import (
    DEFAULT_BOARD_API_OUTPUT,
    DEFAULT_BOARD_API_POINTER,
    build_api_transport_contract,
    capture_official_ir_board_api,
    load_board_api_capture,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_component_contract_diagnostic import (
    DEFAULT_COMPONENT_CONTRACT_POINTER,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve the official SK hynix IR Axios transport from archived issuer bytes and, "
            "only if uniquely resolved, capture the exact Earnings Release /board/list JSON."
        )
    )
    parser.add_argument("--observed-date", type=date.fromisoformat, required=True)
    parser.add_argument("--source-pointer", type=Path, default=DEFAULT_DISCOVERY_POINTER)
    parser.add_argument(
        "--component-pointer",
        type=Path,
        default=DEFAULT_COMPONENT_CONTRACT_POINTER,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_BOARD_API_OUTPUT)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    transport = build_api_transport_contract(
        args.source_pointer,
        args.component_pointer,
        evaluation_date=args.observed_date,
    )
    transport_summary = {
        "status": "skhynix_official_ir_api_transport_checked",
        "transport_evidence_id": transport.evidence_id,
        "source_evidence_id": transport.source_evidence_id,
        "component_evidence_id": transport.component_evidence_id,
        "observed_date": transport.observed_date.isoformat(),
        "page_origin": transport.page_origin,
        "resolution_status": transport.resolution_status,
        "resolved_api_base": transport.resolved_api_base,
        "base_signal_count": len(transport.base_signals),
        "base_signals": [
            {
                "source_file": item.source_file,
                "source_url": item.source_url,
                "key": item.key,
                "raw_value": item.raw_value,
                "resolved_value": item.resolved_value,
                "context": item.context,
            }
            for item in transport.base_signals
        ],
        "axios_config_contexts": list(transport.axios_config_contexts),
        "axios_get_contexts": list(transport.axios_get_contexts),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    if transport.resolution_status != "resolved":
        args.output.mkdir(parents=True, exist_ok=True)
        diagnostic = args.output / "latest_skhynix_ir_api_transport_contract.json"
        diagnostic.write_text(
            json.dumps(transport_summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        transport_summary["transport_diagnostic_path"] = str(diagnostic.resolve())
        transport_summary["board_api_request_sent"] = False
        print(json.dumps(transport_summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    pointer = capture_official_ir_board_api(
        args.source_pointer,
        args.component_pointer,
        evaluation_date=args.observed_date,
        output=args.output,
        timeout_seconds=args.timeout,
    )
    capture = load_board_api_capture(
        args.output / DEFAULT_BOARD_API_POINTER.name,
        evaluation_date=args.observed_date,
    )
    result = {
        **transport_summary,
        **pointer,
        "board_api_request_sent": True,
        "total": capture.total,
        "row_count": len(capture.rows),
        "candidate_seqs": list(capture.candidate_seqs),
        "rows": [
            {
                "seq": item.seq,
                "title": item.title,
                "display_date": item.display_date,
                "file_url1": item.file_url1,
                "file_url2": item.file_url2,
                "file_url3": item.file_url3,
                "file_url4": item.file_url4,
                "candidate_2026q2": item.candidate_2026q2,
            }
            for item in capture.rows
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
