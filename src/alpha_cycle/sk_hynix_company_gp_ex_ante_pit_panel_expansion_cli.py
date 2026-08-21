from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION,
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_replay import (
    run_target_blind_pit_panel_expansion_replay,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Expand the SK hynix target-blind ex-ante PIT filing-feature panel to the "
            "frozen twenty-row sample gate without reading historical targets."
        )
    )
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION),
    )
    parser.add_argument(
        "--combined-bundle-output",
        default=str(DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE),
    )
    parser.add_argument(
        "--report-output",
        default=str(DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_target_blind_pit_panel_expansion_replay(
        OpenDartReadOnlyClient.from_env(),
        evaluation_date=args.evaluation_date,
        manifest=Path(args.manifest),
        combined_bundle_output=Path(args.combined_bundle_output),
        report_output=Path(args.report_output),
    )
    payload = {
        "status": result.status,
        "contract_evidence_id": result.contract_evidence_id,
        "base_bundle_evidence_id": result.base_bundle_evidence_id,
        "selected_legacy_year": result.selected_legacy_year,
        "attempted_source_periods": [item.source_period for item in result.attempts],
        "successful_source_periods": [
            item.source_period for item in result.attempts if item.success
        ],
        "failed_source_periods": [
            item.source_period for item in result.attempts if not item.success
        ],
        "failed_source_diagnostics": [
            {
                "source_period": item.source_period,
                "target_period": item.target_period,
                "error_type": item.error_type,
                "error": item.error,
            }
            for item in result.attempts
            if not item.success
        ],
        "added_target_periods": list(result.added_target_periods),
        "added_target_row_count": result.added_target_row_count,
        "added_feature_observation_count": result.added_feature_observation_count,
        "combined_target_periods": list(result.combined_target_periods),
        "combined_target_row_count": result.combined_target_row_count,
        "combined_feature_observation_count": result.combined_feature_observation_count,
        "combined_bundle_evidence_id": result.combined_bundle_evidence_id,
        "eligible_added_observation_count": result.eligible_added_observation_count,
        "rejected_added_observation_count": result.rejected_added_observation_count,
        "all_added_observations_point_in_time_eligible": (
            result.all_added_observations_point_in_time_eligible
        ),
        "completion_gate_passed": result.completion_gate_passed,
        "historical_target_values_read": result.historical_target_values_read,
        "target_join_authorized": result.target_join_authorized,
        "estimator_fit_authorized": result.estimator_fit_authorized,
        "historical_backtest_run": result.historical_backtest_run,
        "2026q3_target_read": result.q3_target_read,
        "2026q3_source_outcome_loaded": result.q3_source_outcome_loaded,
        "next_action": result.next_action,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
