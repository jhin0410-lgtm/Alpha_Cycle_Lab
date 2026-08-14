from __future__ import annotations

from alpha_cycle.intelligence.scenario_expected_return import (
    SECTOR_SCENARIO_DEFINITIONS,
    ScenarioReadinessInputs,
    evaluate_scenario_expected_return_readiness,
)


def test_sector_scenario_drivers_are_materially_distinct() -> None:
    semiconductor = SECTOR_SCENARIO_DEFINITIONS["semiconductor"]
    defense = SECTOR_SCENARIO_DEFINITIONS["defense"]
    shipbuilding = SECTOR_SCENARIO_DEFINITIONS["shipbuilding"]
    nuclear = SECTOR_SCENARIO_DEFINITIONS["nuclear"]
    construction = SECTOR_SCENARIO_DEFINITIONS["construction"]

    assert "hbm_volume_and_product_mix" in semiconductor.operating_drivers
    assert "export_award_pipeline" in defense.operating_drivers
    assert "newbuild_price" in shipbuilding.operating_drivers
    assert "project_award_probability" in nuclear.operating_drivers
    assert "pf_credit_conditions" in construction.operating_drivers
    assert set(semiconductor.operating_drivers) != set(defense.operating_drivers)
    assert set(defense.operating_drivers) != set(shipbuilding.operating_drivers)


def test_scenario_price_range_requires_forward_model_and_valuation_anchor() -> None:
    readiness = evaluate_scenario_expected_return_readiness(
        ScenarioReadinessInputs(
            sector_id="semiconductor",
            current_price_available=True,
            internal_forward_model_certified=False,
            forward_horizon_certified=False,
            required_operating_drivers_available=False,
            valuation_anchor_certified=False,
            catalyst_timing_available=False,
            market_expectation_level_certified=False,
        )
    )
    assert readiness.scenario_operating_view_status == "blocked"
    assert readiness.valuation_range_status == "blocked"
    assert readiness.expected_return_status == "blocked"
    assert readiness.expectation_gap_context_status == "blocked"
    assert readiness.price_range_enabled is False
    assert readiness.expected_return_enabled is False
    assert readiness.scenario_probabilities_enabled is False
    assert "internal_forward_model_not_certified" in readiness.blockers
    assert "valuation_anchor_not_certified" in readiness.blockers


def test_expected_return_can_enable_without_fabricated_scenario_probabilities() -> None:
    readiness = evaluate_scenario_expected_return_readiness(
        ScenarioReadinessInputs(
            sector_id="defense",
            current_price_available=True,
            internal_forward_model_certified=True,
            forward_horizon_certified=True,
            required_operating_drivers_available=True,
            valuation_anchor_certified=True,
            catalyst_timing_available=True,
            market_expectation_level_certified=True,
        )
    )
    assert readiness.scenario_operating_view_status == "available"
    assert readiness.valuation_range_status == "available"
    assert readiness.expected_return_status == "available"
    assert readiness.expectation_gap_context_status == "available"
    assert readiness.price_range_enabled is True
    assert readiness.expected_return_enabled is True
    assert readiness.scenario_probabilities_enabled is False
    assert readiness.decision_score_enabled is False
