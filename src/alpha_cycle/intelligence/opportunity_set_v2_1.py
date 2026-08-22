"""Cross-sectional opportunity-set comparison for Alpha Cycle Lab Decision System v2.1.

This module compares research-ready securities at the same evaluation date and investment
horizon. It deliberately avoids a weighted composite score, probability-weighted expected
return, current cost basis, target price, optimal portfolio weights, and automatic execution.
The first comparison surface is a transparent Pareto frontier over payoff and catalyst timing.
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
from typing import cast

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DecisionSystemV21Guardrails,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot
from alpha_cycle.intelligence.payoff_surface import PayoffSurfaceSnapshot, ScenarioLabel
from alpha_cycle.intelligence.underwriter_v2_1 import (
    UnderwritingReadiness,
    UnderwritingReadinessSnapshot,
)

OPPORTUNITY_SET_SCHEMA_VERSION = 1
PARETO_DIMENSIONS = (
    "bear_return_lower",
    "base_return_lower",
    "base_return_upper",
    "bull_return_upper",
    "nearest_catalyst_days",
)


class OpportunityResearchClass(StrEnum):
    DEEP_READY = "deep_ready"
    DEEP_FLAGGED = "deep_flagged"
    FAST_READY = "fast_ready"
    RESEARCH_BLOCKED = "research_blocked"


@dataclass(frozen=True)
class OpportunityCandidateSnapshot:
    """One candidate's comparable payoff/timing vector without portfolio-history bias."""

    captured_at: datetime
    evaluation_date: date
    security_id: str
    thesis_snapshot_id: str
    underwriting_readiness_snapshot_id: str
    payoff_surface_snapshot_id: str
    horizon_trading_days: int
    research_class: OpportunityResearchClass
    bear_return_lower: float
    base_return_lower: float
    base_return_upper: float
    bull_return_upper: float
    nearest_catalyst_id: str | None
    nearest_catalyst_days: int | None
    nearest_catalyst_evidence_refs: tuple[str, ...]
    comparison_blockers: tuple[str, ...]
    flags: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _require_text(self.security_id, "security_id")
        _validate_sha(self.thesis_snapshot_id, "thesis_snapshot_id")
        _validate_sha(
            self.underwriting_readiness_snapshot_id,
            "underwriting_readiness_snapshot_id",
        )
        _validate_sha(self.payoff_surface_snapshot_id, "payoff_surface_snapshot_id")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("opportunity horizon must be 60, 120, or 250 trading days")
        for value, field in (
            (self.bear_return_lower, "bear_return_lower"),
            (self.base_return_lower, "base_return_lower"),
            (self.base_return_upper, "base_return_upper"),
            (self.bull_return_upper, "bull_return_upper"),
        ):
            _require_finite(value, field)
        if self.nearest_catalyst_id is None:
            if self.nearest_catalyst_days is not None:
                raise ValueError("nearest_catalyst_days requires nearest_catalyst_id")
            if self.nearest_catalyst_evidence_refs:
                raise ValueError("catalyst evidence requires nearest_catalyst_id")
        else:
            _require_text(self.nearest_catalyst_id, "nearest_catalyst_id")
            if self.nearest_catalyst_days is None:
                raise ValueError("nearest_catalyst_id requires nearest_catalyst_days")
            if self.nearest_catalyst_days < 0:
                raise ValueError("nearest_catalyst_days cannot be negative")
            if not self.nearest_catalyst_evidence_refs:
                raise ValueError("dated catalyst requires evidence references")
        _validate_text_tuple(
            self.nearest_catalyst_evidence_refs,
            "nearest_catalyst_evidence_refs",
        )
        _validate_text_tuple(self.comparison_blockers, "comparison_blockers")
        _validate_text_tuple(self.flags, "flags")
        if self.capital_allocation_comparable and self.comparison_blockers:
            raise ValueError("comparable opportunity candidate cannot contain blockers")

    @property
    def capital_allocation_comparable(self) -> bool:
        deep = self.research_class in {
            OpportunityResearchClass.DEEP_READY,
            OpportunityResearchClass.DEEP_FLAGGED,
        }
        return deep and self.nearest_catalyst_days is not None and not self.comparison_blockers

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "security_id": self.security_id,
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "underwriting_readiness_snapshot_id": self.underwriting_readiness_snapshot_id,
            "payoff_surface_snapshot_id": self.payoff_surface_snapshot_id,
            "horizon_trading_days": self.horizon_trading_days,
            "research_class": self.research_class.value,
            "bear_return_lower": self.bear_return_lower,
            "base_return_lower": self.base_return_lower,
            "base_return_upper": self.base_return_upper,
            "bull_return_upper": self.bull_return_upper,
            "nearest_catalyst_id": self.nearest_catalyst_id,
            "nearest_catalyst_days": self.nearest_catalyst_days,
            "nearest_catalyst_evidence_refs": list(self.nearest_catalyst_evidence_refs),
            "comparison_blockers": list(self.comparison_blockers),
            "flags": list(self.flags),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "capital_allocation_comparable": self.capital_allocation_comparable,
            "current_cost_basis_considered": False,
            "unrealized_pnl_considered": False,
            "composite_score_enabled": False,
            "probability_weighted_expected_return_enabled": False,
            "target_price_enabled": False,
            "optimal_position_size_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class DominanceRelation:
    dominator_security_id: str
    dominated_security_id: str
    strictly_better_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.dominator_security_id, "dominator_security_id")
        _require_text(self.dominated_security_id, "dominated_security_id")
        if self.dominator_security_id == self.dominated_security_id:
            raise ValueError("a security cannot Pareto-dominate itself")
        _validate_text_tuple(self.strictly_better_dimensions, "strictly_better_dimensions")
        if not self.strictly_better_dimensions:
            raise ValueError("dominance relation requires at least one strict dimension")
        if not set(self.strictly_better_dimensions).issubset(PARETO_DIMENSIONS):
            raise ValueError("dominance relation contains an unknown comparison dimension")

    def payload(self) -> dict[str, object]:
        return {
            "dominator_security_id": self.dominator_security_id,
            "dominated_security_id": self.dominated_security_id,
            "strictly_better_dimensions": list(self.strictly_better_dimensions),
        }


