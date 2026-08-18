from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_product_profitability_expanded_logit_margin_method import (
    load_frozen_expanded_logit_margin_method,
)


def test_v3_method_is_frozen_on_clean_21_rows_and_keeps_q3_sealed() -> None:
    method = load_frozen_expanded_logit_margin_method()

    assert method.method_version == "3.0-frozen-pre-fit"
    assert method.training_periods[:6] == (
        "2017Q1",
        "2017Q2",
        "2017Q3",
        "2018Q1",
        "2018Q2",
        "2018Q3",
    )
    assert len(method.training_periods) == 21
    assert "2026Q1" not in method.training_periods
    assert method.contaminated_stress_periods == ("2026Q1",)
    assert method.untouched_holdout_period == "2026Q3"
    assert method.parameter_count == 7
    assert method.prefit_identification_gate.required_residual_degrees_of_freedom == 14
    assert method.prefit_identification_gate.require_full_direction_design_rank is True
    assert (
        method.prefit_identification_gate.require_all_leave_one_out_direction_designs_full_rank
        is True
    )
    assert method.validation_gate.required_row_count == 21
    assert method.validation_gate.require_loocv_mae_better_than_benchmark is True
    assert method.v2_coefficients_seen is True
    assert method.v2_metrics_seen is True
    assert method.v2_gate_failure_seen is True
    assert method.third_wave_preflight_seen is True
    assert method.v3_coefficients_seen_before_freeze is False
    assert method.v3_fit_metrics_seen_before_freeze is False
    assert method.q1_stress_only is True
    assert method.q1_used_for_fit is False
    assert method.q1_used_for_model_selection_gate is False
    assert method.q3_outcome_seen_before_freeze is False
    assert method.numeric_forward_forecast_enabled is False
    assert method.target_price_enabled is False
    assert method.decision_score_enabled is False
