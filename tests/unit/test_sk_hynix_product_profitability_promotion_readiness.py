from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sk_hynix_product_profitability_promotion_readiness import (
    build_promotion_readiness,
    classify_driver_interval,
    load_promotion_readiness_policy,
)
from alpha_cycle.intelligence.sk_hynix_product_profitability_structural_method import (
    load_structural_profitability_method,
)


def _driver(source_text: str) -> SimpleNamespace:
    return SimpleNamespace(source_text=source_text)


def _row(index: int, *, open_interval: bool = False) -> SimpleNamespace:
    scale = float(index + 1)
    return SimpleNamespace(
        dram_revenue_krw_million=1000.0 * scale,
        nand_revenue_krw_million=500.0 * scale + 17.0 * index,
        other_revenue_krw_million=100.0 + 13.0 * index,
        dram_asp=_driver("Over 70% Increase" if open_interval else "Mid-teen% Increase"),
        dram_bit_volume=_driver("High-single% Decrease"),
        nand_asp=_driver("Around 20% Increase"),
        nand_bit_volume=_driver("Mid-single% Decrease"),
    )


def test_interval_semantics_preserve_method_assumption_boundary() -> None:
    policy = load_promotion_readiness_policy()

    bounded = classify_driver_interval("Mid-teen% Increase", policy)
    assert bounded.direction == "increase"
    assert bounded.lower_abs_percent == 13.0
    assert bounded.upper_abs_percent == 17.0
    assert bounded.closed_interval is True
    assert bounded.source_fact is False
    assert bounded.method_assumption is True
    assert bounded.estimation_input_ready is False

    around = classify_driver_interval("Around 20% Decrease", policy)
    assert around.direction == "decrease"
    assert around.lower_abs_percent == 18.0
    assert around.upper_abs_percent == 22.0


def test_over_language_remains_open_ended() -> None:
    policy = load_promotion_readiness_policy()
    interval = classify_driver_interval("Over 70% Increase", policy)

    assert interval.interval_kind == "open_over"
    assert interval.lower_abs_percent == 70.0
    assert interval.upper_abs_percent is None
    assert interval.closed_interval is False


def test_current_shape_fails_closed_before_estimation() -> None:
    policy = load_promotion_readiness_policy()
    method = load_structural_profitability_method()
    rows = tuple(_row(index, open_interval=index == 0) for index in range(9))
    rank_probe = SimpleNamespace(
        evidence_id="a" * 64,
        evaluation_date=date(2026, 8, 17),
        method_manifest_sha256=method.manifest_sha256,
        row_count=9,
        parameter_count=7,
        rows=rows,
        rank_probe_ready=True,
        company_product_revenue_reconciliation_certified=True,
        training_periods=(
            "2023Q1",
            "2023Q2",
            "2023Q3",
            "2024Q1",
            "2024Q2",
            "2024Q3",
            "2025Q1",
            "2025Q2",
            "2025Q3",
        ),
        holdout_evaluation_allowed=False,
    )

    result = build_promotion_readiness(
        policy,
        method,
        rank_probe,  # type: ignore[arg-type]
        evaluation_date=date(2026, 8, 17),
    )

    assert result.required_training_rows == 15
    assert result.additional_training_rows_required == 6
    assert result.residual_degrees_of_freedom == 2
    assert result.sample_depth_gate_passed is False
    assert result.rank_probe_ready is True
    assert result.company_product_revenue_reconciliation_certified is True
    assert result.closed_interval_sensitivity_coverage_complete is False
    assert result.open_interval_source_texts == ("Over 70% Increase",)
    assert result.estimation_driver_input_ready is False
    assert result.method_version_frozen is False
    assert result.holdout_sealed is True
    assert result.promotion_to_frozen_estimation_candidate_allowed is False
    assert result.fit_attempt_allowed is False
    assert result.holdout_evaluation_allowed is False
    assert result.block_reasons == (
        "historical_sample_depth_insufficient",
        "open_ended_interval_language_present",
        "estimation_driver_input_not_source_certified",
        "structural_method_not_frozen",
    )


def test_policy_never_promotes_interval_assumptions_to_source_facts() -> None:
    policy = load_promotion_readiness_policy()
    assert policy.interval_source_fact is False
    assert policy.interval_method_assumption is True
    assert policy.interval_estimation_input_ready is False
    assert policy.interval_sensitivity_is_formal_partial_identification is False
    assert policy.interval_sensitivity_can_enable_fit is False
    assert policy.numeric_forecast_enabled is False
    assert policy.fair_value_estimate_enabled is False
    assert policy.target_price_enabled is False
    assert policy.decision_score_enabled is False