@dataclass(frozen=True)
class OpportunitySetSnapshot:
    """Immutable same-date/same-horizon Pareto opportunity set."""

    captured_at: datetime
    evaluation_date: date
    horizon_trading_days: int
    candidates: tuple[OpportunityCandidateSnapshot, ...]
    pareto_dimensions: tuple[str, ...]
    dominance_relations: tuple[DominanceRelation, ...]
    pareto_frontier_security_ids: tuple[str, ...]
    comparable_security_ids: tuple[str, ...]
    fast_lane_research_security_ids: tuple[str, ...]
    blocked_security_ids: tuple[str, ...]
    epistemically_flagged_security_ids: tuple[str, ...]
    unique_pareto_leader_security_id: str | None
    flags: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("opportunity-set horizon must be 60, 120, or 250 trading days")
        if len(self.candidates) < 2:
            raise ValueError("cross-sectional opportunity set requires at least two candidates")
        if self.pareto_dimensions != PARETO_DIMENSIONS:
            raise ValueError("opportunity-set Pareto dimensions have drifted")
        security_ids = tuple(item.security_id for item in self.candidates)
        if len(set(security_ids)) != len(security_ids):
            raise ValueError("opportunity set requires unique security ids")
        snapshot_ids = tuple(item.snapshot_id for item in self.candidates)
        if len(set(snapshot_ids)) != len(snapshot_ids):
            raise ValueError("opportunity set contains duplicate candidate snapshots")
        for candidate in self.candidates:
            if candidate.evaluation_date != self.evaluation_date:
                raise ValueError("all opportunity candidates must share evaluation_date")
            if candidate.horizon_trading_days != self.horizon_trading_days:
                raise ValueError("all opportunity candidates must share horizon")
            if candidate.guardrail_evidence_id != self.guardrail_evidence_id:
                raise ValueError("opportunity candidate guardrail evidence mismatch")
            if candidate.captured_at > self.captured_at:
                raise ValueError("opportunity-set capture cannot precede candidate capture")
        for values, field in (
            (self.pareto_frontier_security_ids, "pareto_frontier_security_ids"),
            (self.comparable_security_ids, "comparable_security_ids"),
            (self.fast_lane_research_security_ids, "fast_lane_research_security_ids"),
            (self.blocked_security_ids, "blocked_security_ids"),
            (
                self.epistemically_flagged_security_ids,
                "epistemically_flagged_security_ids",
            ),
        ):
            _validate_text_tuple(values, field)
            if not set(values).issubset(security_ids):
                raise ValueError(f"{field} must reference opportunity-set candidates")
        _validate_text_tuple(self.flags, "flags")
        if not set(self.pareto_frontier_security_ids).issubset(
            self.comparable_security_ids
        ):
            raise ValueError("Pareto frontier must be a subset of comparable securities")
        for relation in self.dominance_relations:
            if relation.dominator_security_id not in self.comparable_security_ids:
                raise ValueError("dominance relation dominator must be comparable")
            if relation.dominated_security_id not in self.comparable_security_ids:
                raise ValueError("dominance relation target must be comparable")
        if self.unique_pareto_leader_security_id is not None:
            if self.unique_pareto_leader_security_id not in self.pareto_frontier_security_ids:
                raise ValueError("unique Pareto leader must belong to the frontier")
            if len(self.comparable_security_ids) < 2:
                raise ValueError("unique Pareto leader requires at least two comparable candidates")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        ordered_candidates = sorted(self.candidates, key=lambda item: item.security_id)
        ordered_relations = sorted(
            self.dominance_relations,
            key=lambda item: (item.dominator_security_id, item.dominated_security_id),
        )
        return {
            "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "pareto_dimensions": list(self.pareto_dimensions),
            "candidates": [item.payload_without_id() for item in ordered_candidates],
            "dominance_relations": [item.payload() for item in ordered_relations],
            "pareto_frontier_security_ids": list(self.pareto_frontier_security_ids),
            "comparable_security_ids": list(self.comparable_security_ids),
            "fast_lane_research_security_ids": list(self.fast_lane_research_security_ids),
            "blocked_security_ids": list(self.blocked_security_ids),
            "epistemically_flagged_security_ids": list(
                self.epistemically_flagged_security_ids
            ),
            "unique_pareto_leader_security_id": self.unique_pareto_leader_security_id,
            "flags": list(self.flags),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "ranking_score_enabled": False,
            "weighted_composite_score_enabled": False,
            "probability_weighted_expected_return_enabled": False,
            "cost_basis_used_for_ranking": False,
            "target_price_enabled": False,
            "optimal_portfolio_weights_enabled": False,
            "capital_allocation_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


def build_opportunity_candidate(
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    payoff: PayoffSurfaceSnapshot,
    *,
    captured_at: datetime,
    evaluation_date: date,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> OpportunityCandidateSnapshot:
    """Build one candidate vector without using the investor's cost basis or P&L."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if underwriting.thesis_snapshot_id != thesis.snapshot_id:
        raise ValueError("underwriting snapshot is bound to a different thesis")
    if underwriting.security_id != thesis.security_id:
        raise ValueError("underwriting security differs from thesis")
    if underwriting.evaluation_date != evaluation_date:
        raise ValueError("underwriting evaluation_date differs from opportunity candidate")
    if underwriting.guardrail_evidence_id != active.evidence_id:
        raise ValueError("underwriting guardrail evidence mismatch")
    if underwriting.captured_at > captured_at:
        raise ValueError("opportunity candidate cannot precede underwriting readiness")
    if payoff.thesis_snapshot_id != thesis.snapshot_id:
        raise ValueError("payoff surface is bound to a different thesis")
    if payoff.security_id != thesis.security_id:
        raise ValueError("payoff surface security differs from thesis")
    if payoff.horizon_trading_days != thesis.horizon_trading_days:
        raise ValueError("payoff surface horizon differs from thesis")
    if payoff.guardrail_evidence_id != active.evidence_id:
        raise ValueError("payoff surface guardrail evidence mismatch")
    if payoff.captured_at > captured_at:
        raise ValueError("opportunity candidate cannot precede payoff surface")
    if underwriting.payoff_surface_snapshot_id not in {None, payoff.snapshot_id}:
        raise ValueError("underwriting snapshot references a different payoff surface")

    scenario_by_label = {item.label: item for item in payoff.scenarios}
    bear = scenario_by_label[ScenarioLabel.BEAR]
    base = scenario_by_label[ScenarioLabel.BASE]
    bull = scenario_by_label[ScenarioLabel.BULL]
    research_class = _research_class(underwriting.readiness)
    catalyst_id, catalyst_days, catalyst_evidence, catalyst_flags = _nearest_catalyst(
        thesis,
        evaluation_date=evaluation_date,
    )

    blockers: list[str] = []
    if research_class not in {
        OpportunityResearchClass.DEEP_READY,
        OpportunityResearchClass.DEEP_FLAGGED,
    }:
        blockers.append("underwriter_not_deep_ready")
    if catalyst_days is None:
        blockers.append("dated_catalyst_timing_unavailable")

    flags = list(underwriting.flags)
    flags.extend(catalyst_flags)
    if research_class is OpportunityResearchClass.DEEP_FLAGGED:
        flags.append("deep_underwriting_epistemic_flags_present")
    flags.extend(f"payoff_warning:{warning}" for warning in payoff.warnings)

    return OpportunityCandidateSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        security_id=thesis.security_id,
        thesis_snapshot_id=thesis.snapshot_id,
        underwriting_readiness_snapshot_id=underwriting.snapshot_id,
        payoff_surface_snapshot_id=payoff.snapshot_id,
        horizon_trading_days=thesis.horizon_trading_days,
        research_class=research_class,
        bear_return_lower=bear.return_lower,
        base_return_lower=base.return_lower,
        base_return_upper=base.return_upper,
        bull_return_upper=bull.return_upper,
        nearest_catalyst_id=catalyst_id,
        nearest_catalyst_days=catalyst_days,
        nearest_catalyst_evidence_refs=catalyst_evidence,
        comparison_blockers=tuple(blockers),
        flags=tuple(dict.fromkeys(flags)),
        guardrail_evidence_id=active.evidence_id,
    )


def build_opportunity_set(
    candidates: tuple[OpportunityCandidateSnapshot, ...],
    *,
    captured_at: datetime,
    evaluation_date: date,
    horizon_trading_days: int,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> OpportunitySetSnapshot:
    """Build a Pareto frontier over fully comparable Deep Lane candidates."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if len(candidates) < 2:
        raise ValueError("cross-sectional opportunity set requires at least two candidates")
    for candidate in candidates:
        if candidate.evaluation_date != evaluation_date:
            raise ValueError("candidate evaluation_date differs from opportunity set")
        if candidate.horizon_trading_days != horizon_trading_days:
            raise ValueError("candidate horizon differs from opportunity set")
        if candidate.guardrail_evidence_id != active.evidence_id:
            raise ValueError("candidate guardrail evidence mismatch")
        if candidate.captured_at > captured_at:
            raise ValueError("opportunity-set capture cannot precede candidate capture")

    comparable = tuple(item for item in candidates if item.capital_allocation_comparable)
    relations: list[DominanceRelation] = []
    for dominator in comparable:
        for dominated in comparable:
            if dominator.security_id == dominated.security_id:
                continue
            strict = _strictly_better_dimensions(dominator, dominated)
            if strict is not None:
                relations.append(
                    DominanceRelation(
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
    fast_ready = tuple(
        sorted(
            item.security_id
            for item in candidates
            if item.research_class is OpportunityResearchClass.FAST_READY
        )
    )
    blocked = tuple(
        sorted(
            item.security_id
            for item in candidates
            if item.research_class is OpportunityResearchClass.RESEARCH_BLOCKED
            or item.comparison_blockers
        )
    )
    epistemically_flagged = tuple(
        sorted(
            item.security_id
            for item in candidates
            if item.research_class is OpportunityResearchClass.DEEP_FLAGGED
        )
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
        flags.append("insufficient_fully_comparable_deep_candidates")
    if any(item.comparison_blockers for item in candidates):
        flags.append("partial_cross_sectional_comparability")
    if len(frontier) > 1:
        flags.append("multiple_non_dominated_opportunities")
    if epistemically_flagged:
        flags.append("pareto_set_contains_epistemically_flagged_research")

    return OpportunitySetSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        horizon_trading_days=horizon_trading_days,
        candidates=candidates,
        pareto_dimensions=PARETO_DIMENSIONS,
        dominance_relations=tuple(relations),
        pareto_frontier_security_ids=frontier,
        comparable_security_ids=comparable_ids,
        fast_lane_research_security_ids=fast_ready,
        blocked_security_ids=blocked,
        epistemically_flagged_security_ids=epistemically_flagged,
        unique_pareto_leader_security_id=unique_leader,
        flags=tuple(flags),
        guardrail_evidence_id=active.evidence_id,
    )


def persist_opportunity_candidate(
    snapshot: OpportunityCandidateSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        object_name="opportunity_candidate",
        snapshot_id=snapshot.snapshot_id,
        captured_at=snapshot.captured_at,
        payload=snapshot.payload_without_id(),
        output_root=output_root,
        manifest_extra={
            "security_id": snapshot.security_id,
            "research_class": snapshot.research_class.value,
            "capital_allocation_comparable": snapshot.capital_allocation_comparable,
        },
    )


def persist_opportunity_set(
    snapshot: OpportunitySetSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        object_name="opportunity_set",
        snapshot_id=snapshot.snapshot_id,
        captured_at=snapshot.captured_at,
        payload=snapshot.payload_without_id(),
        output_root=output_root,
        manifest_extra={
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "horizon_trading_days": snapshot.horizon_trading_days,
            "candidate_count": len(snapshot.candidates),
            "comparable_candidate_count": len(snapshot.comparable_security_ids),
            "pareto_frontier_security_ids": list(snapshot.pareto_frontier_security_ids),
            "unique_pareto_leader_security_id": snapshot.unique_pareto_leader_security_id,
            "capital_allocation_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        },
    )


def _research_class(readiness: UnderwritingReadiness) -> OpportunityResearchClass:
    if readiness is UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW:
        return OpportunityResearchClass.DEEP_READY
    if readiness is UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS:
        return OpportunityResearchClass.DEEP_FLAGGED
    if readiness is UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW:
        return OpportunityResearchClass.FAST_READY
    return OpportunityResearchClass.RESEARCH_BLOCKED


def _nearest_catalyst(
    thesis: InvestmentThesisSnapshot,
    *,
    evaluation_date: date,
) -> tuple[str | None, int | None, tuple[str, ...], tuple[str, ...]]:
    dated: list[tuple[int, str, tuple[str, ...], bool]] = []
    for catalyst in thesis.catalysts:
        if catalyst.latest_date is not None and catalyst.latest_date < evaluation_date:
            continue
        if catalyst.earliest_date is None:
            continue
        already_open = catalyst.earliest_date <= evaluation_date
        days = max(0, (catalyst.earliest_date - evaluation_date).days)
        dated.append((days, catalyst.catalyst_id, catalyst.evidence_refs, already_open))
    if not dated:
        return None, None, (), ()
    days, catalyst_id, evidence_refs, already_open = min(dated, key=lambda item: item[:2])
    flags = ("nearest_catalyst_window_already_open",) if already_open else ()
    return catalyst_id, days, evidence_refs, flags


def _strictly_better_dimensions(
    candidate: OpportunityCandidateSnapshot,
    other: OpportunityCandidateSnapshot,
) -> tuple[str, ...] | None:
    if not candidate.capital_allocation_comparable or not other.capital_allocation_comparable:
        return None
    assert candidate.nearest_catalyst_days is not None
    assert other.nearest_catalyst_days is not None
    higher_better = (
        ("bear_return_lower", candidate.bear_return_lower, other.bear_return_lower),
        ("base_return_lower", candidate.base_return_lower, other.base_return_lower),
        ("base_return_upper", candidate.base_return_upper, other.base_return_upper),
        ("bull_return_upper", candidate.bull_return_upper, other.bull_return_upper),
    )
    if any(left < right for _, left, right in higher_better):
        return None
    if candidate.nearest_catalyst_days > other.nearest_catalyst_days:
        return None
    strict = [name for name, left, right in higher_better if left > right]
    if candidate.nearest_catalyst_days < other.nearest_catalyst_days:
        strict.append("nearest_catalyst_days")
    return tuple(strict) if strict else None


def _persist_snapshot(
    *,
    object_name: str,
    snapshot_id: str,
    captured_at: datetime,
    payload: dict[str, object],
    output_root: str | Path,
    manifest_extra: dict[str, object],
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
                "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
                "object_type": object_name,
                "snapshot_id": snapshot_id,
                "captured_at": captured_at.isoformat(),
                "immutable": True,
                "files": [f"{object_name}.json"],
                **manifest_extra,
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
                "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
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


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): item for key, item in cast(dict[object, object], payload).items()}


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
    "DominanceRelation",
    "OpportunityCandidateSnapshot",
    "OpportunityResearchClass",
    "OpportunitySetSnapshot",
    "PARETO_DIMENSIONS",
    "build_opportunity_candidate",
    "build_opportunity_set",
    "persist_opportunity_candidate",
    "persist_opportunity_set",
]
