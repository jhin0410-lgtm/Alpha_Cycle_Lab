from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_numeric_forecast import (
    DEFAULT_2026Q3_NUMERIC_FORECAST_CONTRACT,
    DEFAULT_2026Q3_NUMERIC_FORECAST_OUTPUT,
    lock_2026q3_numeric_forecast,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lock the outcome-blind SK hynix 2026Q3 company-GP numeric forecast."
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_2026Q3_NUMERIC_FORECAST_CONTRACT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_2026Q3_NUMERIC_FORECAST_OUTPUT,
    )
    parser.add_argument(
        "--forecast-locked-at",
        type=str,
        default=None,
        help="Optional timezone-aware ISO-8601 timestamp; primarily for deterministic tests.",
    )
    args = parser.parse_args()
    locked_at = datetime.fromisoformat(args.forecast_locked_at) if args.forecast_locked_at else None
    item, output, reused = lock_2026q3_numeric_forecast(
        forecast_locked_at=locked_at,
        contract_path=args.contract,
        output=args.output,
    )
    payload = {
        "status": item.status,
        "forecast_artifact_reused": reused,
        "output": str(output),
        "contract_evidence_id": item.contract_evidence_id,
        "selected_estimator_evidence_id": item.selected_estimator_evidence_id,
        "feature_vector_evidence_id": item.feature_vector_evidence_id,
        "protocol_evidence_id": item.protocol_evidence_id,
        "source_capture_evidence_id": item.source_capture_evidence_id,
        "forecast_evidence_id": item.evidence_id,
        "target_period": item.target_period,
        "forecast_origin": item.forecast_origin.isoformat(),
        "forecast_locked_at": item.forecast_locked_at.isoformat(),
        "selected_candidate_id": item.selected_candidate_id,
        "predictors": list(item.predictors),
        "feature_values": dict(zip(item.predictors, item.feature_values, strict=True)),
        "raw_unit_intercept": item.raw_unit_intercept,
        "raw_unit_coefficients": list(item.raw_unit_coefficients),
        "standardized_input": list(item.standardized_input),
        "selected_forecast_krw_million": item.selected_forecast_krw_million,
        "selected_forecast_krw_trillion": item.selected_forecast_krw_million / 1_000_000.0,
        "benchmark_id": item.benchmark_id,
        "benchmark_forecast_krw_million": item.benchmark_forecast_krw_million,
        "benchmark_forecast_krw_trillion": item.benchmark_forecast_krw_million / 1_000_000.0,
        "historical_selected_candidate_mae_krw_million": (
            item.historical_selected_candidate_mae_krw_million
        ),
        "historical_benchmark_mae_krw_million": item.historical_benchmark_mae_krw_million,
        "prediction_interval": item.prediction_interval,
        "prospective_feature_vector_frozen": item.prospective_feature_vector_frozen,
        "prospective_forecast_run": item.prospective_forecast_run,
        "2026q1_used_for_selection": item.q1_used_for_selection,
        "2026q3_target_read": item.q3_target_read,
        "2026q3_source_outcome_loaded": item.q3_source_outcome_loaded,
        "2026q3_evaluated": item.q3_evaluated,
        "numeric_forward_forecast_enabled": item.numeric_forward_forecast_enabled,
        "next_action": "wait_for_2026q3_outcome_then_score_locked_forecast_without_model_changes",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
