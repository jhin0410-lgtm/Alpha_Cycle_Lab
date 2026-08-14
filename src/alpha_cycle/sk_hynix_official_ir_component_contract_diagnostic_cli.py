from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_component_contract_diagnostic import (
    DEFAULT_COMPONENT_CONTRACT_OUTPUT,
    DEFAULT_COMPONENT_CONTRACT_POINTER,
    ComponentContractSignal,
    capture_component_contract_diagnostic,
    load_component_contract_diagnostic,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverify archived SK hynix official IR bytes and extract only exact component-level "
            "execute routes, board bcodes, CDN paths, and fileUrl bindings."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument("--source-pointer", default=str(DEFAULT_DISCOVERY_POINTER))
    parser.add_argument("--output", default=str(DEFAULT_COMPONENT_CONTRACT_OUTPUT))
    return parser


def _signal(item: ComponentContractSignal) -> dict[str, object]:
    return {
        "source_file": item.source_file,
        "source_url": item.source_url,
        "component_name": item.component_name,
        "kind": item.kind,
        "value": item.value,
        "method": item.method,
        "context": item.context,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = Path(args.output)
    pointer = capture_component_contract_diagnostic(
        args.source_pointer,
        evaluation_date=args.evaluation_date,
        output=output,
    )
    evidence = load_component_contract_diagnostic(
        output / DEFAULT_COMPONENT_CONTRACT_POINTER.name,
        evaluation_date=args.evaluation_date,
    )
    summary = {
        "status": "skhynix_official_ir_component_contract_diagnostic_reverified",
        "evidence_id": evidence.evidence_id,
        "source_evidence_id": evidence.source_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "execute_route_count": len(evidence.execute_routes),
        "bcode_assignment_count": len(evidence.bcode_assignments),
        "earnings_code_mapping_count": len(evidence.earnings_code_mappings),
        "cdn_path_count": len(evidence.cdn_paths),
        "file_url_binding_count": len(evidence.file_url_bindings),
        "method_window_count": len(evidence.method_windows),
        "execute_routes": [_signal(item) for item in evidence.execute_routes],
        "bcode_assignments": [_signal(item) for item in evidence.bcode_assignments],
        "earnings_code_mappings": [_signal(item) for item in evidence.earnings_code_mappings],
        "cdn_paths": [_signal(item) for item in evidence.cdn_paths],
        "file_url_bindings": [_signal(item) for item in evidence.file_url_bindings],
        "method_windows": [_signal(item) for item in evidence.method_windows],
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
