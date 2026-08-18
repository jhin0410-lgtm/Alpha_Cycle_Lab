from __future__ import annotations

from datetime import UTC, datetime

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_estimator_freeze import (
    build_ex_ante_estimator_freeze_preflight,
    load_frozen_ex_ante_estimator_selection,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    load_ex_ante_feature_frontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_lagged_filing import (
    build_locked_pit_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureObservation,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    load_frozen_company_gp_ex_ante_protocol,
)

_FEATURES = (
    "lagged_company_revenue",
    "lagged_company_gross_profit",
    "lagged_company_gross_margin",
    "lagged_nand_revenue_share",
    "lagged_other_revenue_share",
)
_CERTIFIED_14 = (
    "2017Q2",
    "2017Q3",
    "2018Q2",
    "2018Q3",
    "2019Q2",
    "2019Q3",
    "2020Q2",
    "2020Q3",
    "2023Q2",
    "2023Q3",
    "2024Q2",
    "2024Q3",
    "2025Q2",
    "2025Q3",
)


def _bundle(periods: tuple[str, ...]):
    observations: list[PointInTimeFeatureObservation] = []
    for period_index, period_id in enumerate(periods, start=1):
        year = int(period_id[:4])
        for feature_index, feature_id in enumerate(_FEATURES, start=1):
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
                    direct_source_fact=feature_id
                    in {"lagged_company_revenue", "lagged_company_gross_profit"},
                    deterministic_transform=feature_id
                    not in {"lagged_company_revenue", "lagged_company_gross_profit"},
                )
            )
    return build_locked_pit_feature_bundle(
        created_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
        observations=tuple(observations),
    )


def test_estimator_freeze_is_target_blind_and_has_fixed_candidate_geometry() -> None:
    freeze = load_frozen_ex_ante_estimator_selection()

    assert freeze.freeze_version == "1.0-frozen-pre-target-join"
    assert freeze.certified_base_target_rows == 14
    assert freeze.certified_base_feature_observations == 70
    assert freeze.minimum_scored_folds == 8
    assert freeze.shared_initial_training_rows == 12
    assert freeze.required_rows_before_first_target_join == 20
    assert tuple(item.parameter_count for item in freeze.candidates) == (2, 3, 4)
    assert tuple(item.minimum_training_rows for item in freeze.candidates) == (10, 11, 12)
    assert tuple(
        item.required_total_rows_for_eight_folds_if_scored_alone
        for item in freeze.candidates
    ) == (18, 19, 20)
    assert not freeze.target_join_allowed_now
    assert not freeze.estimator_fit_allowed_now
    assert not freeze.first_pit_backtest_run
    assert not freeze.q3_target_read


def test_current_14_row_certified_shape_remains_sample_incomplete() -> None:
    freeze = load_frozen_ex_ante_estimator_selection()
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()
    result = build_ex_ante_estimator_freeze_preflight(
        freeze,
        protocol,
        frontier,
        _bundle(_CERTIFIED_14),
    )

    assert result.current_target_blind_feature_rows == 14
    assert result.current_feature_observation_count == 70
    assert result.all_rows_have_exact_frozen_feature_set
    assert result.all_observations_point_in_time_eligible
    assert result.rejected_observation_count == 0
    assert result.shared_scored_folds_available_now == 2
    assert result.row_shortfall_before_first_target_join == 6
    assert not result.all_frozen_candidates_sample_eligible_now
    assert not result.target_join_authorized
    assert not result.estimator_fit_authorized
    assert not result.historical_backtest_run


def test_twenty_target_blind_rows_satisfy_sample_geometry_but_do_not_join_targets() -> None:
    freeze = load_frozen_ex_ante_estimator_selection()
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()
    periods = protocol.development_periods[:20]
    result = build_ex_ante_estimator_freeze_preflight(
        freeze,
        protocol,
        frontier,
        _bundle(periods),
    )

    assert result.current_target_blind_feature_rows == 20
    assert result.shared_scored_folds_available_now == 8
    assert result.row_shortfall_before_first_target_join == 0
    assert result.all_frozen_candidates_sample_eligible_now
    assert all(item.individually_sample_eligible_now for item in result.candidates)
    assert not result.target_join_authorized
    assert not result.estimator_fit_authorized
    assert not result.q3_target_read
    assert not result.q3_source_outcome_loaded
