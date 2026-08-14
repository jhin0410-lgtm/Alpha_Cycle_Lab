from __future__ import annotations

import pandas as pd

from alpha_cycle.intelligence.decision_semiconductor_baseline_allocation_calibrated import (
    _attach,
    _defaults,
)
from alpha_cycle.intelligence.expectation_gap_decision_evidence import (
    build_expectation_gap_decision_evidence,
)


def _scorecard() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "semiconductor_baseline_reconciliation_certified": False,
                "semiconductor_assumption_baseline_reconciliation_certified": False,
                "semiconductor_assumption_all_scenario_assumptions_model_use_ready": True,
                "semiconductor_assumption_output_method_certified": True,
                "semiconductor_assumption_company_reconciliation_certified": True,
                "semiconductor_assumption_model_version_frozen": True,
                "kis_forward_evidence_available": False,
                "kis_estimate_snapshot_change_available": False,
            }
        ]
    )


def test_unavailable_allocation_is_explicit_and_does_not_touch_direct_baseline() -> None:
    original = _scorecard()
    result = _defaults(original)
    row = result.iloc[0]

    assert bool(row["semiconductor_baseline_reconciliation_certified"]) is False
    assert bool(row["semiconductor_assumption_baseline_reconciliation_certified"]) is False
    assert bool(row["semiconductor_baseline_allocation_available"]) is False
    assert bool(row["semiconductor_baseline_allocation_revenue_model_input_ready"]) is False
    assert bool(row["semiconductor_baseline_allocation_profitability_baseline_certified"]) is False
    assert bool(row["semiconductor_baseline_allocation_full_baseline_certified"]) is False
    assert bool(row["semiconductor_baseline_allocation_source_fact"]) is False
    assert bool(row["semiconductor_baseline_allocation_numeric_forecast_enabled"]) is False
    assert bool(row["semiconductor_baseline_allocation_decision_score_enabled"]) is False


def test_even_complete_three_block_derived_revenue_cannot_unlock_expectation_gap() -> None:
    attached = _attach(
        _scorecard(),
        evidence_id="a" * 64,
        required_block_count=3,
        allocated_block_count=3,
        missing_block_count=0,
        reconciliation_delta=0.0,
        revenue_reconciliation_certified=True,
        revenue_model_input_ready=True,
    )
    row = attached.iloc[0]

    assert bool(row["semiconductor_baseline_allocation_available"]) is True
    assert bool(row["semiconductor_baseline_allocation_revenue_reconciliation_certified"]) is True
    assert bool(row["semiconductor_baseline_allocation_revenue_model_input_ready"]) is True
    assert bool(row["semiconductor_baseline_allocation_profitability_baseline_certified"]) is False
    assert bool(row["semiconductor_baseline_allocation_full_baseline_certified"]) is False
    assert bool(row["semiconductor_baseline_allocation_source_fact"]) is False
    assert bool(row["semiconductor_baseline_reconciliation_certified"]) is False
    assert bool(row["semiconductor_assumption_baseline_reconciliation_certified"]) is False

    expectation = build_expectation_gap_decision_evidence(attached)
    expectation_row = expectation.rows.iloc[0]
    blockers = str(expectation_row["internal_forward_view_blockers_json"])

    assert expectation_row["internal_forward_view_status"] == (
        "operating_assumptions_ready_model_certification_pending"
    )
    assert "baseline_reconciliation_not_certified" in blockers
    assert expectation_row["expectation_gap_status"] == "blocked"
    assert bool(expectation_row["expectation_gap_enabled"]) is False
    assert bool(expectation_row["decision_score_enabled"]) is False
