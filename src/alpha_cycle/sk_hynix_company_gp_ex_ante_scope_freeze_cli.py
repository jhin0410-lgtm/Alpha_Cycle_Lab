from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE,
    DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE,
    build_exact_twenty_period_ex_ante_scope_freeze,
    persist_exact_twenty_period_ex_ante_scope_freeze,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze the exact twenty-period SK hynix target-blind ex-ante PIT scope "
            "before the first historical target join."
        )
    )
    parser.add_argument(
        "--expansion-report",
        default=str(DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_REPORT),
    )
    parser.add_argument(
        "--combined-bundle",
        default=str(DEFAULT_EX_ANTE_PIT_PANEL_EXPANSION_BUNDLE),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_COMPANY_GP_EX_ANTE_SCOPE_FREEZE),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scope = build_exact_twenty_period_ex_ante_scope_freeze(
        expansion_report_path=Path(args.expansion_report),
        combined_bundle_path=Path(args.combined_bundle),
    )
    output = persist_exact_twenty_period_ex_ante_scope_freeze(
        scope,
        Path(args.output),
    )
    payload = {
        "status": scope.status,
        "scope_evidence_id": scope.evidence_id,
        "protocol_evidence_id": scope.protocol_evidence_id,
        "feature_frontier_evidence_id": scope.feature_frontier_evidence_id,
        "estimator_freeze_evidence_id": scope.estimator_freeze_evidence_id,
        "expansion_contract_evidence_id": scope.expansion_contract_evidence_id,
        "expansion_report_sha256": scope.expansion_report_sha256,
        "base_bundle_evidence_id": scope.base_bundle_evidence_id,
        "combined_bundle_evidence_id": scope.combined_bundle_evidence_id,
        "target_periods": list(scope.target_periods),
        "target_row_count": scope.target_row_count,
        "feature_observation_count": scope.feature_observation_count,
        "selected_legacy_year": scope.selected_legacy_year,
        "shared_initial_training_rows": scope.shared_initial_training_rows,
        "scored_fold_count": scope.scored_fold_count,
        "all_observations_point_in_time_eligible": (
            scope.all_observations_point_in_time_eligible
        ),
        "all_frozen_candidates_sample_eligible": (
            scope.all_frozen_candidates_sample_eligible
        ),
        "historical_target_values_read": scope.historical_target_values_read,
        "target_join_authorized": scope.target_join_authorized,
        "estimator_fit_authorized": scope.estimator_fit_authorized,
        "historical_backtest_run": scope.historical_backtest_run,
        "2026q3_target_read": scope.q3_target_read,
        "2026q3_source_outcome_loaded": scope.q3_source_outcome_loaded,
        "output": str(output),
        "next_action": scope.next_action,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
