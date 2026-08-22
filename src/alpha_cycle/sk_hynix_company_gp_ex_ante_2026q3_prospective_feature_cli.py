from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_prospective_feature import (
    DEFAULT_2026Q3_PROSPECTIVE_FEATURE_CONTRACT,
    DEFAULT_2026Q3_PROSPECTIVE_OUTPUT,
    freeze_2026q3_prospective_feature_vector,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze the SK hynix 2026Q3 prospective predictor vector from locked 2026Q2 "
            "OpenDART source bytes without reading the protected 2026Q3 outcome."
        )
    )
    parser.add_argument(
        "--contract",
        default=str(DEFAULT_2026Q3_PROSPECTIVE_FEATURE_CONTRACT),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_2026Q3_PROSPECTIVE_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    item, capture, source_reused, feature_reused = freeze_2026q3_prospective_feature_vector(
        OpenDartReadOnlyClient.from_env(),
        contract_path=Path(args.contract),
        output=Path(args.output),
    )
    payload = {
        "status": item.status,
        "feature_vector_evidence_id": item.evidence_id,
        "contract_evidence_id": item.contract_evidence_id,
        "protocol_evidence_id": item.protocol_evidence_id,
        "selected_estimator_evidence_id": item.selected_estimator_evidence_id,
        "historical_execution_evidence_id": item.historical_execution_evidence_id,
        "source_capture_evidence_id": item.source_capture_evidence_id,
        "raw_source_capture_reused": source_reused,
        "feature_vector_reused": feature_reused,
        "target_period": item.target_period,
        "source_period": item.source_period,
        "forecast_origin": item.forecast_origin.isoformat(),
        "frozen_at": item.frozen_at.isoformat(),
        "source_receipt_no": item.source_receipt_no,
        "source_receipt_date": item.source_receipt_date.isoformat(),
        "source_available_at": item.source_available_at.isoformat(),
        "source_raw_payload_sha256": item.source_raw_payload_sha256,
        "source_captured_payload_bytes_sha256": (
            item.source_captured_payload_bytes_sha256
        ),
        "predictors": list(item.predictors),
        "feature_values": {
            predictor: value
            for predictor, value in zip(item.predictors, item.feature_values, strict=True)
        },
        "prospective_feature_vector_frozen": item.prospective_feature_vector_frozen,
        "prospective_forecast_run": item.prospective_forecast_run,
        "2026q1_used_for_selection": item.q1_used_for_selection,
        "2026q3_target_read": item.q3_target_read,
        "2026q3_source_outcome_loaded": item.q3_source_outcome_loaded,
        "2026q3_evaluated": item.q3_evaluated,
        "numeric_forward_forecast_enabled": item.numeric_forward_forecast_enabled,
        "next_action": (
            "run_locked_2026q3_numeric_forecast_without_reading_2026q3_outcome"
        ),
        "source_capture_status": capture.status,
        "output": str(Path(args.output)),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
