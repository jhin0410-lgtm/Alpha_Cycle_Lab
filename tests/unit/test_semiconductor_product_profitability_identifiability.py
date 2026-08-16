from __future__ import annotations

import pytest

from alpha_cycle.intelligence.semiconductor_product_profitability_identifiability import (
    ProductProfitabilityIdentifiability,
    assess_product_profitability_identifiability,
)


def test_missing_direct_product_profitability_requires_calibration_and_forbids_shortcuts() -> None:
    result = assess_product_profitability_identifiability(
        "000660",
        required_product_blocks=("dram_total", "nand_and_solutions"),
    )
    assert result.direct_product_profitability_metrics_required == 2
    assert result.direct_product_profitability_metrics_available == 0
    assert result.identifiable_from_source_facts is False
    assert result.calibrated_assumption_required is True
    assert result.calibration_status == "direct_product_profitability_source_facts_missing"
    assert result.revenue_share_profit_allocation_source_fact_allowed is False
    assert result.residual_profit_allocation_source_fact_allowed is False
    assert result.peer_margin_substitution_source_fact_allowed is False
    assert result.product_profitability_certified is False
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_complete_direct_product_profitability_is_identifiable_but_still_non_forecast() -> None:
    result = assess_product_profitability_identifiability(
        "000660",
        required_product_blocks=("dram_total", "nand_and_solutions"),
        directly_disclosed_product_profitability_blocks=("dram_total", "nand_and_solutions"),
    )
    assert result.direct_product_profitability_metrics_available == 2
    assert result.identifiable_from_source_facts is True
    assert result.calibrated_assumption_required is False
    assert result.calibration_status == "direct_product_profitability_source_facts_complete"
    assert result.product_profitability_certified is True
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_partial_product_profitability_does_not_solve_remaining_product_margin() -> None:
    result = assess_product_profitability_identifiability(
        "000660",
        required_product_blocks=("dram_total", "nand_and_solutions"),
        directly_disclosed_product_profitability_blocks=("dram_total",),
    )
    assert result.direct_product_profitability_metrics_available == 1
    assert result.identifiable_from_source_facts is False
    assert result.calibrated_assumption_required is True
    assert result.product_profitability_certified is False


def test_identifiability_rejects_promoting_revenue_share_profit_allocation_to_source_fact() -> None:
    with pytest.raises(ValueError, match="cannot be promoted to source fact"):
        ProductProfitabilityIdentifiability(
            ticker="000660",
            required_product_blocks=("dram_total", "nand_and_solutions"),
            directly_disclosed_product_profitability_blocks=(),
            direct_product_profitability_metrics_required=2,
            direct_product_profitability_metrics_available=0,
            identifiable_from_source_facts=False,
            calibrated_assumption_required=True,
            calibration_status="direct_product_profitability_source_facts_missing",
            revenue_share_profit_allocation_source_fact_allowed=True,
            product_profitability_certified=False,
        )


def test_identifiability_requires_at_least_one_product_block() -> None:
    with pytest.raises(ValueError, match="requires product blocks"):
        assess_product_profitability_identifiability("000660", required_product_blocks=())
