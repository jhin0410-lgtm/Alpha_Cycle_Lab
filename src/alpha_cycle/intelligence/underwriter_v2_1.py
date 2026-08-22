"""Fail-closed research-readiness underwriter for Alpha Cycle Lab Decision System v2.1.

The underwriter assembles already-frozen research evidence. It does not create an investment
thesis, select a target price, calculate an optimal position size, or execute a trade. A ready
state means only that the documented Fast or Deep Lane evidence contract is sufficiently
populated for human PM review.
"""

from __future__ import annotations

import hashlib
import json
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
from alpha_cycle.intelligence.decision_thesis_v2 import (
    InvestmentThesisSnapshot,
    ThesisStatus,
)
from alpha_cycle.intelligence.epistemic_defense import EpistemicDefensePackageSnapshot
from alpha_cycle.intelligence.expectation_state import (
    ExpectationKind,
    ExpectationStateSnapshot,
)
from alpha_cycle.intelligence.forecast_ledger import ForecastRegistrationSnapshot
from alpha_cycle.intelligence.forward_valuation import (
    ForwardValuationStateSnapshot,
    ForwardValuationStatus,
)
from alpha_cycle.intelligence.payoff_surface import PayoffSurfaceSnapshot
from alpha_cycle.intelligence.price_implied_requirement import (
    PriceImpliedRequirementSnapshot,
    PriceImpliedRequirementStatus,
)
from alpha_cycle.intelligence.semiconductor_causal_graph import (
    SemiconductorCausalGraphSnapshot,
)

UNDERWRITER_SCHEMA_VERSION = 1
SUPPLEMENTAL_DEEP_ELEMENTS = (
    "price_implied_requirement",
    "catalyst",
    "kill_condition",
)
TERMINAL_THESIS_STATUSES = {
    ThesisStatus.INVALIDATED,
    ThesisStatus.REPLACED,
    ThesisStatus.CLOSED,
}


class UnderwritingLane(StrEnum):
    FAST = "fast"
    DEEP = "deep"


class UnderwritingReadiness(StrEnum):
    FAST_LANE_BLOCKED = "fast_lane_blocked"
    FAST_LANE_READY_FOR_HUMAN_REVIEW = "fast_lane_ready_for_human_review"
    DEEP_LANE_BLOCKED = "deep_lane_blocked"
    DEEP_LANE_READY_FOR_HUMAN_REVIEW = "deep_lane_ready_for_human_review"
    DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS = "deep_lane_ready_with_epistemic_flags"


