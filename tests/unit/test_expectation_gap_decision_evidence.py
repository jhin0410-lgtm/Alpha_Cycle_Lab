from __future__ import annotations

import json

import pandas as pd

from alpha_cycle.intelligence.expectation_gap_contract import evaluate_expectation_readiness
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
