from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_estimation_method import (
    load_frozen_regime_estimation_method,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_regime_validation_protocol import (
    load_regime_validation_protocol,
)


def test_frozen_regime_method_is_bound_before_outcomes() -> None:
    method = load_frozen_regime_estimation_method()
    protocol = load_regime_validation_protocol(method)

    assert method.method_version == "1.0-frozen-pre-holdout"
    assert method.method_version_frozen is True
    assert len(method.training_periods) == 15
    assert method.parameter_count == 7
    assert method.holdout_period == "2026Q1"
    assert method.driver_encoding.semantics == "categorical_direction_regime"
    assert method.driver_encoding.exact_numeric_second_wave_magnitude_used_for_fit is False
    assert method.coefficient_outcomes_seen_before_freeze is False
    assert method.training_fit_metrics_seen_before_freeze is False
    assert method.holdout_outcome_seen_before_freeze is False
    assert protocol.method_evidence_id == method.evidence_id
    assert protocol.company_revenue_reconciliation_tolerance_krw == 1_000_000
    assert protocol.holdout_may_be_scored_before_training_gate is False
    assert protocol.require_immutable_result_reuse is True
    assert protocol.refit_after_holdout_allowed is False
