from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE,
    build_ex_ante_estimator_freeze_preflight,
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER,
    load_ex_ante_feature_frontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    DEFAULT_LAGGED_FILING_BUNDLE,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    load_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL,
    load_frozen_company_gp_ex_ante_protocol,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the target-blind SK hynix ex-ante estimator freeze without "
            "loading GP targets"
        )
    )
    parser.add_argument(
        "--freeze",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_ESTIMATOR_FREEZE),
    )
    parser.add_argument(
        "--protocol",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_PROTOCOL),
    )
    parser.add_argument(
        "--frontier",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_FEATURE_FRONTIER),
    )
    parser.add_argument("--bundle", default=str(DEFAULT_LAGGED_FILING_BUNDLE))
    return parser


def main() -> int:
    args = _parser().parse_args()
    freeze = load_frozen_ex_ante_estimator_selection(Path(args.freeze))
    protocol = load_frozen_company_gp_ex_ante_protocol(Path(args.protocol))
    frontier = load_ex_ante_feature_frontier(Path(args.frontier))
    bundle = load_point_in_time_feature_bundle(Path(args.bundle))
    result = build_ex_ante_estimator_freeze_preflight(
        freeze,
        protocol,
        frontier,
        bundle,
    )

    if result.row_shortfall_before_first_target_join > 0:
        next_action = (
            "expand_target_blind_pit_development_panel_to_at_least_20_rows_"
            "and_refreeze_period_scope_before_first_target_join"
        )
    else:
        next_action = (
            "implement_separate_target_join_and_chronological_backtest_runner_"
            "without_changing_the_frozen_candidates"
        )

    sample_ready = (
        result.all_frozen_candidates_sample_eligible_now
        and result.shared_scored_folds_available_now >= result.minimum_scored_folds
    )
    payload = {
        "status": (
            "skhynix_ex_ante_estimator_freeze_sample_ready"
            if sample_ready
            else "skhynix_ex_ante_estimator_freeze_sample_incomplete"
        ),
        "freeze_version": freeze.freeze_version,
        "freeze_evidence_id": freeze.evidence_id,
        "bundle_evidence_id": bundle.evidence_id,
        "current_target_blind_feature_rows": result.current_target_blind_feature_rows,
        "current_feature_observation_count": result.current_feature_observation_count,
        "all_rows_have_exact_frozen_feature_set": (
            result.all_rows_have_exact_frozen_feature_set
        ),
        "all_observations_point_in_time_eligible": (
            result.all_observations_point_in_time_eligible
        ),
        "rejected_observation_count": result.rejected_observation_count,
        "shared_initial_training_rows": result.shared_initial_training_rows,
        "minimum_scored_folds": result.minimum_scored_folds,
        "shared_scored_folds_available_now": result.shared_scored_folds_available_now,
        "required_rows_before_first_target_join": (
            result.required_rows_before_first_target_join
        ),
        "row_shortfall_before_first_target_join": (
            result.row_shortfall_before_first_target_join
        ),
        "candidate_preflight": [asdict(item) for item in result.candidates],
        "all_frozen_candidates_sample_eligible_now": (
            result.all_frozen_candidates_sample_eligible_now
        ),
        "target_join_authorized": result.target_join_authorized,
        "estimator_fit_authorized": result.estimator_fit_authorized,
        "historical_backtest_run": result.historical_backtest_run,
        "2026q3_target_read": result.q3_target_read,
        "2026q3_source_outcome_loaded": result.q3_source_outcome_loaded,
        "next_action": next_action,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
