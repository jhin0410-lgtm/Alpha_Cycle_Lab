from __future__ import annotations

import json

import pandas as pd

from alpha_cycle.intelligence.scenario_expected_return_decision_evidence import (
    append_scenario_expected_return_report,
    build_scenario_expected_return_decision_evidence,
)


def _scorecards() -> pd.DataFrame:
    common = {
        "structural_hbm_demand_mix_status": "partial",
        "structural_hbm_capacity_yield_status": "partial",
        "structural_competitive_position_status": "partial",
        "structural_end_demand_status": "partial",
        "structural_memory_pricing_status": "partial",
        "semiconductor_transmission_history_ready": True,
        "expectation_gap_expectation_level_status": "blocked",
        "expectation_gap_internal_forward_view_status": "historical_transmission_only_not_forward_model",
        "future_certified_event_count": 0,
        "scenario_valuation_anchor_certified": False,
        "scenario_forward_horizon_certified": False,
    }
    return pd.DataFrame(
        [
            {"ticker": "000660", "composite_score": 3.8, "valuation_score": pd.NA, **common},
            {"ticker": "005930", "composite_score": 3.6, "valuation_score": pd.NA, **common},
        ]
    )


def test_live_semiconductor_does_not_invent_price_range_or_expected_return() -> None:
    evidence = build_scenario_expected_return_decision_evidence(_scorecards())
    assert evidence.decision_score_enabled is False
    assert evidence.price_range_enabled is False
    assert evidence.expected_return_enabled is False
    assert len(evidence.rows) == 2
    assert evidence.rows["scenario_operating_view_status"].eq("blocked").all()
    assert evidence.rows["scenario_valuation_range_status"].eq("blocked").all()
    assert evidence.rows["scenario_expected_return_status"].eq("blocked").all()
    assert evidence.rows["scenario_price_range_enabled"].eq(False).all()
    assert evidence.rows["scenario_expected_return_enabled"].eq(False).all()
    assert evidence.rows["scenario_probabilities_enabled"].eq(False).all()

    hynix = evidence.rows.loc[evidence.rows["ticker"].eq("000660")].iloc[0]
    blockers = json.loads(str(hynix["scenario_blockers_json"]))
    assert "internal_forward_model_not_certified" in blockers
    assert "required_operating_drivers_missing" in blockers
    assert "valuation_anchor_not_certified" in blockers
    assert "catalyst_timing_missing" in blockers
    assert "market_expectation_level_not_certified" in blockers

    report = append_scenario_expected_return_report("# Base\n", evidence)
    assert "Scenario / Expected Return v1" in report
    assert "확률" in report
    assert "price range/expected return" in report