@dataclass(frozen=True)
class UnderwritingContextSnapshot:
    """Provenance links for context not yet represented by a richer typed contract."""

    captured_at: datetime
    evaluation_date: date
    thesis_snapshot_id: str
    security_id: str
    transmission_evidence_refs: tuple[str, ...]
    opportunity_set_comparison_refs: tuple[str, ...]
    portfolio_overlap_evidence_refs: tuple[str, ...]
    guardrail_evidence_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _validate_sha(self.thesis_snapshot_id, "thesis_snapshot_id")
        _require_text(self.security_id, "security_id")
        _validate_sha_tuple(self.transmission_evidence_refs, "transmission_evidence_refs")
        _validate_sha_tuple(
            self.opportunity_set_comparison_refs,
            "opportunity_set_comparison_refs",
        )
        _validate_sha_tuple(
            self.portfolio_overlap_evidence_refs,
            "portfolio_overlap_evidence_refs",
        )
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _validate_text_tuple(self.warnings, "warnings")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": UNDERWRITER_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "security_id": self.security_id,
            "transmission_evidence_refs": list(self.transmission_evidence_refs),
            "opportunity_set_comparison_refs": list(
                self.opportunity_set_comparison_refs
            ),
            "portfolio_overlap_evidence_refs": list(
                self.portfolio_overlap_evidence_refs
            ),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "warnings": list(self.warnings),
            "content_semantics_independently_verified": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class ForecastTournamentAssessment:
    """Comparability check for a preregistered multi-forecaster tournament."""

    comparable: bool
    forecast_snapshot_ids: tuple[str, ...]
    forecast_ids: tuple[str, ...]
    security_id: str | None
    target_variable: str | None
    target_date: date | None
    unit: str | None
    forecast_origin: datetime | None
    information_cutoff: datetime | None
    primary_error_metric: str | None
    distinct_forecaster_count: int
    dependency_cluster_count: int
    blockers: tuple[str, ...]
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_sha_tuple(self.forecast_snapshot_ids, "forecast_snapshot_ids")
        _validate_text_tuple(self.forecast_ids, "forecast_ids")
        _validate_text_tuple(self.blockers, "blockers")
        _validate_text_tuple(self.flags, "flags")
        if self.distinct_forecaster_count < 0 or self.dependency_cluster_count < 0:
            raise ValueError("forecast tournament counts cannot be negative")
        if self.comparable and self.blockers:
            raise ValueError("comparable forecast tournament cannot contain blockers")

    def payload(self) -> dict[str, object]:
        return {
            "comparable": self.comparable,
            "forecast_snapshot_ids": list(self.forecast_snapshot_ids),
            "forecast_ids": list(self.forecast_ids),
            "security_id": self.security_id,
            "target_variable": self.target_variable,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "unit": self.unit,
            "forecast_origin": (
                self.forecast_origin.isoformat() if self.forecast_origin else None
            ),
            "information_cutoff": (
                self.information_cutoff.isoformat() if self.information_cutoff else None
            ),
            "primary_error_metric": self.primary_error_metric,
            "distinct_forecaster_count": self.distinct_forecaster_count,
            "dependency_cluster_count": self.dependency_cluster_count,
            "blockers": list(self.blockers),
            "flags": list(self.flags),
        }


@dataclass(frozen=True)
class UnderwritingReadinessSnapshot:
    """Immutable result of assembling research evidence for human PM review."""

    captured_at: datetime
    evaluation_date: date
    thesis_snapshot_id: str
    security_id: str
    lane: UnderwritingLane
    readiness: UnderwritingReadiness
    guardrail_evidence_id: str
    context_snapshot_id: str
    causal_graph_snapshot_id: str | None
    forecast_tournament: ForecastTournamentAssessment
    expectation_state_snapshot_id: str | None
    forward_valuation_snapshot_id: str | None
    price_implied_requirement_snapshot_id: str | None
    payoff_surface_snapshot_id: str | None
    epistemic_defense_snapshot_id: str | None
    required_elements_satisfied: tuple[str, ...]
    required_elements_missing: tuple[str, ...]
    blockers: tuple[str, ...]
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _validate_sha(self.thesis_snapshot_id, "thesis_snapshot_id")
        _require_text(self.security_id, "security_id")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _validate_sha(self.context_snapshot_id, "context_snapshot_id")
        for value, field in (
            (self.causal_graph_snapshot_id, "causal_graph_snapshot_id"),
            (self.expectation_state_snapshot_id, "expectation_state_snapshot_id"),
            (self.forward_valuation_snapshot_id, "forward_valuation_snapshot_id"),
            (
                self.price_implied_requirement_snapshot_id,
                "price_implied_requirement_snapshot_id",
            ),
            (self.payoff_surface_snapshot_id, "payoff_surface_snapshot_id"),
            (self.epistemic_defense_snapshot_id, "epistemic_defense_snapshot_id"),
        ):
            if value is not None:
                _validate_sha(value, field)
        _validate_text_tuple(self.required_elements_satisfied, "required_elements_satisfied")
        _validate_text_tuple(self.required_elements_missing, "required_elements_missing")
        _validate_text_tuple(self.blockers, "blockers")
        _validate_text_tuple(self.flags, "flags")
        overlap = set(self.required_elements_satisfied) & set(self.required_elements_missing)
        if overlap:
            raise ValueError("underwriter element cannot be both satisfied and missing")
        ready_states = {
            UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW,
            UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
            UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS,
        }
        if self.readiness in ready_states and (self.required_elements_missing or self.blockers):
            raise ValueError("ready underwriting state cannot contain missing elements or blockers")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": UNDERWRITER_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "security_id": self.security_id,
            "lane": self.lane.value,
            "readiness": self.readiness.value,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "context_snapshot_id": self.context_snapshot_id,
            "causal_graph_snapshot_id": self.causal_graph_snapshot_id,
            "forecast_tournament": self.forecast_tournament.payload(),
            "expectation_state_snapshot_id": self.expectation_state_snapshot_id,
            "forward_valuation_snapshot_id": self.forward_valuation_snapshot_id,
            "price_implied_requirement_snapshot_id": (
                self.price_implied_requirement_snapshot_id
            ),
            "payoff_surface_snapshot_id": self.payoff_surface_snapshot_id,
            "epistemic_defense_snapshot_id": self.epistemic_defense_snapshot_id,
            "required_elements_satisfied": list(self.required_elements_satisfied),
            "required_elements_missing": list(self.required_elements_missing),
            "blockers": list(self.blockers),
            "flags": list(self.flags),
            "investability_decision_enabled": False,
            "automatic_thesis_transition_enabled": False,
            "target_price_enabled": False,
            "optimal_position_size_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


