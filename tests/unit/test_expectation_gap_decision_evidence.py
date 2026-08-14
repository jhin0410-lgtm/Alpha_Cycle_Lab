from __future__ import annotations

import json

import pandas as pd

from alpha_cycle.intelligence.expectation_gap_contract import (
    evaluate_expectation_readiness,
)
from alpha_cycle.intelligence.expectation_gap_decision_evidence import (
    append_expectation_gap_report,
    build_expectation_gap_decision_evidence,
    kis_expectation_semantics,
)


def _scorecards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "000660",
                "composite_score": 3.8,
                "valuation_score": pd.NA,
                "kis_forward_evidence_available": True,
                "kis_estimate_snapshot_change_available": True,
                "kis_estimate_snapshot_change_verified": False,
                "semiconductor_transmission_history_ready": True,
            },
            {
                "ticker": "005930",
                "composite_score": 3.6,
                "valuation_score": pd.NA,
                "kis_forward_evidence_available": True,
                "kis_estimate_snapshot_change_available": False,
                "kis_estimate_snapshot_change_verified": False,
                "semiconductor_transmission_history_ready": False,
            },
        ]
    )


def test_kis_adapter_preserves_existing_fail_closed_semantics() -> None:
    semantics = kis_expectation_semantics(
        raw_artifact_available=True,
        prior_snapshot_available=True,
    )
    readiness = evaluate_expectation_readiness(semantics)
    assert readiness.provider_id == "kis_estimate_perform_raw_unclassified"
    assert readiness.level_status == "blocked"
    assert readiness.revision_status == "blocked"
    assert readiness.numeric_level_enabled is False
    assert readiness.numeric_revision_enabled is False
    assert "provider_semantics_not_certified" in readiness.level_blockers
    assert "comparable_snapshot_scope_not_certified" in readiness.revision_blockers


def test_expectation_gap_requires_both_market_and_internal_forward_views() -> None:
    evidence = build_expectation_gap_decision_evidence(_scorecards())
    assert evidence.decision_score_enabled is False
    assert evidence.expectation_gap_enabled is False
    assert len(evidence.rows) == 2
    assert evidence.rows["expectation_level_status"].eq("blocked").all()
    assert evidence.rows["expectation_revision_status"].eq("blocked").all()
    assert evidence.rows["expectation_gap_status"].eq("blocked").all()
    assert evidence.rows["numeric_expectation_level_enabled"].eq(False).all()
    assert evidence.rows["numeric_expectation_revision_enabled"].eq(False).all()
    assert evidence.rows["expectation_gap_enabled"].eq(False).all()

    hynix = evidence.rows.loc[evidence.rows["ticker"].eq("000660")].iloc[0]
    samsung = evidence.rows.loc[evidence.rows["ticker"].eq("005930")].iloc[0]
    assert (
        hynix["internal_forward_view_status"]
        == "historical_transmission_only_not_forward_model"
    )
    assert samsung["internal_forward_view_status"] == "internal_forward_view_missing"
    blockers = json.loads(str(hynix["expectation_gap_blockers_json"]))
    assert "historical_transmission_not_a_forecast" in blockers
    assert "certified_market_expectation_level_required" in blockers

    report = append_expectation_gap_report("# Base\n", evidence)
    assert "Expectation Gap v1" in report
    assert "forward expectation의 '수준'과 'revision'" in report
    assert "numeric gap" in report


def test_complete_source_inputs_do_not_bypass_operating_assumption_and_baseline_gates() -> None:
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "kis_forward_evidence_available": True,
                "semiconductor_forward_all_numeric_inputs_covered": True,
                "semiconductor_forward_internal_forward_model_certified": False,
            }
        ]
    )
    row = build_expectation_gap_decision_evidence(scorecards).rows.iloc[0]
    assert (
        row["internal_forward_view_status"]
        == "numeric_source_inputs_complete_assumptions_and_bridges_pending"
    )
    blockers = json.loads(str(row["internal_forward_view_blockers_json"]))
    assert "operating_scenario_assumptions_missing" in blockers
    assert "baseline_reconciliation_not_certified" in blockers


def test_ready_operating_assumptions_still_require_baseline_and_model_certification() -> None:
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "kis_forward_evidence_available": True,
                "semiconductor_assumption_horizon_quarters": 4,
                "semiconductor_assumption_all_scenario_assumptions_documented": True,
                "semiconductor_assumption_all_scenario_assumptions_model_use_ready": True,
                "semiconductor_assumption_baseline_reconciliation_certified": False,
                "semiconductor_assumption_output_method_certified": False,
                "semiconductor_assumption_company_reconciliation_certified": False,
                "semiconductor_assumption_model_version_frozen": False,
                "semiconductor_assumption_internal_forward_model_certified": False,
            }
        ]
    )
    row = build_expectation_gap_decision_evidence(scorecards).rows.iloc[0]
    assert (
        row["internal_forward_view_status"]
        == "operating_assumptions_ready_model_certification_pending"
    )
    blockers = json.loads(str(row["internal_forward_view_blockers_json"]))
    assert "baseline_reconciliation_not_certified" in blockers
    assert "company_reconciliation_not_certified" in blockers
    assert bool(row["expectation_gap_enabled"]) is False


def test_verified_baseline_bridge_removes_only_the_baseline_blocker() -> None:
    scorecards = pd.DataFrame(
        [
            {
                "ticker": "005930",
                "kis_forward_evidence_available": True,
                "semiconductor_assumption_horizon_quarters": 4,
                "semiconductor_assumption_all_scenario_assumptions_documented": True,
                "semiconductor_assumption_all_scenario_assumptions_model_use_ready": True,
                "semiconductor_baseline_reconciliation_certified": True,
                "semiconductor_assumption_output_method_certified": False,
                "semiconductor_assumption_company_reconciliation_certified": False,
                "semiconductor_assumption_model_version_frozen": False,
                "semiconductor_assumption_internal_forward_model_certified": False,
            }
        ]
    )
    row = build_expectation_gap_decision_evidence(scorecards).rows.iloc[0]
    blockers = json.loads(str(row["internal_forward_view_blockers_json"]))
    assert "baseline_reconciliation_not_certified" not in blockers
    assert "output_method_not_certified" in blockers
    assert "company_reconciliation_not_certified" in blockers
    assert "model_version_not_frozen" in blockers
    assert bool(row["expectation_gap_enabled"]) is False
