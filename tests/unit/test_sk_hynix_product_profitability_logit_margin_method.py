from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_logit_margin_method import (
    load_frozen_logit_margin_method,
)


def test_v2_method_is_frozen_before_fit_and_reserves_q3() -> None:
    method = load_frozen_logit_margin_method()

    assert method.method_version == "2.0-frozen-pre-fit"
    assert method.training_periods[-1] == "2026Q1"
    assert method.contaminated_development_periods == ("2026Q1",)
    assert method.untouched_holdout_period == "2026Q3"
    assert method.parameter_count == 7
    assert method.validation_gate.required_row_count == 16
    assert method.validation_gate.required_residual_degrees_of_freedom == 9
    assert method.v1_2026q1_holdout_seen_before_v2_freeze is True
    assert method.v2_coefficients_seen_before_freeze is False
    assert method.v2_fit_metrics_seen_before_freeze is False
    assert method.holdout_outcome_seen_before_freeze is False
    assert method.numeric_forward_forecast_enabled is False
    assert method.target_price_enabled is False
    assert method.decision_score_enabled is False
