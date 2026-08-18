from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_reduced_identifiable_method import (
    load_frozen_reduced_identifiable_method,
)


def test_v4_method_is_frozen_reduced_and_keeps_q3_sealed() -> None:
    method = load_frozen_reduced_identifiable_method()

    assert method.method_version == "4.0-frozen-pre-fit"
    assert method.parameter_count == 5
    assert method.training_periods[:3] == ("2017Q1", "2017Q2", "2017Q3")
    assert method.training_periods[-1] == "2025Q3"
    assert method.contaminated_stress_periods == ("2026Q1",)
    assert method.untouched_holdout_period == "2026Q3"
    assert method.prefit_gate.required_row_count == 21
    assert method.prefit_gate.required_residual_degrees_of_freedom == 16
    assert method.validation_gate.required_parameter_count == 5
    assert method.v3_nullspace_seen_before_freeze is True
    assert method.v4_coefficients_seen_before_freeze is False
    assert method.v4_fit_metrics_seen_before_freeze is False
    assert method.holdout_outcome_seen_before_freeze is False
    assert method.other_margin_claimed_zero is False
    assert method.other_contribution_role == "unmodeled_company_gross_profit_residual"
    assert method.q1_used_for_fit is False
    assert method.q1_used_for_model_selection_gate is False
    assert method.q3_reserved_future_holdout is True
    assert method.numeric_forward_forecast_enabled is False
    assert method.target_price_enabled is False
    assert method.decision_score_enabled is False