def build_underwriting_context(
    thesis: InvestmentThesisSnapshot,
    *,
    captured_at: datetime,
    evaluation_date: date,
    transmission_evidence_refs: tuple[str, ...] = (),
    opportunity_set_comparison_refs: tuple[str, ...] = (),
    portfolio_overlap_evidence_refs: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> UnderwritingContextSnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if captured_at < thesis.captured_at:
        raise ValueError("underwriting context cannot precede thesis capture")
    return UnderwritingContextSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        thesis_snapshot_id=thesis.snapshot_id,
        security_id=thesis.security_id,
        transmission_evidence_refs=transmission_evidence_refs,
        opportunity_set_comparison_refs=opportunity_set_comparison_refs,
        portfolio_overlap_evidence_refs=portfolio_overlap_evidence_refs,
        guardrail_evidence_id=active.evidence_id,
        warnings=warnings,
    )


def assess_forecast_tournament(
    forecasts: tuple[ForecastRegistrationSnapshot, ...],
    *,
    thesis_security_id: str,
    evaluation_date: date,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> ForecastTournamentAssessment:
    """Require forecasts to be genuinely comparable, not merely numerous."""

    active = guardrails or load_decision_system_v21_guardrails()
    blockers: list[str] = []
    flags: list[str] = []
    if len(forecasts) < 2:
        blockers.append("forecast_tournament_requires_at_least_two_registrations")

    snapshot_ids = tuple(item.snapshot_id for item in forecasts)
    forecast_ids = tuple(item.forecast_id for item in forecasts)
    if len(set(snapshot_ids)) != len(snapshot_ids):
        blockers.append("duplicate_forecast_snapshot")
    if len(set(forecast_ids)) != len(forecast_ids):
        blockers.append("duplicate_forecast_id")

    first = forecasts[0] if forecasts else None
    security_id = first.security_id if first else None
    target_variable = first.target_variable if first else None
    target_date = first.target_date if first else None
    unit = first.unit if first else None
    forecast_origin = first.forecast_origin if first else None
    information_cutoff = first.information_cutoff if first else None
    primary_error_metric = first.primary_error_metric.value if first else None

    if first is not None:
        target_key = first.target_key
        for item in forecasts:
            if item.guardrail_evidence_id != active.evidence_id:
                blockers.append("forecast_guardrail_mismatch")
            if item.security_id != thesis_security_id:
                blockers.append("forecast_security_mismatch")
            if item.target_key != target_key:
                blockers.append("forecast_target_mismatch")
            if item.forecast_origin != first.forecast_origin:
                blockers.append("forecast_origin_mismatch")
            if item.information_cutoff != first.information_cutoff:
                blockers.append("forecast_information_cutoff_mismatch")
            if item.primary_error_metric is not first.primary_error_metric:
                blockers.append("forecast_error_metric_mismatch")
            if item.target_date <= evaluation_date:
                blockers.append("forecast_target_not_forward_of_evaluation_date")

    forecaster_descriptors = {
        (item.forecaster_kind.value, item.model_family) for item in forecasts
    }
    if len(forecasts) >= 2 and len(forecaster_descriptors) < 2:
        blockers.append("forecast_tournament_requires_distinct_forecasters")
    dependency_clusters = {item.dependency_cluster_id for item in forecasts}
    if len(forecasts) >= 2 and len(dependency_clusters) < len(forecasts):
        flags.append("forecast_dependency_overlap")

    return ForecastTournamentAssessment(
        comparable=not blockers,
        forecast_snapshot_ids=snapshot_ids,
        forecast_ids=forecast_ids,
        security_id=security_id,
        target_variable=target_variable,
        target_date=target_date,
        unit=unit,
        forecast_origin=forecast_origin,
        information_cutoff=information_cutoff,
        primary_error_metric=primary_error_metric,
        distinct_forecaster_count=len(forecaster_descriptors),
        dependency_cluster_count=len(dependency_clusters),
        blockers=tuple(dict.fromkeys(blockers)),
        flags=tuple(dict.fromkeys(flags)),
    )


def build_underwriting_readiness(
    thesis: InvestmentThesisSnapshot,
    context: UnderwritingContextSnapshot,
    *,
    lane: UnderwritingLane,
    captured_at: datetime,
    evaluation_date: date,
    forecasts: tuple[ForecastRegistrationSnapshot, ...] = (),
    causal_graph: SemiconductorCausalGraphSnapshot | None = None,
    expectations: ExpectationStateSnapshot | None = None,
    forward_valuation: ForwardValuationStateSnapshot | None = None,
    price_implied: PriceImpliedRequirementSnapshot | None = None,
    payoff_surface: PayoffSurfaceSnapshot | None = None,
    epistemic_defense: EpistemicDefensePackageSnapshot | None = None,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> UnderwritingReadinessSnapshot:
    """Assemble lane readiness without changing thesis status or approving an investment."""

    active = guardrails or load_decision_system_v21_guardrails()
    _validate_bindings(
        thesis,
        context,
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        active=active,
        causal_graph=causal_graph,
        expectations=expectations,
        forward_valuation=forward_valuation,
        price_implied=price_implied,
        payoff_surface=payoff_surface,
        epistemic_defense=epistemic_defense,
    )
    tournament = assess_forecast_tournament(
        forecasts,
        thesis_security_id=thesis.security_id,
        evaluation_date=evaluation_date,
        guardrails=active,
    )

    if lane is UnderwritingLane.FAST:
        required = active.fast_lane_required_elements
        satisfied_map = _fast_lane_elements(
            thesis,
            context,
            causal_graph=causal_graph,
            expectations=expectations,
            price_implied=price_implied,
            epistemic_defense=epistemic_defense,
        )
        blockers: list[str] = []
        if thesis.status.value not in active.fast_lane_allowed_thesis_statuses:
            blockers.append("thesis_status_not_allowed_in_fast_lane")
        missing = tuple(item for item in required if not satisfied_map.get(item, False))
        satisfied = tuple(item for item in required if satisfied_map.get(item, False))
        flags = _epistemic_flags(epistemic_defense)
        readiness = (
            UnderwritingReadiness.FAST_LANE_BLOCKED
            if missing or blockers
            else UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW
        )
    else:
        required = active.deep_lane_required_elements + SUPPLEMENTAL_DEEP_ELEMENTS
        satisfied_map = _deep_lane_elements(
            thesis,
            context,
            tournament=tournament,
            causal_graph=causal_graph,
            expectations=expectations,
            forward_valuation=forward_valuation,
            price_implied=price_implied,
            payoff_surface=payoff_surface,
            epistemic_defense=epistemic_defense,
        )
        blockers = []
        if thesis.status in TERMINAL_THESIS_STATUSES:
            blockers.append("terminal_thesis_status")
        missing = tuple(item for item in required if not satisfied_map.get(item, False))
        satisfied = tuple(item for item in required if satisfied_map.get(item, False))
        flags = tuple(
            dict.fromkeys(
                tournament.flags
                + _epistemic_flags(epistemic_defense)
                + (("sector_level_causal_graph",) if causal_graph and causal_graph.security_id is None else ())
            )
        )
        if missing or blockers:
            readiness = UnderwritingReadiness.DEEP_LANE_BLOCKED
        elif flags:
            readiness = UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS
        else:
            readiness = UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW

    return UnderwritingReadinessSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        thesis_snapshot_id=thesis.snapshot_id,
        security_id=thesis.security_id,
        lane=lane,
        readiness=readiness,
        guardrail_evidence_id=active.evidence_id,
        context_snapshot_id=context.snapshot_id,
        causal_graph_snapshot_id=causal_graph.snapshot_id if causal_graph else None,
        forecast_tournament=tournament,
        expectation_state_snapshot_id=expectations.snapshot_id if expectations else None,
        forward_valuation_snapshot_id=(
            forward_valuation.snapshot_id if forward_valuation else None
        ),
        price_implied_requirement_snapshot_id=(
            price_implied.snapshot_id if price_implied else None
        ),
        payoff_surface_snapshot_id=payoff_surface.snapshot_id if payoff_surface else None,
        epistemic_defense_snapshot_id=(
            epistemic_defense.snapshot_id if epistemic_defense else None
        ),
        required_elements_satisfied=satisfied,
        required_elements_missing=missing,
        blockers=tuple(blockers),
        flags=tuple(flags),
    )


def persist_underwriting_context(
    snapshot: UnderwritingContextSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        object_name="underwriting_context",
        snapshot_id=snapshot.snapshot_id,
        captured_at=snapshot.captured_at,
        payload=snapshot.payload_without_id(),
        output_root=output_root,
        manifest_extra={
            "thesis_snapshot_id": snapshot.thesis_snapshot_id,
            "security_id": snapshot.security_id,
        },
    )


def persist_underwriting_readiness(
    snapshot: UnderwritingReadinessSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        object_name="underwriting_readiness",
        snapshot_id=snapshot.snapshot_id,
        captured_at=snapshot.captured_at,
        payload=snapshot.payload_without_id(),
        output_root=output_root,
        manifest_extra={
            "thesis_snapshot_id": snapshot.thesis_snapshot_id,
            "security_id": snapshot.security_id,
            "lane": snapshot.lane.value,
            "readiness": snapshot.readiness.value,
            "investability_decision_enabled": False,
            "automatic_execution_enabled": False,
        },
    )


def _fast_lane_elements(
    thesis: InvestmentThesisSnapshot,
    context: UnderwritingContextSnapshot,
    *,
    causal_graph: SemiconductorCausalGraphSnapshot | None,
    expectations: ExpectationStateSnapshot | None,
    price_implied: PriceImpliedRequirementSnapshot | None,
    epistemic_defense: EpistemicDefensePackageSnapshot | None,
) -> dict[str, bool]:
    return {
        "why_now": bool(thesis.why_now.strip()),
        "catalyst": bool(thesis.catalysts),
        "transmission": bool(context.transmission_evidence_refs) or causal_graph is not None,
        "expectation_or_priced_in_assessment": (
            _has_security_expectation(expectations, thesis.security_id)
            or _has_available_price_implied(price_implied, thesis.security_id)
        ),
        "top_downside": bool(thesis.first_rejection_risk.strip()),
        "counter_thesis": epistemic_defense is not None,
        "kill_condition": bool(thesis.kill_conditions),
        "position_uncertainty": thesis.uncertainty is not None,
    }


def _deep_lane_elements(
    thesis: InvestmentThesisSnapshot,
    context: UnderwritingContextSnapshot,
    *,
    tournament: ForecastTournamentAssessment,
    causal_graph: SemiconductorCausalGraphSnapshot | None,
    expectations: ExpectationStateSnapshot | None,
    forward_valuation: ForwardValuationStateSnapshot | None,
    price_implied: PriceImpliedRequirementSnapshot | None,
    payoff_surface: PayoffSurfaceSnapshot | None,
    epistemic_defense: EpistemicDefensePackageSnapshot | None,
) -> dict[str, bool]:
    return {
        "full_causal_graph": causal_graph is not None,
        "forecast_tournament": tournament.comparable,
        "certified_expectation": _has_comparable_market_consensus(expectations, tournament),
        "valuation": _has_available_forward_valuation(forward_valuation, thesis.security_id),
        "payoff_surface": payoff_surface is not None,
        "counter_thesis": epistemic_defense is not None,
        "outside_graph_scan": epistemic_defense is not None,
        "opportunity_set_comparison": bool(thesis.opportunity_set_refs)
        and bool(context.opportunity_set_comparison_refs),
        "portfolio_overlap": bool(thesis.portfolio_overlap)
        and bool(context.portfolio_overlap_evidence_refs),
        "price_implied_requirement": _has_available_price_implied(
            price_implied,
            thesis.security_id,
        ),
        "catalyst": bool(thesis.catalysts),
        "kill_condition": bool(thesis.kill_conditions),
    }


def _validate_bindings(
    thesis: InvestmentThesisSnapshot,
    context: UnderwritingContextSnapshot,
    *,
    captured_at: datetime,
    evaluation_date: date,
    active: DecisionSystemV21Guardrails,
    causal_graph: SemiconductorCausalGraphSnapshot | None,
    expectations: ExpectationStateSnapshot | None,
    forward_valuation: ForwardValuationStateSnapshot | None,
    price_implied: PriceImpliedRequirementSnapshot | None,
    payoff_surface: PayoffSurfaceSnapshot | None,
    epistemic_defense: EpistemicDefensePackageSnapshot | None,
) -> None:
    _require_aware(captured_at, "captured_at")
    if captured_at < thesis.captured_at or captured_at < context.captured_at:
        raise ValueError("underwriting readiness cannot precede thesis or context capture")
    if context.thesis_snapshot_id != thesis.snapshot_id:
        raise ValueError("underwriting context is bound to a different thesis")
    if context.security_id != thesis.security_id:
        raise ValueError("underwriting context security differs from thesis")
    if context.evaluation_date != evaluation_date:
        raise ValueError("underwriting context evaluation_date mismatch")
    if context.guardrail_evidence_id != active.evidence_id:
        raise ValueError("underwriting context guardrail evidence mismatch")

    if causal_graph is not None:
        if causal_graph.guardrail_evidence_id != active.evidence_id:
            raise ValueError("causal graph guardrail evidence mismatch")
        if causal_graph.security_id not in {None, thesis.security_id}:
            raise ValueError("causal graph security differs from thesis")
        try:
            graph_date = date.fromisoformat(causal_graph.evaluation_date)
        except ValueError as exc:
            raise ValueError("causal graph evaluation_date is not ISO date") from exc
        if graph_date != evaluation_date:
            raise ValueError("causal graph evaluation_date mismatch")
        if causal_graph.captured_at > captured_at:
            raise ValueError("causal graph cannot be captured after underwriting readiness")

    if expectations is not None:
        if expectations.evaluation_date != evaluation_date:
            raise ValueError("expectation state evaluation_date mismatch")
        if expectations.captured_at > captured_at:
            raise ValueError("expectation state cannot be captured after underwriting readiness")

    if forward_valuation is not None:
        if expectations is None:
            raise ValueError("forward valuation requires the bound expectation state")
        if forward_valuation.evaluation_date != evaluation_date:
            raise ValueError("forward valuation evaluation_date mismatch")
        if forward_valuation.expectation_state_snapshot_id != expectations.snapshot_id:
            raise ValueError("forward valuation is bound to a different expectation state")
        if forward_valuation.guardrail_evidence_id != active.evidence_id:
            raise ValueError("forward valuation guardrail evidence mismatch")
        if forward_valuation.captured_at > captured_at:
            raise ValueError("forward valuation cannot be captured after underwriting readiness")

    if price_implied is not None:
        if price_implied.evaluation_date != evaluation_date:
            raise ValueError("price-implied requirement evaluation_date mismatch")
        if price_implied.security_id != thesis.security_id:
            raise ValueError("price-implied requirement security differs from thesis")
        if price_implied.guardrail_evidence_id != active.evidence_id:
            raise ValueError("price-implied requirement guardrail evidence mismatch")
        if price_implied.captured_at > captured_at:
            raise ValueError("price-implied requirement cannot postdate underwriting readiness")

    if payoff_surface is not None:
        if payoff_surface.thesis_snapshot_id != thesis.snapshot_id:
            raise ValueError("payoff surface is bound to a different thesis")
        if payoff_surface.security_id != thesis.security_id:
            raise ValueError("payoff surface security differs from thesis")
        if payoff_surface.horizon_trading_days != thesis.horizon_trading_days:
            raise ValueError("payoff surface horizon differs from thesis")
        if payoff_surface.guardrail_evidence_id != active.evidence_id:
            raise ValueError("payoff surface guardrail evidence mismatch")
        if payoff_surface.captured_at > captured_at:
            raise ValueError("payoff surface cannot postdate underwriting readiness")

    if epistemic_defense is not None:
        if epistemic_defense.thesis_snapshot_id != thesis.snapshot_id:
            raise ValueError("epistemic defense is bound to a different thesis")
        if epistemic_defense.guardrail_evidence_id != active.evidence_id:
            raise ValueError("epistemic defense guardrail evidence mismatch")
        if epistemic_defense.captured_at > captured_at:
            raise ValueError("epistemic defense cannot postdate underwriting readiness")


def _has_security_expectation(
    expectations: ExpectationStateSnapshot | None,
    security_id: str,
) -> bool:
    return expectations is not None and any(
        item.security_id == security_id for item in expectations.observations
    )


def _has_comparable_market_consensus(
    expectations: ExpectationStateSnapshot | None,
    tournament: ForecastTournamentAssessment,
) -> bool:
    if expectations is None or not tournament.comparable:
        return False
    if (
        tournament.security_id is None
        or tournament.target_variable is None
        or tournament.target_date is None
        or tournament.unit is None
    ):
        return False
    return any(
        item.security_id == tournament.security_id
        and item.expectation_kind is ExpectationKind.MARKET_CONSENSUS
        and item.market_consensus_certified
        and item.metric.value == tournament.target_variable
        and item.target_period_end == tournament.target_date
        and item.unit == tournament.unit
        for item in expectations.observations
    )


def _has_available_forward_valuation(
    valuation: ForwardValuationStateSnapshot | None,
    security_id: str,
) -> bool:
    return valuation is not None and any(
        item.security_id == security_id and item.status is ForwardValuationStatus.AVAILABLE
        for item in valuation.observations
    )


def _has_available_price_implied(
    price_implied: PriceImpliedRequirementSnapshot | None,
    security_id: str,
) -> bool:
    return price_implied is not None and any(
        item.security_id == security_id
        and item.status is PriceImpliedRequirementStatus.AVAILABLE
        for item in price_implied.observations
    )


def _epistemic_flags(
    epistemic_defense: EpistemicDefensePackageSnapshot | None,
) -> tuple[str, ...]:
    if epistemic_defense is None:
        return ()
    flags = list(epistemic_defense.research_flags)
    if epistemic_defense.high_materiality_counter_explanation_count:
        flags.append("high_materiality_counter_explanation")
    if epistemic_defense.high_materiality_unresolved_contradiction_count:
        flags.append("high_materiality_unresolved_contradiction")
    if epistemic_defense.uncovered_high_materiality_blind_spot_count:
        flags.append("uncovered_high_materiality_blind_spot")
    if epistemic_defense.blind_spot_promotion_candidate_count:
        flags.append("blind_spot_promotion_candidate")
    return tuple(dict.fromkeys(flags))


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
                "schema_version": UNDERWRITER_SCHEMA_VERSION,
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
                "schema_version": UNDERWRITER_SCHEMA_VERSION,
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
    "ForecastTournamentAssessment",
    "UnderwritingContextSnapshot",
    "UnderwritingLane",
    "UnderwritingReadiness",
    "UnderwritingReadinessSnapshot",
    "assess_forecast_tournament",
    "build_underwriting_context",
    "build_underwriting_readiness",
    "persist_underwriting_context",
    "persist_underwriting_readiness",
]
