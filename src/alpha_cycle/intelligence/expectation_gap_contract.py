"""Provider-agnostic forward expectation/revision trust contract.

Expectation *levels* and expectation *revisions* are different capabilities.
A provider can expose forward-looking rows without those rows being safe to call
consensus, without their target periods being known, and without two snapshots
being comparable enough to call the difference a revision.  Alpha Cycle therefore
certifies each capability separately and fails closed when semantics are missing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpectationSemantics:
    provider_id: str
    provider_semantics_certified: bool
    target_period_semantics_certified: bool
    metric_semantics_certified: bool
    aggregation_semantics_certified: bool
    observation_timestamp_certified: bool
    provider_vintage_certified: bool
    comparable_prior_snapshot_available: bool
    comparable_snapshot_scope_certified: bool
    revision_calculation_certified: bool
    numeric_evidence_available: bool
    source_scope: str

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.source_scope.strip():
            raise ValueError("Expectation provider_id/source_scope cannot be blank")


@dataclass(frozen=True)
class ExpectationReadiness:
    provider_id: str
    level_status: str
    revision_status: str
    level_blockers: tuple[str, ...]
    revision_blockers: tuple[str, ...]
    numeric_level_enabled: bool
    numeric_revision_enabled: bool
    expectation_gap_enabled: bool
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        allowed = {"available", "blocked", "missing"}
        if self.level_status not in allowed or self.revision_status not in allowed:
            raise ValueError("Expectation readiness status is invalid")
        if self.numeric_level_enabled and self.level_status != "available":
            raise ValueError("Numeric expectation level requires available readiness")
        if self.numeric_revision_enabled and self.revision_status != "available":
            raise ValueError("Numeric expectation revision requires available readiness")
        if self.expectation_gap_enabled:
            raise ValueError(
                "Expectation gap requires an independently certified internal forward operating view"
            )
        if self.decision_score_enabled:
            raise ValueError("Expectation readiness must remain non-scoring")


def evaluate_expectation_readiness(
    semantics: ExpectationSemantics,
) -> ExpectationReadiness:
    """Certify level and revision capability independently."""

    level_requirements = {
        "provider_semantics_not_certified": semantics.provider_semantics_certified,
        "target_period_semantics_not_certified": semantics.target_period_semantics_certified,
        "metric_semantics_not_certified": semantics.metric_semantics_certified,
        "aggregation_semantics_not_certified": semantics.aggregation_semantics_certified,
        "observation_timestamp_not_certified": semantics.observation_timestamp_certified,
        "numeric_forward_evidence_unavailable": semantics.numeric_evidence_available,
    }
    level_blockers = tuple(
        blocker for blocker, satisfied in level_requirements.items() if not satisfied
    )
    level_status = "available" if not level_blockers else "blocked"

    revision_requirements = {
        **level_requirements,
        "provider_vintage_not_certified": semantics.provider_vintage_certified,
        "comparable_prior_snapshot_missing": semantics.comparable_prior_snapshot_available,
        "comparable_snapshot_scope_not_certified": semantics.comparable_snapshot_scope_certified,
        "revision_calculation_not_certified": semantics.revision_calculation_certified,
    }
    revision_blockers = tuple(
        blocker for blocker, satisfied in revision_requirements.items() if not satisfied
    )
    revision_status = "available" if not revision_blockers else "blocked"

    return ExpectationReadiness(
        provider_id=semantics.provider_id,
        level_status=level_status,
        revision_status=revision_status,
        level_blockers=level_blockers,
        revision_blockers=revision_blockers,
        numeric_level_enabled=level_status == "available",
        numeric_revision_enabled=revision_status == "available",
        expectation_gap_enabled=False,
        decision_score_enabled=False,
    )


__all__ = [
    "ExpectationReadiness",
    "ExpectationSemantics",
    "evaluate_expectation_readiness",
]
