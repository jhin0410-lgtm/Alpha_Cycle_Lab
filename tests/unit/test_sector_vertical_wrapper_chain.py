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
    crosscheck = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_company_actual_crosscheck_calibrated.py"
    ).read_text(encoding="utf-8")
    company_actual = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_company_actual_calibrated.py"
    ).read_text(encoding="utf-8")
    allocation = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_baseline_allocation_calibrated.py"
    ).read_text(encoding="utf-8")
    product_revenue = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_product_revenue_calibrated.py"
    ).read_text(encoding="utf-8")
    accounting = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_accounting_identity_calibrated.py"
    ).read_text(encoding="utf-8")
    baseline = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_baseline_reconciliation_calibrated.py"
    ).read_text(encoding="utf-8")
    assumptions = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_operating_assumption_calibrated.py"
    ).read_text(encoding="utf-8")
    forward_input = Path(
        "src/alpha_cycle/intelligence/decision_semiconductor_forward_input_calibrated.py"
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
        "decision_semiconductor_forward_input_calibrated",
        "decision_semiconductor_operating_assumption_calibrated",
        "decision_semiconductor_baseline_reconciliation_calibrated",
        "decision_semiconductor_accounting_identity_calibrated",
        "decision_semiconductor_product_revenue_calibrated",
        "decision_semiconductor_baseline_allocation_calibrated",
        "decision_semiconductor_company_actual_calibrated",
        "decision_semiconductor_company_actual_crosscheck_calibrated",
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
    assert "semiconductor_baseline_reconciliation_pointer" in scenario
    assert "semiconductor_accounting_identity_pointer" in scenario
    assert "semiconductor_baseline_allocation_pointer" in scenario
    assert "opendart_provisional_earnings_pointer" in scenario
    assert "sec_company_actual_pointer" in scenario

    assert "decision_expectation_gap_calibrated" in catalyst
    assert "_build_expectation_snapshot" in catalyst
    assert "load_catalyst_horizon_decision_evidence" in catalyst
    assert "semiconductor_baseline_reconciliation_pointer" in catalyst
    assert "semiconductor_accounting_identity_pointer" in catalyst
    assert "semiconductor_baseline_allocation_pointer" in catalyst
    assert "opendart_provisional_earnings_pointer" in catalyst
    assert "sec_company_actual_pointer" in catalyst

    assert "decision_semiconductor_company_actual_crosscheck_calibrated" in expectation
    assert "_build_company_actual_crosscheck_snapshot" in expectation
    assert "build_expectation_gap_decision_evidence" in expectation
    assert "semiconductor_accounting_identity_pointer" in expectation
    assert "semiconductor_baseline_allocation_pointer" in expectation
    assert "opendart_provisional_earnings_pointer" in expectation
    assert "sec_company_actual_pointer" in expectation

    assert "decision_semiconductor_company_actual_calibrated" in crosscheck
    assert "_build_company_actual_snapshot" in crosscheck
    assert "load_sec_company_actual_decision_evidence" in crosscheck
    assert "build_company_actual_crosscheck" in crosscheck
    assert "company_actual_crosscheck_product_baseline_eligible" in crosscheck

    assert "decision_semiconductor_baseline_allocation_calibrated" in company_actual
    assert "_build_baseline_allocation_snapshot" in company_actual
    assert "load_opendart_provisional_earnings_decision_evidence" in company_actual
    assert "opendart_provisional_product_baseline_eligible" in company_actual

    assert "decision_semiconductor_product_revenue_calibrated" in allocation
    assert "_build_product_revenue_snapshot" in allocation
    assert "load_semiconductor_baseline_allocation_decision_evidence" in allocation

    assert "decision_semiconductor_accounting_identity_calibrated" in product_revenue
    assert "_build_accounting_identity_snapshot" in product_revenue
    assert "load_periodic_product_revenue_certification" in product_revenue
    assert "build_product_revenue_ir_crosscheck" in product_revenue
    assert "semiconductor_direct_product_revenue_non_scoring" in product_revenue

    assert "decision_semiconductor_baseline_reconciliation_calibrated" in accounting
    assert "_build_baseline_snapshot" in accounting
    assert "load_semiconductor_accounting_identity_decision_evidence" in accounting

    assert "decision_semiconductor_operating_assumption_calibrated" in baseline
    assert "_build_operating_assumption_snapshot" in baseline
    assert "load_semiconductor_baseline_reconciliation_decision_evidence" in baseline

    assert "decision_semiconductor_forward_input_calibrated" in assumptions
    assert "_build_forward_input_snapshot" in assumptions
    assert "load_semiconductor_operating_assumption_decision_evidence" in assumptions

    assert "decision_macro_liquidity_calibrated" in forward_input
    assert "_build_macro_liquidity_snapshot" in forward_input
    assert "load_semiconductor_forward_input_decision_evidence" in forward_input

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
