from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    build_locked_pit_feature_bundle,
    persist_locked_pit_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureObservation,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit_panel_expansion import (
    load_frozen_pit_panel_expansion_contract,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_scope_freeze import (
    build_exact_twenty_period_ex_ante_scope_freeze,
    load_frozen_exact_twenty_period_ex_ante_scope,
    persist_exact_twenty_period_ex_ante_scope_freeze,
)

_PERIODS = tuple(
    f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
)
_ADDED_PERIODS = (
    "2021Q2",
    "2021Q3",
    "2022Q2",
    "2022Q3",
    "2016Q2",
    "2016Q3",
)
_FEATURES = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)


def _write_bundle(path: Path) -> str:
    observations: list[PointInTimeFeatureObservation] = []
    for period_index, period_id in enumerate(_PERIODS, start=1):
        year = int(period_id[:4])
        for feature_index, feature_id in enumerate(_FEATURES, start=1):
            direct = feature_id in {
                "lagged_company_revenue",
                "lagged_company_gross_profit",
            }
            observations.append(
                PointInTimeFeatureObservation(
                    period_id=period_id,
                    feature_id=feature_id,
                    value=float(period_index * 10 + feature_index),
                    provenance_class="timestamped_immutable_filing",
                    source_available_at=datetime(year, 1, 1, tzinfo=UTC),
                    source_bytes_sha256="a" * 64,
                    source_evidence_id="b" * 64,
                    source_version_identity=f"test:{period_id}",
                    direct_source_fact=direct,
                    deterministic_transform=not direct,
                )
            )
    bundle = build_locked_pit_feature_bundle(
        created_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
        observations=tuple(observations),
    )
    persist_locked_pit_feature_bundle(bundle, path)
    return bundle.evidence_id


def _write_report(
    path: Path,
    combined_bundle_evidence_id: str,
    *,
    combined_periods: tuple[str, ...] = _PERIODS,
    attempt_target_value_read: bool = False,
) -> None:
    contract = load_frozen_pit_panel_expansion_contract()
    attempts = [
        {
            "source_period": source_period,
            "target_period": target_period,
            "success": True,
            "receipt_no": "20160516000001",
            "receipt_date": "2016-05-16",
            "company_raw_bytes_sha256": "c" * 64,
            "product_archive_sha256": "d" * 64,
            "error_type": None,
            "error": None,
            "target_value_read": attempt_target_value_read,
            "estimator_fit_run": False,
            "backtest_run": False,
        }
        for source_period, target_period in (
            ("2021Q1", "2021Q2"),
            ("2021Q2", "2021Q3"),
            ("2022Q1", "2022Q2"),
            ("2022Q2", "2022Q3"),
            ("2016Q1", "2016Q2"),
            ("2016Q2", "2016Q3"),
        )
    ]
    payload = {
        "schema_version": 1,
        "status": "skhynix_ex_ante_pit_panel_expansion_complete_target_blind",
        "result": {
            "contract_evidence_id": contract.evidence_id,
            "base_bundle_evidence_id": contract.base_bundle_evidence_id,
            "selected_legacy_year": 2016,
            "attempts": attempts,
            "added_target_periods": list(_ADDED_PERIODS),
            "added_target_row_count": 6,
            "added_feature_observation_count": 30,
            "combined_target_periods": list(combined_periods),
            "combined_target_row_count": 20,
            "combined_feature_observation_count": 100,
            "combined_bundle_evidence_id": combined_bundle_evidence_id,
            "eligible_added_observation_count": 30,
            "rejected_added_observation_count": 0,
            "all_added_observations_point_in_time_eligible": True,
            "completion_gate_passed": True,
            "status": "skhynix_ex_ante_pit_panel_expansion_complete_target_blind",
            "next_action": (
                "refreeze_exact_twenty_period_ex_ante_scope_before_first_target_join"
            ),
            "historical_target_values_read": False,
            "target_join_authorized": False,
            "estimator_fit_authorized": False,
            "historical_backtest_run": False,
            "q3_target_read": False,
            "q3_source_outcome_loaded": False,
        },
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_scope_freeze_binds_exact_twenty_row_target_blind_panel(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "report.json"
    output_path = tmp_path / "scope" / "latest_scope_freeze.json"
    bundle_id = _write_bundle(bundle_path)
    _write_report(report_path, bundle_id)

    scope = build_exact_twenty_period_ex_ante_scope_freeze(
        expansion_report_path=report_path,
        combined_bundle_path=bundle_path,
        frozen_at=datetime(2026, 8, 21, 13, 30, tzinfo=UTC),
    )
    persisted = persist_exact_twenty_period_ex_ante_scope_freeze(scope, output_path)
    replayed = load_frozen_exact_twenty_period_ex_ante_scope(persisted)

    assert scope.target_periods == _PERIODS
    assert scope.target_row_count == 20
    assert scope.feature_observation_count == 100
    assert scope.selected_legacy_year == 2016
    assert scope.shared_initial_training_rows == 12
    assert scope.scored_fold_count == 8
    assert scope.all_observations_point_in_time_eligible
    assert scope.all_frozen_candidates_sample_eligible
    assert scope.combined_bundle_evidence_id == bundle_id
    assert not scope.historical_target_values_read
    assert not scope.target_join_authorized
    assert not scope.estimator_fit_authorized
    assert not scope.historical_backtest_run
    assert not scope.q3_target_read
    assert not scope.q3_source_outcome_loaded
    assert replayed == scope
    assert (output_path.parent / f"scope-{scope.evidence_id}.json").is_file()


def test_scope_freeze_rejects_target_period_drift_before_join(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "report.json"
    bundle_id = _write_bundle(bundle_path)
    drifted = (*_PERIODS[:-1], "2015Q3")
    _write_report(report_path, bundle_id, combined_periods=drifted)

    with pytest.raises(ValueError, match="combined target-period scope drifted"):
        build_exact_twenty_period_ex_ante_scope_freeze(
            expansion_report_path=report_path,
            combined_bundle_path=bundle_path,
        )


def test_scope_freeze_rejects_any_source_attempt_that_read_a_target(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    report_path = tmp_path / "report.json"
    bundle_id = _write_bundle(bundle_path)
    _write_report(report_path, bundle_id, attempt_target_value_read=True)

    with pytest.raises(ValueError, match="source replay crossed"):
        build_exact_twenty_period_ex_ante_scope_freeze(
            expansion_report_path=report_path,
            combined_bundle_path=bundle_path,
        )
