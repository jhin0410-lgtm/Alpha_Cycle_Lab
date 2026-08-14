from __future__ import annotations

from alpha_cycle.intelligence.expectation_gap_contract import (
    ExpectationSemantics,
    evaluate_expectation_readiness,
)


def test_expectation_level_and_revision_are_certified_separately() -> None:
    semantics = ExpectationSemantics(
        provider_id="certified_provider",
        provider_semantics_certified=True,
        target_period_semantics_certified=True,
        metric_semantics_certified=True,
        aggregation_semantics_certified=True,
        observation_timestamp_certified=True,
        provider_vintage_certified=False,
        comparable_prior_snapshot_available=False,
        comparable_snapshot_scope_certified=False,
        revision_calculation_certified=False,
        numeric_evidence_available=True,
        source_scope="test certified level only",
    )
    readiness = evaluate_expectation_readiness(semantics)
    assert readiness.level_status == "available"
    assert readiness.numeric_level_enabled is True
    assert readiness.revision_status == "blocked"
    assert readiness.numeric_revision_enabled is False
    assert "provider_vintage_not_certified" in readiness.revision_blockers
    assert "comparable_prior_snapshot_missing" in readiness.revision_blockers
    assert readiness.expectation_gap_enabled is False
    assert readiness.decision_score_enabled is False


def test_fully_certified_provider_can_enable_level_and_revision_but_not_gap_by_itself() -> None:
    semantics = ExpectationSemantics(
        provider_id="certified_provider",
        provider_semantics_certified=True,
        target_period_semantics_certified=True,
        metric_semantics_certified=True,
        aggregation_semantics_certified=True,
        observation_timestamp_certified=True,
        provider_vintage_certified=True,
        comparable_prior_snapshot_available=True,
        comparable_snapshot_scope_certified=True,
        revision_calculation_certified=True,
        numeric_evidence_available=True,
        source_scope="fully certified expectation snapshots",
    )
    readiness = evaluate_expectation_readiness(semantics)
    assert readiness.level_status == "available"
    assert readiness.revision_status == "available"
    assert readiness.numeric_level_enabled is True
    assert readiness.numeric_revision_enabled is True
    assert readiness.expectation_gap_enabled is False


def test_uncertified_provider_blocks_numeric_forward_evidence() -> None:
    semantics = ExpectationSemantics(
        provider_id="raw_unknown",
        provider_semantics_certified=False,
        target_period_semantics_certified=False,
        metric_semantics_certified=False,
        aggregation_semantics_certified=False,
        observation_timestamp_certified=True,
        provider_vintage_certified=False,
        comparable_prior_snapshot_available=True,
        comparable_snapshot_scope_certified=False,
        revision_calculation_certified=False,
        numeric_evidence_available=False,
        source_scope="raw structure only",
    )
    readiness = evaluate_expectation_readiness(semantics)
    assert readiness.level_status == "blocked"
    assert readiness.revision_status == "blocked"
    assert readiness.numeric_level_enabled is False
    assert readiness.numeric_revision_enabled is False
    assert "provider_semantics_not_certified" in readiness.level_blockers
    assert "target_period_semantics_not_certified" in readiness.level_blockers
    assert "numeric_forward_evidence_unavailable" in readiness.level_blockers
