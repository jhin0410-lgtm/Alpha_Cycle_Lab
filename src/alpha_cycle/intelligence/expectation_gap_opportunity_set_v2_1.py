"""Preregistered expectation-gap overlay for the Decision System v2.1 opportunity set.

The base opportunity set remains authoritative for payoff/catalyst comparison. This module may
add one consensus-relative-gap dimension only when a provider/metric/target frame was frozen
before the gap snapshots and every compared value is semantically aligned. Price-implied
references remain research evidence because their cross-security valuation frames are not
assumed comparable.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DecisionSystemV21Guardrails,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_view_v2_1 import DecisionExpectationGapSnapshot
from alpha_cycle.intelligence.expectation_state import ExpectationMetric
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    PARETO_DIMENSIONS,
    OpportunityCandidateSnapshot,
    OpportunitySetSnapshot,
)

EXPECTATION_GAP_OPPORTUNITY_SCHEMA_VERSION = 1
EXPECTATION_AUGMENTED_PARETO_DIMENSIONS = PARETO_DIMENSIONS + (
    "consensus_relative_gap",
)


class ExpectationGapComparisonStatistic(StrEnum):
    CONSENSUS_RELATIVE_GAP = "consensus_relative_gap"


@dataclass(frozen=True)
class ExpectationGapComparisonPolicySnapshot:
    """Cross-sectional comparison frame frozen before candidate gap snapshots exist."""

    policy_id: str
    registered_at: datetime
    evaluation_date: date
    consensus_provider_id: str
    metric: ExpectationMetric
    target_date: date
    statistic: ExpectationGapComparisonStatistic
    rationale: str
    source_evidence_ids: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "policy_id")
        _require_aware(self.registered_at, "registered_at")
        _require_text(self.consensus_provider_id, "consensus_provider_id")
        _require_text(self.rationale, "rationale")
        if self.registered_at.date() > self.evaluation_date:
            raise ValueError("expectation-gap policy cannot be registered after evaluation_date")
        if self.target_date <= self.evaluation_date:
            raise ValueError("expectation-gap policy target must remain forward")
        if self.statistic is not ExpectationGapComparisonStatistic.CONSENSUS_RELATIVE_GAP:
            raise ValueError("unsupported expectation-gap comparison statistic")
        _validate_sha_tuple(self.source_evidence_ids, "source_evidence_ids")
        if not self.source_evidence_ids:
            raise ValueError("expectation-gap comparison policy requires source evidence")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": EXPECTATION_GAP_OPPORTUNITY_SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "registered_at": self.registered_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "consensus_provider_id": self.consensus_provider_id,
            "metric": self.metric.value,
            "target_date": self.target_date.isoformat(),
            "statistic": self.statistic.value,
            "rationale": self.rationale,
            "source_evidence_ids": list(self.source_evidence_ids),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "provider_selected_after_gap_inspection": False,
            "metric_selected_after_gap_inspection": False,
            "target_selected_after_gap_inspection": False,
            "price_implied_cross_security_comparison_enabled": False,
            "weighted_composite_score_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class ExpectationGapOpportunityCandidateSnapshot:
    """One base opportunity candidate plus a policy-aligned consensus-gap value."""

    captured_at: datetime
    evaluation_date: date
    security_id: str
    opportunity_candidate_snapshot_id: str
    decision_expectation_gap_snapshot_id: str
    comparison_policy_snapshot_id: str
    consensus_provider_id: str
    metric: ExpectationMetric
    target_date: date
    consensus_relative_gap: float | None
    comparison_blockers: tuple[str, ...]
    flags: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _require_text(self.security_id, "security_id")
        _validate_sha(
            self.opportunity_candidate_snapshot_id,
            "opportunity_candidate_snapshot_id",
        )
        _validate_sha(
            self.decision_expectation_gap_snapshot_id,
            "decision_expectation_gap_snapshot_id",
        )
        _validate_sha(self.comparison_policy_snapshot_id, "comparison_policy_snapshot_id")
        _require_text(self.consensus_provider_id, "consensus_provider_id")
        if self.target_date <= self.evaluation_date:
            raise ValueError("expectation-gap candidate target must remain forward")
        if self.consensus_relative_gap is not None:
            _require_finite(self.consensus_relative_gap, "consensus_relative_gap")
        _validate_text_tuple(self.comparison_blockers, "comparison_blockers")
        _validate_text_tuple(self.flags, "flags")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        if self.expectation_gap_comparable and self.comparison_blockers:
            raise ValueError("comparable expectation-gap candidate cannot contain blockers")
        if not self.expectation_gap_comparable and not self.comparison_blockers:
            raise ValueError("non-comparable expectation-gap candidate requires a blocker")

    @property
    def expectation_gap_comparable(self) -> bool:
        return self.consensus_relative_gap is not None and not self.comparison_blockers

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": EXPECTATION_GAP_OPPORTUNITY_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "security_id": self.security_id,
            "opportunity_candidate_snapshot_id": self.opportunity_candidate_snapshot_id,
            "decision_expectation_gap_snapshot_id": (
                self.decision_expectation_gap_snapshot_id
            ),
            "comparison_policy_snapshot_id": self.comparison_policy_snapshot_id,
            "consensus_provider_id": self.consensus_provider_id,
            "metric": self.metric.value,
            "target_date": self.target_date.isoformat(),
            "consensus_relative_gap": self.consensus_relative_gap,
            "comparison_blockers": list(self.comparison_blockers),
            "flags": list(self.flags),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "expectation_gap_comparable": self.expectation_gap_comparable,
            "price_implied_gap_used_for_cross_security_ranking": False,
            "cost_basis_used_for_ranking": False,
            "weighted_composite_score_enabled": False,
            "target_price_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class ExpectationAugmentedDominanceRelation:
    dominator_security_id: str
    dominated_security_id: str
    strictly_better_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.dominator_security_id, "dominator_security_id")
        _require_text(self.dominated_security_id, "dominated_security_id")
        if self.dominator_security_id == self.dominated_security_id:
            raise ValueError("a security cannot dominate itself")
        _validate_text_tuple(self.strictly_better_dimensions, "strictly_better_dimensions")
        if not self.strictly_better_dimensions:
            raise ValueError("dominance relation requires a strict dimension")
        if not set(self.strictly_better_dimensions).issubset(
            EXPECTATION_AUGMENTED_PARETO_DIMENSIONS
        ):
            raise ValueError("expectation dominance relation contains unknown dimension")

    def payload(self) -> dict[str, object]:
        return {
            "dominator_security_id": self.dominator_security_id,
            "dominated_security_id": self.dominated_security_id,
            "strictly_better_dimensions": list(self.strictly_better_dimensions),
        }


@dataclass(frozen=True)
class ExpectationAugmentedOpportunitySetSnapshot:
    """Pareto overlay that preserves the base surface and adds one certified gap dimension."""

    captured_at: datetime
    evaluation_date: date
    horizon_trading_days: int
    base_opportunity_set_snapshot_id: str
    comparison_policy_snapshot_id: str
    candidates: tuple[ExpectationGapOpportunityCandidateSnapshot, ...]
    pareto_dimensions: tuple[str, ...]
    dominance_relations: tuple[ExpectationAugmentedDominanceRelation, ...]
    base_pareto_frontier_security_ids: tuple[str, ...]
    expectation_pareto_frontier_security_ids: tuple[str, ...]
    expectation_comparable_security_ids: tuple[str, ...]
    expectation_blocked_security_ids: tuple[str, ...]
    unique_expectation_pareto_leader_security_id: str | None
    flags: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _validate_sha(self.base_opportunity_set_snapshot_id, "base_opportunity_set_snapshot_id")
        _validate_sha(self.comparison_policy_snapshot_id, "comparison_policy_snapshot_id")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("expectation opportunity horizon must be 60, 120, or 250")
        if len(self.candidates) < 2:
            raise ValueError("expectation overlay requires at least two base candidates")
        if self.pareto_dimensions != EXPECTATION_AUGMENTED_PARETO_DIMENSIONS:
            raise ValueError("expectation-augmented Pareto dimensions have drifted")
        security_ids = tuple(item.security_id for item in self.candidates)
        if len(set(security_ids)) != len(security_ids):
            raise ValueError("expectation overlay requires unique securities")
        for candidate in self.candidates:
            if candidate.evaluation_date != self.evaluation_date:
                raise ValueError("expectation candidate evaluation_date mismatch")
            if candidate.guardrail_evidence_id != self.guardrail_evidence_id:
                raise ValueError("expectation candidate guardrail evidence mismatch")
            if candidate.captured_at > self.captured_at:
                raise ValueError("overlay capture cannot precede candidate capture")
        for values, field in (
            (self.base_pareto_frontier_security_ids, "base_pareto_frontier_security_ids"),
            (
                self.expectation_pareto_frontier_security_ids,
                "expectation_pareto_frontier_security_ids",
            ),
            (
                self.expectation_comparable_security_ids,
                "expectation_comparable_security_ids",
            ),
            (self.expectation_blocked_security_ids, "expectation_blocked_security_ids"),
        ):
            _validate_text_tuple(values, field)
            if not set(values).issubset(security_ids):
                raise ValueError(f"{field} must reference overlay candidates")
        if not set(self.expectation_pareto_frontier_security_ids).issubset(
            self.expectation_comparable_security_ids
        ):
            raise ValueError("expectation frontier must be a subset of comparable securities")
        _validate_text_tuple(self.flags, "flags")
        if self.unique_expectation_pareto_leader_security_id is not None:
            if self.unique_expectation_pareto_leader_security_id not in (
                self.expectation_pareto_frontier_security_ids
            ):
                raise ValueError("unique expectation leader must belong to the frontier")
            if len(self.expectation_comparable_security_ids) < 2:
                raise ValueError("unique expectation leader requires two comparable candidates")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        candidates = sorted(self.candidates, key=lambda item: item.security_id)
        relations = sorted(
            self.dominance_relations,
            key=lambda item: (item.dominator_security_id, item.dominated_security_id),
        )
        return {
            "schema_version": EXPECTATION_GAP_OPPORTUNITY_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "base_opportunity_set_snapshot_id": self.base_opportunity_set_snapshot_id,
            "comparison_policy_snapshot_id": self.comparison_policy_snapshot_id,
            "pareto_dimensions": list(self.pareto_dimensions),
            "candidates": [item.payload_without_id() for item in candidates],
            "dominance_relations": [item.payload() for item in relations],
            "base_pareto_frontier_security_ids": list(
                self.base_pareto_frontier_security_ids
            ),
            "expectation_pareto_frontier_security_ids": list(
                self.expectation_pareto_frontier_security_ids
            ),
            "expectation_comparable_security_ids": list(
                self.expectation_comparable_security_ids
            ),
            "expectation_blocked_security_ids": list(
                self.expectation_blocked_security_ids
            ),
            "unique_expectation_pareto_leader_security_id": (
                self.unique_expectation_pareto_leader_security_id
            ),
            "flags": list(self.flags),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "base_opportunity_set_replaced": False,
            "price_implied_gap_used_for_cross_security_ranking": False,
            "provider_aggregation_enabled": False,
            "weighted_composite_score_enabled": False,
            "capital_allocation_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


def build_expectation_gap_comparison_policy(
    *,
    policy_id: str,
    registered_at: datetime,
    evaluation_date: date,
    consensus_provider_id: str,
    metric: ExpectationMetric,
    target_date: date,
    rationale: str,
    source_evidence_ids: tuple[str, ...],
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> ExpectationGapComparisonPolicySnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    return ExpectationGapComparisonPolicySnapshot(
        policy_id=policy_id,
        registered_at=registered_at,
        evaluation_date=evaluation_date,
        consensus_provider_id=consensus_provider_id,
        metric=metric,
        target_date=target_date,
        statistic=ExpectationGapComparisonStatistic.CONSENSUS_RELATIVE_GAP,
        rationale=rationale,
        source_evidence_ids=source_evidence_ids,
        guardrail_evidence_id=active.evidence_id,
    )


def build_expectation_gap_opportunity_candidate(
    opportunity: OpportunityCandidateSnapshot,
    gap: DecisionExpectationGapSnapshot,
    policy: ExpectationGapComparisonPolicySnapshot,
    *,
    captured_at: datetime,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> ExpectationGapOpportunityCandidateSnapshot:
    """Attach a policy-aligned provider gap without pretending all gaps are comparable."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if opportunity.guardrail_evidence_id != active.evidence_id:
        raise ValueError("opportunity candidate guardrail evidence mismatch")
    if gap.guardrail_evidence_id != active.evidence_id:
        raise ValueError("Decision expectation gap guardrail evidence mismatch")
    if policy.guardrail_evidence_id != active.evidence_id:
        raise ValueError("expectation comparison policy guardrail evidence mismatch")
    if opportunity.security_id != gap.security_id:
        raise ValueError("opportunity and expectation gap securities differ")
    if opportunity.evaluation_date != gap.evaluation_date:
        raise ValueError("opportunity and expectation gap evaluation dates differ")
    if policy.evaluation_date != gap.evaluation_date:
        raise ValueError("comparison policy evaluation_date differs from gap")
    if opportunity.captured_at > captured_at or gap.captured_at > captured_at:
        raise ValueError("expectation opportunity capture cannot precede source snapshots")
    if policy.registered_at >= gap.captured_at:
        raise ValueError("comparison policy must be registered before gap values are frozen")

    blockers: list[str] = []
    if not opportunity.capital_allocation_comparable:
        blockers.append("base_opportunity_not_capital_allocation_comparable")
    if gap.target_variable != policy.metric.value:
        blockers.append("expectation_metric_not_policy_comparable")
    if gap.target_date != policy.target_date:
        blockers.append("expectation_target_date_not_policy_comparable")

    matching = tuple(
        item
        for item in gap.consensus_gaps
        if item.provider_id == policy.consensus_provider_id
    )
    relative_gap: float | None = None
    if len(matching) != 1:
        blockers.append("policy_consensus_provider_gap_unavailable")
    elif matching[0].relative_gap is None:
        blockers.append("consensus_relative_gap_unavailable")
    elif not blockers:
        relative_gap = matching[0].relative_gap

    flags = list(gap.flags)
    if gap.price_implied_gaps:
        flags.append("price_implied_gaps_preserved_as_nonranking_evidence")

    return ExpectationGapOpportunityCandidateSnapshot(
        captured_at=captured_at,
        evaluation_date=gap.evaluation_date,
        security_id=gap.security_id,
        opportunity_candidate_snapshot_id=opportunity.snapshot_id,
        decision_expectation_gap_snapshot_id=gap.snapshot_id,
        comparison_policy_snapshot_id=policy.snapshot_id,
        consensus_provider_id=policy.consensus_provider_id,
        metric=policy.metric,
        target_date=policy.target_date,
        consensus_relative_gap=relative_gap,
        comparison_blockers=tuple(dict.fromkeys(blockers)),
        flags=tuple(dict.fromkeys(flags)),
        guardrail_evidence_id=active.evidence_id,
    )


