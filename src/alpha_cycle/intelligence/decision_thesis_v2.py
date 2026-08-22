"""Immutable thesis and uncertainty contracts for Alpha Cycle Lab decision-system v2.

This module deliberately does not replace the existing scorecard pipeline. It defines the
forward v2 research unit that can later be integrated without changing any already-frozen
prospective experiment.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import yaml

DEFAULT_DECISION_SYSTEM_V2_POLICY = Path("config/decision_system_v2_policy.v1.yaml")
PRIMARY_HORIZONS = (60, 120, 250)
SUPPORTING_PATH_HORIZONS = (1, 5, 20)
EXPECTATION_CLAIM_CATEGORIES = frozenset(
    {"market_expectation", "market_consensus", "expectation_state"}
)


class EpistemicStatus(StrEnum):
    OBSERVED_FACT = "observed_fact"
    ACCOUNTING_IDENTITY = "accounting_identity"
    ECONOMIC_HYPOTHESIS = "economic_hypothesis"
    EMPIRICALLY_VALIDATED_RELATIONSHIP = "empirically_validated_relationship"
    UNVALIDATED_INFERENCE = "unvalidated_inference"


class ClaimDirection(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NEUTRAL = "neutral"


class UncertaintyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ThesisStatus(StrEnum):
    RESEARCH_PRIORITY = "research_priority"
    UNDERWRITING = "underwriting"
    INVESTABLE_NOW = "investable_now"
    VALUATION_GATED = "valuation_gated"
    CATALYST_GATED = "catalyst_gated"
    EVIDENCE_GATED = "evidence_gated"
    TIMING_GATED = "timing_gated"
    WEAKENING = "weakening"
    INVALIDATED = "invalidated"
    REPLACED = "replaced"
    CLOSED = "closed"


@dataclass(frozen=True)
class ThesisClaim:
    """One explicit claim in a thesis graph."""

    claim_id: str
    category: str
    statement: str
    epistemic_status: EpistemicStatus
    direction: ClaimDirection
    evidence_refs: tuple[str, ...] = ()
    opposing_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.claim_id, "claim_id")
        _require_text(self.category, "category")
        _require_text(self.statement, "statement")
        _validate_refs(self.evidence_refs, "evidence_refs")
        _validate_refs(self.opposing_evidence_refs, "opposing_evidence_refs")
        if self.epistemic_status in {
            EpistemicStatus.OBSERVED_FACT,
            EpistemicStatus.ACCOUNTING_IDENTITY,
            EpistemicStatus.EMPIRICALLY_VALIDATED_RELATIONSHIP,
        } and not self.evidence_refs:
            raise ValueError(
                f"{self.epistemic_status.value} claim requires at least one evidence reference"
            )

    def payload(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "category": self.category,
            "statement": self.statement,
            "epistemic_status": self.epistemic_status.value,
            "direction": self.direction.value,
            "evidence_refs": list(self.evidence_refs),
            "opposing_evidence_refs": list(self.opposing_evidence_refs),
        }


@dataclass(frozen=True)
class CatalystClock:
    """A dated or conditional catalyst without inventing a precise date."""

    catalyst_id: str
    statement: str
    evidence_refs: tuple[str, ...]
    earliest_date: date | None = None
    latest_date: date | None = None
    condition: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.catalyst_id, "catalyst_id")
        _require_text(self.statement, "statement")
        _validate_refs(self.evidence_refs, "evidence_refs")
        if not self.evidence_refs:
            raise ValueError("CatalystClock requires at least one evidence reference")
        if self.condition is not None:
            _require_text(self.condition, "condition")
        if self.earliest_date is not None and self.latest_date is not None:
            if self.latest_date < self.earliest_date:
                raise ValueError("latest_date cannot precede earliest_date")
        if self.earliest_date is None and self.latest_date is None and self.condition is None:
            raise ValueError("CatalystClock requires a date window or an explicit condition")

    def payload(self) -> dict[str, object]:
        return {
            "catalyst_id": self.catalyst_id,
            "statement": self.statement,
            "evidence_refs": list(self.evidence_refs),
            "earliest_date": self.earliest_date.isoformat() if self.earliest_date else None,
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
            "condition": self.condition,
        }


@dataclass(frozen=True)
class UncertaintyDimension:
    """One uncertainty dimension with an explicit rationale."""

    level: UncertaintyLevel
    rationale: str

    def __post_init__(self) -> None:
        _require_text(self.rationale, "uncertainty rationale")

    def payload(self) -> dict[str, str]:
        return {"level": self.level.value, "rationale": self.rationale}


@dataclass(frozen=True)
class ThesisUncertainty:
    evidence: UncertaintyDimension
    model: UncertaintyDimension
    regime: UncertaintyDimension
    expectation: UncertaintyDimension
    catalyst: UncertaintyDimension
    valuation: UncertaintyDimension

    def payload(self) -> dict[str, object]:
        return {
            "evidence": self.evidence.payload(),
            "model": self.model.payload(),
            "regime": self.regime.payload(),
            "expectation": self.expectation.payload(),
            "catalyst": self.catalyst.payload(),
            "valuation": self.valuation.payload(),
        }


@dataclass(frozen=True)
class DecisionSystemV2Policy:
    """Architecture policy frozen before v2 thesis integration."""

    policy_id: str
    policy_version: str
    status: str
    primary_horizons: tuple[int, ...]
    supporting_horizons: tuple[int, ...]
    exact_calendar_equivalence_claimed: bool
    automatic_order_execution_enabled: bool
    unconstrained_kelly_sizing_enabled: bool
    mathematically_optimal_weight_claim_enabled: bool
    explicit_portfolio_overlap_required_for_investable_thesis: bool
    opportunity_cost_comparison_required_for_investable_thesis: bool
    point_in_time_required: bool
    revision_lineage_required_when_source_can_revise: bool
    protected_outcome_rule_must_be_frozen_before_scoring: bool
    post_outcome_thesis_rewrite_allowed: bool
    successor_model_requires_new_research_round: bool
    uncertified_provider_semantics_may_be_promoted_to_consensus: bool
    missing_evidence_may_be_replaced_with_neutral_score: bool
    provenance_effort_must_be_proportional_to_economic_importance: bool
    existing_decision_scorecard_removed: bool
    existing_scorecard_role: str
    v2_thesis_integrated_into_existing_decision_snapshot: bool
    skhynix_2026q3_frozen_research_round_changed: bool
    evidence_id: str

    def __post_init__(self) -> None:
        if self.policy_id != "alpha_cycle_decision_system_v2":
            raise ValueError("Unexpected decision-system v2 policy id")
        if self.policy_version != "1.0-architecture-freeze":
            raise ValueError("Unexpected decision-system v2 policy version")
        if self.status != "architecture_frozen_before_v2_thesis_integration":
            raise ValueError("Unexpected decision-system v2 policy status")
        if self.primary_horizons != PRIMARY_HORIZONS:
            raise ValueError("Primary v2 horizons must remain 60/120/250 trading days")
        if self.supporting_horizons != SUPPORTING_PATH_HORIZONS:
            raise ValueError("Supporting path horizons must remain 1/5/20 trading days")
        if self.exact_calendar_equivalence_claimed:
            raise ValueError("Trading-day horizons cannot claim exact calendar equivalence")
        if self.automatic_order_execution_enabled:
            raise ValueError("Decision-system v2 cannot enable automatic order execution")
        if self.unconstrained_kelly_sizing_enabled:
            raise ValueError("Unconstrained Kelly sizing is not permitted before calibration")
        if self.mathematically_optimal_weight_claim_enabled:
            raise ValueError("Optimal-weight claims are not permitted before calibration")
        if not self.explicit_portfolio_overlap_required_for_investable_thesis:
            raise ValueError("Investable theses must assess portfolio overlap")
        if not self.opportunity_cost_comparison_required_for_investable_thesis:
            raise ValueError("Investable theses must compare opportunity cost")
        if not self.point_in_time_required:
            raise ValueError("Point-in-time evidence remains mandatory")
        if not self.revision_lineage_required_when_source_can_revise:
            raise ValueError("Revisable sources require revision lineage")
        if not self.protected_outcome_rule_must_be_frozen_before_scoring:
            raise ValueError("Protected-outcome rules must be frozen before scoring")
        if self.post_outcome_thesis_rewrite_allowed:
            raise ValueError("Post-outcome thesis rewriting is prohibited")
        if not self.successor_model_requires_new_research_round:
            raise ValueError("Successor models must use a new research-round identity")
        if self.uncertified_provider_semantics_may_be_promoted_to_consensus:
            raise ValueError("Uncertified provider semantics cannot be promoted to consensus")
        if self.missing_evidence_may_be_replaced_with_neutral_score:
            raise ValueError("Missing evidence cannot be replaced with a neutral score")
        if not self.provenance_effort_must_be_proportional_to_economic_importance:
            raise ValueError("Provenance effort must remain proportional to economic importance")
        if self.existing_decision_scorecard_removed:
            raise ValueError("The v1 scorecard must remain available as a diagnostic")
        if self.existing_scorecard_role != "backward_compatibility_and_diagnostic":
            raise ValueError("Unexpected legacy scorecard role")
        if self.v2_thesis_integrated_into_existing_decision_snapshot:
            raise ValueError("v2 thesis integration was explicitly deferred in the frozen policy")
        if self.skhynix_2026q3_frozen_research_round_changed:
            raise ValueError("Architecture v2 must not alter the frozen SK hynix 2026Q3 round")
        _validate_sha(self.evidence_id, "policy evidence_id")


@dataclass(frozen=True)
class InvestmentThesisSnapshot:
    """Content-addressed point-in-time thesis state.

    A later update creates another snapshot and references this snapshot as its parent. It
    does not mutate the original belief state.
    """

    thesis_id: str
    snapshot_version: int
    parent_snapshot_id: str | None
    captured_at: datetime
    security_id: str
    horizon_trading_days: int
    variant_view: str
    why_now: str
    claims: tuple[ThesisClaim, ...]
    catalysts: tuple[CatalystClock, ...]
    forecast_refs: tuple[str, ...]
    scenario_refs: tuple[str, ...]
    uncertainty: ThesisUncertainty
    kill_conditions: tuple[str, ...]
    first_rejection_risk: str
    portfolio_overlap: tuple[str, ...]
    opportunity_set_refs: tuple[str, ...]
    status: ThesisStatus

    def __post_init__(self) -> None:
        _require_text(self.thesis_id, "thesis_id")
        _require_text(self.security_id, "security_id")
        _require_text(self.variant_view, "variant_view")
        _require_text(self.why_now, "why_now")
        _require_text(self.first_rejection_risk, "first_rejection_risk")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if self.snapshot_version <= 0:
            raise ValueError("snapshot_version must be positive")
        if self.snapshot_version == 1 and self.parent_snapshot_id is not None:
            raise ValueError("First thesis snapshot cannot have a parent_snapshot_id")
        if self.snapshot_version > 1:
            if self.parent_snapshot_id is None:
                raise ValueError("Later thesis snapshots require parent_snapshot_id")
            _validate_sha(self.parent_snapshot_id, "parent_snapshot_id")
        if self.horizon_trading_days not in PRIMARY_HORIZONS:
            raise ValueError("Thesis horizon must be one of 60, 120, or 250 trading days")
        if not self.claims:
            raise ValueError("Investment thesis requires at least one explicit claim")
        _validate_unique_ids((claim.claim_id for claim in self.claims), "claim_id")
        _validate_unique_ids(
            (catalyst.catalyst_id for catalyst in self.catalysts),
            "catalyst_id",
        )
        _validate_refs(self.forecast_refs, "forecast_refs")
        _validate_refs(self.scenario_refs, "scenario_refs")
        _validate_refs(self.opportunity_set_refs, "opportunity_set_refs")
        _validate_text_tuple(self.kill_conditions, "kill_conditions")
        _validate_text_tuple(self.portfolio_overlap, "portfolio_overlap")
        if self.status is ThesisStatus.INVESTABLE_NOW:
            if not self.kill_conditions:
                raise ValueError("Investable thesis requires at least one kill condition")
            if not self.opportunity_set_refs:
                raise ValueError("Investable thesis requires opportunity-set comparison")
            if not self.portfolio_overlap:
                raise ValueError("Investable thesis requires explicit portfolio-overlap assessment")
            if not self.catalysts:
                raise ValueError("Investable thesis requires at least one catalyst clock")
            if not self.scenario_refs:
                raise ValueError("Investable thesis requires at least one payoff scenario")
            if not _has_evidence_backed_expectation_claim(self.claims):
                raise ValueError(
                    "Investable thesis requires an evidence-backed market-expectation claim"
                )

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "thesis_id": self.thesis_id,
            "snapshot_version": self.snapshot_version,
            "parent_snapshot_id": self.parent_snapshot_id,
            "captured_at": self.captured_at.isoformat(),
            "security_id": self.security_id,
            "horizon_trading_days": self.horizon_trading_days,
            "variant_view": self.variant_view,
            "why_now": self.why_now,
            "claims": [claim.payload() for claim in self.claims],
            "catalysts": [catalyst.payload() for catalyst in self.catalysts],
            "forecast_refs": list(self.forecast_refs),
            "scenario_refs": list(self.scenario_refs),
            "uncertainty": self.uncertainty.payload(),
            "kill_conditions": list(self.kill_conditions),
            "first_rejection_risk": self.first_rejection_risk,
            "portfolio_overlap": list(self.portfolio_overlap),
            "opportunity_set_refs": list(self.opportunity_set_refs),
            "status": self.status.value,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


def load_decision_system_v2_policy(
    path: str | Path = DEFAULT_DECISION_SYSTEM_V2_POLICY,
) -> DecisionSystemV2Policy:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Decision-system v2 policy must be a YAML object")
    root = cast(dict[str, object], payload)
    if root.get("schema_version") != 1:
        raise ValueError("Unexpected decision-system v2 policy schema_version")
    policy_raw = root.get("policy")
    if not isinstance(policy_raw, dict):
        raise ValueError("Decision-system v2 policy must contain a policy object")
    policy = cast(dict[str, object], policy_raw)
    horizons_raw = _mapping(policy.get("horizons"), "horizons")
    portfolio_raw = _mapping(policy.get("portfolio_policy"), "portfolio_policy")
    governance_raw = _mapping(policy.get("research_governance"), "research_governance")
    migration_raw = _mapping(policy.get("migration"), "migration")
    primary = _int_tuple(horizons_raw.get("primary_trading_days"), "primary_trading_days")
    supporting = _int_tuple(
        horizons_raw.get("supporting_path_trading_days"),
        "supporting_path_trading_days",
    )
    evidence_id = _sha(root)
    return DecisionSystemV2Policy(
        policy_id=str(policy.get("policy_id", "")),
        policy_version=str(policy.get("policy_version", "")),
        status=str(policy.get("status", "")),
        primary_horizons=primary,
        supporting_horizons=supporting,
        exact_calendar_equivalence_claimed=_bool_field(
            horizons_raw, "exact_calendar_equivalence_claimed"
        ),
        automatic_order_execution_enabled=_bool_field(
            portfolio_raw, "automatic_order_execution_enabled"
        ),
        unconstrained_kelly_sizing_enabled=_bool_field(
            portfolio_raw, "unconstrained_kelly_sizing_enabled"
        ),
        mathematically_optimal_weight_claim_enabled=_bool_field(
            portfolio_raw, "mathematically_optimal_weight_claim_enabled"
        ),
        explicit_portfolio_overlap_required_for_investable_thesis=_bool_field(
            portfolio_raw,
            "explicit_portfolio_overlap_required_for_investable_thesis",
        ),
        opportunity_cost_comparison_required_for_investable_thesis=_bool_field(
            portfolio_raw,
            "opportunity_cost_comparison_required_for_investable_thesis",
        ),
        point_in_time_required=_bool_field(governance_raw, "point_in_time_required"),
        revision_lineage_required_when_source_can_revise=_bool_field(
            governance_raw, "revision_lineage_required_when_source_can_revise"
        ),
        protected_outcome_rule_must_be_frozen_before_scoring=_bool_field(
            governance_raw, "protected_outcome_rule_must_be_frozen_before_scoring"
        ),
        post_outcome_thesis_rewrite_allowed=_bool_field(
            governance_raw, "post_outcome_thesis_rewrite_allowed"
        ),
        successor_model_requires_new_research_round=_bool_field(
            governance_raw, "successor_model_requires_new_research_round"
        ),
        uncertified_provider_semantics_may_be_promoted_to_consensus=_bool_field(
            governance_raw,
            "uncertified_provider_semantics_may_be_promoted_to_consensus",
        ),
        missing_evidence_may_be_replaced_with_neutral_score=_bool_field(
            governance_raw, "missing_evidence_may_be_replaced_with_neutral_score"
        ),
        provenance_effort_must_be_proportional_to_economic_importance=_bool_field(
            governance_raw,
            "provenance_effort_must_be_proportional_to_economic_importance",
        ),
        existing_decision_scorecard_removed=_bool_field(
            migration_raw, "existing_decision_scorecard_removed"
        ),
        existing_scorecard_role=str(migration_raw.get("existing_scorecard_role", "")),
        v2_thesis_integrated_into_existing_decision_snapshot=_bool_field(
            migration_raw,
            "v2_thesis_integrated_into_existing_decision_snapshot",
        ),
        skhynix_2026q3_frozen_research_round_changed=_bool_field(
            migration_raw, "skhynix_2026q3_frozen_research_round_changed"
        ),
        evidence_id=evidence_id,
    )


def _has_evidence_backed_expectation_claim(claims: tuple[ThesisClaim, ...]) -> bool:
    for claim in claims:
        category = claim.category.strip().casefold().replace("-", "_").replace(" ", "_")
        if category in EXPECTATION_CLAIM_CATEGORIES and claim.evidence_refs:
            return True
    return False


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _validate_refs(values: tuple[str, ...], field: str) -> None:
    _validate_text_tuple(values, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicate references")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)


def _validate_unique_ids(values: Iterable[str], field: str) -> None:
    normalized = tuple(value.strip() for value in values)
    if any(not item for item in normalized):
        raise ValueError(f"{field} cannot be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"Duplicate {field} values are prohibited")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _bool_field(mapping: dict[str, object], field: str) -> bool:
    value = mapping.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a YAML boolean")
    return value


def _int_tuple(value: object, field: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty list")
    if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in value):
        raise ValueError(f"{field} must contain positive integers")
    return tuple(cast(list[int], value))


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
