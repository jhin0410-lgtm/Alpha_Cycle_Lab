from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_outcome_scoring import (
    DEFAULT_2026Q3_OUTCOME_SCORING_CONTRACT,
    DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT,
    score_locked_2026q3_forecast,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Score the immutable SK hynix 2026Q3 company-GP forecast against the immutable "
            "persistence benchmark after the official 2026Q3 filing is available."
        )
    )
    parser.add_argument(
        "--evaluation-date",
        required=True,
        help="Explicit YYYY-MM-DD evaluation date; do not run before the official Q3 filing.",
    )
    parser.add_argument(
        "--contract",
        default=str(DEFAULT_2026Q3_OUTCOME_SCORING_CONTRACT),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_2026Q3_OUTCOME_SCORING_OUTPUT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evaluation_date = date.fromisoformat(args.evaluation_date)
    score, capture, capture_reused, score_reused = score_locked_2026q3_forecast(
        OpenDartReadOnlyClient.from_env(),
        evaluation_date=evaluation_date,
        contract_path=Path(args.contract),
        output=Path(args.output),
    )
    payload = {
        "status": score.status,
        "score_evidence_id": score.evidence_id,
        "contract_evidence_id": score.contract_evidence_id,
        "forecast_evidence_id": score.forecast_evidence_id,
        "source_capture_evidence_id": score.source_capture_evidence_id,
        "historical_execution_evidence_id": score.historical_execution_evidence_id,
        "evaluation_date": score.evaluation_date.isoformat(),
        "target_period": score.target_period,
        "target_receipt_no": score.target_receipt_no,
        "actual_krw_million": score.actual_krw_million,
        "actual_krw_trillion": score.actual_krw_million / 1_000_000.0,
        "selected_forecast_krw_million": score.selected_forecast_krw_million,
        "benchmark_forecast_krw_million": score.benchmark_forecast_krw_million,
        "selected_signed_error_krw_million": score.selected_signed_error_krw_million,
        "benchmark_signed_error_krw_million": score.benchmark_signed_error_krw_million,
        "selected_absolute_error_krw_million": score.selected_absolute_error_krw_million,
        "benchmark_absolute_error_krw_million": score.benchmark_absolute_error_krw_million,
        "absolute_error_advantage_krw_million": score.absolute_error_advantage_krw_million,
        "winner": score.winner,
        "raw_source_capture_reused": capture_reused,
        "score_artifact_reused": score_reused,
        "source_capture_status": capture.status,
        "2026q3_target_read": score.q3_target_read,
        "2026q3_source_outcome_loaded": score.q3_source_outcome_loaded,
        "2026q3_evaluated": score.q3_evaluated,
        "model_refit_run": score.model_refit_run,
        "forecast_changed_after_lock": score.forecast_changed_after_lock,
        "next_action": "interpret_prospective_result_without_rewriting_the_frozen_research_round",
        "output": str(Path(args.output)),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
