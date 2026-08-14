from __future__ import annotations

from pathlib import Path


def test_package_routes_final_decision_builder_through_full_vertical_chain() -> None:
    package = Path("src/alpha_cycle/intelligence/__init__.py").read_text(encoding="utf-8")
    scenario = Path(
        "src/alpha_cycle/intelligence/decision_scenario_expected_return_calibrated.py"
    ).read_text(encoding="utf-8")
    catalyst = Path(
        "src/alpha_cycle/intelligence/decision_catalyst_horizon_calibrated.py"
    ).read_text(encoding="utf-8")
    expectation = Path(
        "src/alpha_cycle/intelligence/decision_expectation_gap_calibrated.py"
    ).read_text(encoding="utf-8")
    macro = Path(
        "src/alpha_cycle/intelligence/decision_macro_liquidity_calibrated.py"
    ).read_text(encoding="utf-8")
    structural = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_structural_calibrated.py"
    ).read_text(encoding="utf-8")
    transmission = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_transmission_calibrated.py"
    ).read_text(encoding="utf-8")
    sector = Path(
        "src/alpha_cycle/intelligence/decision_sector_vertical_calibrated.py"
    ).read_text(encoding="utf-8")

    for wrapper in (
        "decision_industry_evidence_calibrated",
        "decision_forward_estimate_calibrated",
        "decision_historical_pb_calibrated",
        "decision_sector_vertical_calibrated",
        "decision_semiconductor_transmission_calibrated",
        "decision_semiconductor_structural_calibrated",
        "decision_macro_liquidity_calibrated",
        "decision_expectation_gap_calibrated",
        "decision_catalyst_horizon_calibrated",
        "decision_scenario_expected_return_calibrated",
    ):
        assert wrapper in package
    assert (
        "from alpha_cycle.intelligence.decision_scenario_expected_return_calibrated import"
        in package
    )

    assert "decision_catalyst_horizon_calibrated" in scenario
    assert "_build_catalyst_snapshot" in scenario
    assert "build_scenario_expected_return_decision_evidence" in scenario

    assert "decision_expectation_gap_calibrated" in catalyst
    assert "_build_expectation_snapshot" in catalyst
    assert "load_catalyst_horizon_decision_evidence" in catalyst

    assert "decision_macro_liquidity_calibrated" in expectation
    assert "_build_macro_liquidity_snapshot" in expectation
    assert "build_expectation_gap_decision_evidence" in expectation

    assert "decision_semiconductor_structural_calibrated" in macro
    assert "_build_structural_snapshot" in macro
    assert "build_macro_liquidity_decision_evidence" in macro

    assert "decision_semiconductor_transmission_calibrated" in structural
    assert "_build_transmission_snapshot" in structural
    assert "load_structural_decision_evidence" in structural

    assert "decision_sector_vertical_calibrated" in transmission
    assert "_build_sector_vertical_snapshot" in transmission
    assert "build_semiconductor_transmission_evidence" in transmission

    assert "decision_historical_pb_calibrated" in sector
    assert "_build_historical_pb_snapshot" in sector
    assert "build_semiconductor_vertical_assessment" in sector
    assert "sector_vertical_missing_evidence_not_zero_scored" in sector
