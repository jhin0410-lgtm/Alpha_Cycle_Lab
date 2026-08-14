"""Portfolio and opportunity-cost readiness for thesis-driven position decisions.

The contract deliberately ignores purchase price and break-even recovery as
reasons to hold.  Replacement/add/trim decisions require current-price expected
return, downside, thesis validity, catalyst timing, and capital-lockup context.
When those inputs are missing the framework reports research blockers rather than
inventing a portfolio action.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionDecisionInputs:
    ticker: str
    current_market_value_available: bool
    thesis_validity_assessed: bool
    scenario_expected_return_available: bool
    downside_range_available: bool
    catalyst_horizon_available: bool
    thesis_invalidation_defined: bool
    holding_period_or_capital_lockup_assessed: bool
    alternative_expected_return_available: bool
    portfolio_overlap_assessed: bool
    liquidity_constraint_assessed: bool
    purchase_price_available: bool = False
    current_return_since_purchase_available: bool = False


@dataclass(frozen=True)
class PositionDecisionReadiness:
    ticker: str
    hold_or_replace_readiness: str
    add_readiness: str
    trim_or_exit_readiness: str
    opportunity_cost_readiness: str
    blockers: tuple[str, ...]
    break_even_recovery_used_as_decision_input: bool = False
    purchase_price_used_as_expected_return_anchor: bool = False
    action_recommendation_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        allowed = {"available", "blocked"}
        for status in (
            self.hold_or_replace_readiness,
            self.add_readiness,
            self.trim_or_exit_readiness,
            self.opportunity_cost_readiness,
        ):
            if status not in allowed:
                raise ValueError("Portfolio readiness status is invalid")
        if self.break_even_recovery_used_as_decision_input:
            raise ValueError("Break-even recovery cannot be a portfolio decision input")
        if self.purchase_price_used_as_expected_return_anchor:
            raise ValueError("Purchase price cannot anchor current expected return")
        if self.decision_score_enabled:
            raise ValueError("Portfolio opportunity-cost readiness must remain non-scoring")


def evaluate_position_decision_readiness(
    inputs: PositionDecisionInputs,
) -> PositionDecisionReadiness:
    if len(inputs.ticker) != 6 or not inputs.ticker.isdigit():
        raise ValueError("Portfolio ticker must be six digits")

    common = {
        "current_market_value_missing": inputs.current_market_value_available,
        "thesis_validity_not_assessed": inputs.thesis_validity_assessed,
        "scenario_expected_return_missing": inputs.scenario_expected_return_available,
        "downside_range_missing": inputs.downside_range_available,
        "catalyst_horizon_missing": inputs.catalyst_horizon_available,
        "thesis_invalidation_missing": inputs.thesis_invalidation_defined,
        "capital_lockup_not_assessed": inputs.holding_period_or_capital_lockup_assessed,
    }
    common_blockers = tuple(
        blocker for blocker, satisfied in common.items() if not satisfied
    )
    hold_replace_blockers = list(common_blockers)
    if not inputs.alternative_expected_return_available:
        hold_replace_blockers.append("alternative_expected_return_missing")
    if not inputs.portfolio_overlap_assessed:
        hold_replace_blockers.append("portfolio_overlap_not_assessed")

    add_blockers = list(common_blockers)
    if not inputs.portfolio_overlap_assessed:
        add_blockers.append("portfolio_overlap_not_assessed")
    if not inputs.liquidity_constraint_assessed:
        add_blockers.append("liquidity_constraint_not_assessed")

    trim_blockers = list(common_blockers)
    opportunity_blockers = []
    if not inputs.scenario_expected_return_available:
        opportunity_blockers.append("current_asset_expected_return_missing")
    if not inputs.alternative_expected_return_available:
        opportunity_blockers.append("alternative_expected_return_missing")
    if not inputs.holding_period_or_capital_lockup_assessed:
        opportunity_blockers.append("capital_lockup_not_assessed")

    all_blockers = tuple(
        dict.fromkeys(
            (*hold_replace_blockers, *add_blockers, *trim_blockers, *opportunity_blockers)
        )
    )
    actions_ready = (
        not hold_replace_blockers
        and not add_blockers
        and not trim_blockers
        and not opportunity_blockers
    )
    return PositionDecisionReadiness(
        ticker=inputs.ticker,
        hold_or_replace_readiness="available" if not hold_replace_blockers else "blocked",
        add_readiness="available" if not add_blockers else "blocked",
        trim_or_exit_readiness="available" if not trim_blockers else "blocked",
        opportunity_cost_readiness=(
            "available" if not opportunity_blockers else "blocked"
        ),
        blockers=all_blockers,
        break_even_recovery_used_as_decision_input=False,
        purchase_price_used_as_expected_return_anchor=False,
        action_recommendation_enabled=actions_ready,
        decision_score_enabled=False,
    )


__all__ = [
    "PositionDecisionInputs",
    "PositionDecisionReadiness",
    "evaluate_position_decision_readiness",
]
