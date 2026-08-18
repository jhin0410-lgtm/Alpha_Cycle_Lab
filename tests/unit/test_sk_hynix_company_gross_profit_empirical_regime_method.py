from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_company_gross_profit_empirical_regime_method import (
    load_frozen_company_gp_empirical_method,
)


def test_v5_method_is_frozen_empirical_scope_only() -> None:
    method = load_frozen_company_gp_empirical_method()

    assert method.method_version == "5.0-frozen-pre-fit"
    assert method.parameter_count == 7
    assert len(method.training_periods) == 21
    assert method.contaminated_stress_periods == ("2026Q1",)
    assert method.untouched_future_holdout_period == "2026Q3"
    assert method.coefficients_are_empirical_company_gp_weights is True
    assert method.coefficients_are_literal_product_margins is False
    assert method.product_margin_structural_interpretation_allowed is False
    assert method.v4_outcome_seen_before_freeze is True
    assert method.v5_coefficients_seen_before_freeze is False
    assert method.v5_fit_metrics_seen_before_freeze is False
    assert method.numeric_forward_forecast_enabled is False
    assert method.target_price_enabled is False
    assert method.decision_score_enabled is False
    assert method.product_margin_output_enabled is False
