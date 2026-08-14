from __future__ import annotations

from alpha_cycle.intelligence.portfolio_opportunity_cost import (
    PositionDecisionInputs,
    evaluate_position_decision_readiness,
)


def test_purchase_price_and_break_even_are_not_used_as_hold_reasons() -> None:
    readiness = evaluate_position_decision_readiness(
        PositionDecisionInputs(
            ticker="000660",
            current_market_value_available=True,
            thesis_validity_assessed=True,
            scenario_expected_return_available=False,
            downside_range_available=False,
            catalyst_horizon_available=False,
            thesis_invalidation_defined=True,
            holding_period_or_capital_lockup_assessed=False,
            alternative_expected_return_available=False,
            portfolio_overlap_assessed=True,
            liquidity_constraint_assessed=True,
            purchase_price_available=True,
            current_return_since_purchase_available=True,
        )
    )
    assert readiness.break_even_recovery_used_as_decision_input is False
    assert readiness.purchase_price_used_as_expected_return_anchor is False
    assert readiness.hold_or_replace_readiness == "blocked"
    assert "scenario_expected_return_missing" in readiness.blockers
    assert "alternative_expected_return_missing" in readiness.blockers
    assert readiness.action_recommendation_enabled is False


def test_add_requires_downside_catalyst_overlap_and_liquidity_context() -> None:
    readiness = evaluate_position_decision_readiness(
        PositionDecisionInputs(
            ticker="005930",
            current_market_value_available=True,
            thesis_validity_assessed=True,
            scenario_expected_return_available=True,
            downside_range_available=True,
            catalyst_horizon_available=True,
            thesis_invalidation_defined=True,
            holding_period_or_capital_lockup_assessed=True,
            alternative_expected_return_available=True,
            portfolio_overlap_assessed=False,
            liquidity_constraint_assessed=False,
        )
    )
    assert readiness.trim_or_exit_readiness == "available"
    assert readiness.opportunity_cost_readiness == "available"
    assert readiness.add_readiness == "blocked"
    assert "portfolio_overlap_not_assessed" in readiness.blockers
    assert "liquidity_constraint_not_assessed" in readiness.blockers
    assert readiness.action_recommendation_enabled is False


def test_fully_ready_position_can_enable_action_comparison_without_score() -> None:
    readiness = evaluate_position_decision_readiness(
        PositionDecisionInputs(
            ticker="012450",
            current_market_value_available=True,
            thesis_validity_assessed=True,
            scenario_expected_return_available=True,
            downside_range_available=True,
            catalyst_horizon_available=True,
            thesis_invalidation_defined=True,
            holding_period_or_capital_lockup_assessed=True,
            alternative_expected_return_available=True,
            portfolio_overlap_assessed=True,
            liquidity_constraint_assessed=True,
        )
    )
    assert readiness.hold_or_replace_readiness == "available"
    assert readiness.add_readiness == "available"
    assert readiness.trim_or_exit_readiness == "available"
    assert readiness.opportunity_cost_readiness == "available"
    assert readiness.action_recommendation_enabled is True
    assert readiness.decision_score_enabled is False