def build_expectation_augmented_opportunity_set(
    base: OpportunitySetSnapshot,
    policy: ExpectationGapComparisonPolicySnapshot,
    candidates: tuple[ExpectationGapOpportunityCandidateSnapshot, ...],
    *,
    captured_at: datetime,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> ExpectationAugmentedOpportunitySetSnapshot:
    """Add one preregistered consensus-gap dimension to the existing Pareto surface."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if base.guardrail_evidence_id != active.evidence_id:
        raise ValueError("base opportunity-set guardrail evidence mismatch")
    if policy.guardrail_evidence_id != active.evidence_id:
        raise ValueError("expectation comparison policy guardrail evidence mismatch")
    if base.evaluation_date != policy.evaluation_date:
        raise ValueError("base opportunity set and expectation policy evaluation_date differ")
    if base.captured_at > captured_at:
        raise ValueError("expectation overlay cannot precede base opportunity set")
    if len(candidates) < 2:
        raise ValueError("expectation overlay requires at least two candidates")

    by_security = {item.security_id: item for item in candidates}
    if len(by_security) != len(candidates):
        raise ValueError("expectation overlay candidates require unique security ids")
    required_ids = set(base.comparable_security_ids)
    if set(by_security) != required_ids:
        raise ValueError(
            "expectation overlay must represent every and only base-comparable security"
        )
    for candidate in candidates:
        if candidate.comparison_policy_snapshot_id != policy.snapshot_id:
            raise ValueError("expectation candidate comparison policy mismatch")
        if candidate.evaluation_date != base.evaluation_date:
            raise ValueError("expectation candidate evaluation_date mismatch")
        if candidate.guardrail_evidence_id != active.evidence_id:
            raise ValueError("expectation candidate guardrail evidence mismatch")
        if candidate.captured_at > captured_at:
            raise ValueError("expectation overlay cannot precede candidate capture")
        original = _base_candidate(base, candidate.security_id)
        if candidate.opportunity_candidate_snapshot_id != original.snapshot_id:
            raise ValueError("expectation candidate is bound to a different base candidate")

    comparable = tuple(item for item in candidates if item.expectation_gap_comparable)
    relations: list[ExpectationAugmentedDominanceRelation] = []
    for dominator in comparable:
        for dominated in comparable:
            if dominator.security_id == dominated.security_id:
                continue
            strict = _strictly_better_dimensions(
                _base_candidate(base, dominator.security_id),
                dominator,
                _base_candidate(base, dominated.security_id),
                dominated,
            )
            if strict is not None:
                relations.append(
                    ExpectationAugmentedDominanceRelation(
                        dominator_security_id=dominator.security_id,
                        dominated_security_id=dominated.security_id,
                        strictly_better_dimensions=strict,
                    )
                )

    dominated_ids = {item.dominated_security_id for item in relations}
    frontier = tuple(
        sorted(
            item.security_id
            for item in comparable
            if item.security_id not in dominated_ids
        )
    )
    comparable_ids = tuple(sorted(item.security_id for item in comparable))
    blocked_ids = tuple(
        sorted(item.security_id for item in candidates if not item.expectation_gap_comparable)
    )

    unique_leader: str | None = None
    if len(comparable) >= 2:
        for candidate in comparable:
            dominated_by_candidate = {
                relation.dominated_security_id
                for relation in relations
                if relation.dominator_security_id == candidate.security_id
            }
            others = {item.security_id for item in comparable} - {candidate.security_id}
            if dominated_by_candidate == others:
                unique_leader = candidate.security_id
                break

    flags: list[str] = []
    if len(comparable) < 2:
        flags.append("insufficient_expectation_comparable_candidates")
    if blocked_ids:
        flags.append("partial_expectation_gap_comparability")
    if len(frontier) > 1:
        flags.append("multiple_expectation_augmented_non_dominated_opportunities")
    if tuple(sorted(base.pareto_frontier_security_ids)) != frontier:
        flags.append("expectation_gap_changes_pareto_frontier")

    return ExpectationAugmentedOpportunitySetSnapshot(
        captured_at=captured_at,
        evaluation_date=base.evaluation_date,
        horizon_trading_days=base.horizon_trading_days,
        base_opportunity_set_snapshot_id=base.snapshot_id,
        comparison_policy_snapshot_id=policy.snapshot_id,
        candidates=candidates,
        pareto_dimensions=EXPECTATION_AUGMENTED_PARETO_DIMENSIONS,
        dominance_relations=tuple(relations),
        base_pareto_frontier_security_ids=tuple(
            sorted(base.pareto_frontier_security_ids)
        ),
        expectation_pareto_frontier_security_ids=frontier,
        expectation_comparable_security_ids=comparable_ids,
        expectation_blocked_security_ids=blocked_ids,
        unique_expectation_pareto_leader_security_id=unique_leader,
        flags=tuple(flags),
        guardrail_evidence_id=active.evidence_id,
    )


def persist_expectation_gap_comparison_policy(
    snapshot: ExpectationGapComparisonPolicySnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        "expectation_gap_comparison_policy",
        snapshot.snapshot_id,
        snapshot.registered_at,
        snapshot.payload_without_id(),
        output_root,
    )


def persist_expectation_gap_opportunity_candidate(
    snapshot: ExpectationGapOpportunityCandidateSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        "expectation_gap_opportunity_candidate",
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
    )


def persist_expectation_augmented_opportunity_set(
    snapshot: ExpectationAugmentedOpportunitySetSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        "expectation_augmented_opportunity_set",
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
    )


def _strictly_better_dimensions(
    left_base: OpportunityCandidateSnapshot,
    left_gap: ExpectationGapOpportunityCandidateSnapshot,
    right_base: OpportunityCandidateSnapshot,
    right_gap: ExpectationGapOpportunityCandidateSnapshot,
) -> tuple[str, ...] | None:
    if left_gap.consensus_relative_gap is None or right_gap.consensus_relative_gap is None:
        return None
    if left_base.nearest_catalyst_days is None or right_base.nearest_catalyst_days is None:
        return None
    higher_better = (
        ("bear_return_lower", left_base.bear_return_lower, right_base.bear_return_lower),
        ("base_return_lower", left_base.base_return_lower, right_base.base_return_lower),
        ("base_return_upper", left_base.base_return_upper, right_base.base_return_upper),
        ("bull_return_upper", left_base.bull_return_upper, right_base.bull_return_upper),
        (
            "consensus_relative_gap",
            left_gap.consensus_relative_gap,
            right_gap.consensus_relative_gap,
        ),
    )
    if any(left < right for _, left, right in higher_better):
        return None
    if left_base.nearest_catalyst_days > right_base.nearest_catalyst_days:
        return None
    strict = [name for name, left, right in higher_better if left > right]
    if left_base.nearest_catalyst_days < right_base.nearest_catalyst_days:
        strict.append("nearest_catalyst_days")
    return tuple(strict) if strict else None


def _base_candidate(
    base: OpportunitySetSnapshot,
    security_id: str,
) -> OpportunityCandidateSnapshot:
    matches = tuple(item for item in base.candidates if item.security_id == security_id)
    if len(matches) != 1:
        raise ValueError("base opportunity set must contain exactly one security candidate")
    return matches[0]


def _persist(
    object_name: str,
    snapshot_id: str,
    captured_at: datetime,
    payload: dict[str, object],
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / object_name
    root.mkdir(parents=True, exist_ok=True)
    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot_id[:12]}"
    pointer = root / f"latest_{object_name}.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot_id:
            raise ValueError(f"existing {object_name} directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            manifest = {
                "schema_version": EXPECTATION_GAP_OPPORTUNITY_SCHEMA_VERSION,
                "object_type": object_name,
                "snapshot_id": snapshot_id,
                "captured_at": captured_at.isoformat(),
                "immutable": True,
                "files": [f"{object_name}.json"],
                "weighted_composite_score_enabled": False,
                "target_price_enabled": False,
                "capital_allocation_recommendation_enabled": False,
                "automatic_execution_enabled": False,
            }
            (temporary / f"{object_name}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.rename(directory)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
    pointer.write_text(
        json.dumps(
            {
                "schema_version": EXPECTATION_GAP_OPPORTUNITY_SCHEMA_VERSION,
                "object_type": object_name,
                "snapshot_id": snapshot_id,
                "snapshot_path": str(directory),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pointer


def _require_finite(value: float, field: str) -> None:
    if not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _validate_sha(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): value for key, value in payload.items()}


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "EXPECTATION_AUGMENTED_PARETO_DIMENSIONS",
    "ExpectationAugmentedDominanceRelation",
    "ExpectationAugmentedOpportunitySetSnapshot",
    "ExpectationGapComparisonPolicySnapshot",
    "ExpectationGapComparisonStatistic",
    "ExpectationGapOpportunityCandidateSnapshot",
    "build_expectation_augmented_opportunity_set",
    "build_expectation_gap_comparison_policy",
    "build_expectation_gap_opportunity_candidate",
    "persist_expectation_augmented_opportunity_set",
    "persist_expectation_gap_comparison_policy",
    "persist_expectation_gap_opportunity_candidate",
]
