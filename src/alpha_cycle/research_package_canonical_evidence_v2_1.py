"""Canonical persisted-evidence reconstruction for Decision System v2.1 packages.

This module is intentionally stricter than repository selection.  A bound evidence id is not
accepted merely because a self-hashed JSON object exists.  The persisted payload must reconstruct
the typed object, round-trip to the exact canonical payload, live in its canonical content-addressed
directory, and carry the complete manifest emitted by the owning persistence contract.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import (
    EpistemicStatus,
    InvestmentThesisSnapshot,
)
from alpha_cycle.intelligence.decision_view_v2_1 import (
    DecisionExpectationGapSnapshot,
    DecisionViewSnapshot,
    build_decision_expectation_gap,
)
from alpha_cycle.intelligence.epistemic_defense import (
    EPISTEMIC_DEFENSE_SCHEMA_VERSION,
    EpistemicDefensePackageSnapshot,
)
from alpha_cycle.intelligence.expectation_gap_contract import ExpectationSemantics
from alpha_cycle.intelligence.expectation_state import (
    EXPECTATION_STATE_SCHEMA_VERSION,
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
)
from alpha_cycle.intelligence.forward_valuation import (
    FORWARD_VALUATION_SCHEMA_VERSION,
    ForwardValuationMetric,
    ForwardValuationObservation,
    ForwardValuationStateSnapshot,
    ForwardValuationStatus,
)
from alpha_cycle.intelligence.payoff_surface import PayoffSurfaceSnapshot
from alpha_cycle.intelligence.price_implied_requirement import (
    PRICE_IMPLIED_SCHEMA_VERSION,
    PriceImpliedRequirementObservation,
    PriceImpliedRequirementSnapshot,
    PriceImpliedRequirementStatus,
    ReferenceFrameKind,
)
from alpha_cycle.intelligence.semiconductor_causal_graph import (
    CAUSAL_GRAPH_SCHEMA_VERSION,
    CausalEdge,
    CausalEdgeDirection,
    CausalNode,
    CausalNodeType,
    CriticalStateVariable,
    SemiconductorCausalGraphSnapshot,
    TransmissionLag,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    UNDERWRITER_SCHEMA_VERSION,
    UnderwritingContextSnapshot,
    UnderwritingLane,
    UnderwritingReadinessSnapshot,
)
from alpha_cycle.research_package_integrity_v2_1 import require_trusted_artifact_root


class CanonicalResearchEvidenceError(ValueError):
    """Raised when a persisted evidence envelope cannot be trusted."""


def underwriting_bound_evidence_is_valid(
    root: str | Path,
    *,
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    payoff: PayoffSurfaceSnapshot | None,
) -> bool:
    """Revalidate every persisted evidence binding used by a ready underwriting snapshot."""

    from alpha_cycle.research_package_source_revalidation_v2_1 import (
        epistemic_package_sources_are_canonical,
        forward_valuation_sources_are_canonical,
        price_implied_sources_are_canonical,
    )

    artifact_root = Path(root)
    active = load_decision_system_v21_guardrails()
    if underwriting.guardrail_evidence_id != active.evidence_id:
        return False

    context = load_canonical_underwriting_context(
        artifact_root,
        underwriting.context_snapshot_id,
    )
    if context is None:
        return False
    if (
        context.thesis_snapshot_id != thesis.snapshot_id
        or context.security_id != thesis.security_id
        or context.evaluation_date != underwriting.evaluation_date
        or context.guardrail_evidence_id != underwriting.guardrail_evidence_id
        or context.captured_at > underwriting.captured_at
    ):
        return False

    graph = _load_optional(
        underwriting.causal_graph_snapshot_id,
        lambda snapshot_id: load_canonical_causal_graph(artifact_root, snapshot_id),
    )
    if underwriting.causal_graph_snapshot_id is not None and graph is None:
        return False
    if graph is not None and (
        graph.security_id not in {None, thesis.security_id}
        or graph.evaluation_date != underwriting.evaluation_date.isoformat()
        or graph.guardrail_evidence_id != underwriting.guardrail_evidence_id
        or graph.captured_at > underwriting.captured_at
    ):
        return False

    expectations = _load_optional(
        underwriting.expectation_state_snapshot_id,
        lambda snapshot_id: load_canonical_expectation_state(artifact_root, snapshot_id),
    )
    if underwriting.expectation_state_snapshot_id is not None and expectations is None:
        return False
    if expectations is not None and (
        expectations.evaluation_date != underwriting.evaluation_date
        or expectations.captured_at > underwriting.captured_at
    ):
        return False

    forward_valuation = _load_optional(
        underwriting.forward_valuation_snapshot_id,
        lambda snapshot_id: load_canonical_forward_valuation(artifact_root, snapshot_id),
    )
    if underwriting.forward_valuation_snapshot_id is not None and forward_valuation is None:
        return False
    if forward_valuation is not None:
        if expectations is None:
            return False
        if (
            forward_valuation.evaluation_date != underwriting.evaluation_date
            or forward_valuation.expectation_state_snapshot_id != expectations.snapshot_id
            or forward_valuation.guardrail_evidence_id
            != underwriting.guardrail_evidence_id
            or forward_valuation.captured_at > underwriting.captured_at
        ):
            return False
        if not forward_valuation_sources_are_canonical(
            artifact_root,
            snapshot=forward_valuation,
            expectations=expectations,
        ):
            return False

    price_implied = _load_optional(
        underwriting.price_implied_requirement_snapshot_id,
        lambda snapshot_id: load_canonical_price_implied(artifact_root, snapshot_id),
    )
    if underwriting.price_implied_requirement_snapshot_id is not None and price_implied is None:
        return False
    if price_implied is not None and (
        price_implied.security_id != thesis.security_id
        or price_implied.evaluation_date != underwriting.evaluation_date
        or price_implied.guardrail_evidence_id != underwriting.guardrail_evidence_id
        or price_implied.captured_at > underwriting.captured_at
    ):
        return False
    if price_implied is not None and not price_implied_sources_are_canonical(
        artifact_root,
        snapshot=price_implied,
    ):
        return False

    epistemic = _load_optional(
        underwriting.epistemic_defense_snapshot_id,
        lambda snapshot_id: load_canonical_epistemic_package(artifact_root, snapshot_id),
    )
    if underwriting.epistemic_defense_snapshot_id is not None and epistemic is None:
        return False
    if epistemic is not None and (
        epistemic.thesis_snapshot_id != thesis.snapshot_id
        or epistemic.guardrail_evidence_id != underwriting.guardrail_evidence_id
        or epistemic.captured_at > underwriting.captured_at
        or not epistemic.required_contracts_present
    ):
        return False
    if epistemic is not None and not epistemic_package_sources_are_canonical(
        artifact_root,
        thesis=thesis,
        snapshot=epistemic,
    ):
        return False

    if underwriting.lane is UnderwritingLane.FAST:
        return _fast_lane_evidence_contract_matches(
            thesis,
            underwriting,
            context=context,
            graph=graph,
            expectations=expectations,
            price_implied=price_implied,
            epistemic=epistemic,
        )
    if underwriting.lane is not UnderwritingLane.DEEP:
        return False
    return _deep_lane_evidence_contract_matches(
        thesis,
        underwriting,
        payoff=payoff,
        context=context,
        graph=graph,
        expectations=expectations,
        forward_valuation=forward_valuation,
        price_implied=price_implied,
        epistemic=epistemic,
    )


def decision_gap_bound_sources_are_canonical(
    root: str | Path,
    *,
    view: DecisionViewSnapshot,
    gap: DecisionExpectationGapSnapshot,
) -> bool:
    """Rebuild a persisted expectation gap from its certified source snapshots."""

    artifact_root = Path(root)
    expectations = load_canonical_expectation_state(
        artifact_root,
        gap.expectation_state_snapshot_id,
    )
    if expectations is None:
        return False
    # No current persisted provider contract independently proves certified consensus.
    # Rebuilding gap arithmetic from the same self-declared ExpectationState would be
    # circular, so every consensus-dependent gap remains fail closed.  This applies to
    # Fast and Deep packages alike; it deliberately does not create a generic provider
    # authority or relabel current KIS evidence as certified.
    if gap.consensus_gaps:
        return False
    price_implied: PriceImpliedRequirementSnapshot | None = None
    if gap.price_implied_requirement_snapshot_id is not None:
        price_implied = load_canonical_price_implied(
            artifact_root,
            gap.price_implied_requirement_snapshot_id,
        )
        if price_implied is None:
            return False
    try:
        rebuilt = build_decision_expectation_gap(
            view,
            expectations,
            captured_at=gap.captured_at,
            evaluation_date=gap.evaluation_date,
            price_implied=price_implied,
            guardrails=load_decision_system_v21_guardrails(),
        )
    except (TypeError, ValueError):
        return False
    return bool(
        rebuilt.snapshot_id == gap.snapshot_id
        and rebuilt.payload_without_id() == gap.payload_without_id()
    )


def load_canonical_underwriting_context(
    root: Path,
    snapshot_id: str,
) -> UnderwritingContextSnapshot | None:
    envelope = _load_envelope(
        root,
        repository_name="underwriting_context",
        snapshot_id=snapshot_id,
        payload_name="underwriting_context.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        snapshot = UnderwritingContextSnapshot(
            captured_at=_datetime(payload, "captured_at"),
            evaluation_date=_date(payload, "evaluation_date"),
            thesis_snapshot_id=_text(payload, "thesis_snapshot_id"),
            security_id=_text(payload, "security_id"),
            transmission_evidence_refs=_text_tuple(payload, "transmission_evidence_refs"),
            opportunity_set_comparison_refs=_text_tuple(
                payload, "opportunity_set_comparison_refs"
            ),
            portfolio_overlap_evidence_refs=_text_tuple(
                payload, "portfolio_overlap_evidence_refs"
            ),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
            warnings=_text_tuple(payload, "warnings"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = {
        "schema_version": UNDERWRITER_SCHEMA_VERSION,
        "object_type": "underwriting_context",
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "immutable": True,
        "files": ["underwriting_context.json"],
        "thesis_snapshot_id": snapshot.thesis_snapshot_id,
        "security_id": snapshot.security_id,
    }
    return snapshot if _canonical_snapshot_matches(
        snapshot_id,
        payload,
        manifest,
        directory,
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        expected_manifest,
    ) else None


def load_canonical_expectation_state(
    root: Path,
    snapshot_id: str,
) -> ExpectationStateSnapshot | None:
    envelope = _load_envelope(
        root,
        repository_name="expectation_state",
        snapshot_id=snapshot_id,
        payload_name="expectations.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        observations_raw = _object_list(payload, "observations")
        observations = tuple(_expectation_observation(item) for item in observations_raw)
        payload_sources = _text_tuple(payload, "source_snapshot_ids")
        manifest_sources = _text_tuple(manifest, "source_snapshot_ids")
        if sorted(payload_sources) != sorted(manifest_sources):
            return None
        snapshot = ExpectationStateSnapshot(
            captured_at=_datetime(payload, "captured_at"),
            evaluation_date=_date(payload, "evaluation_date"),
            observations=observations,
            source_snapshot_ids=manifest_sources,
            warnings=_text_tuple(payload, "warnings"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = {
        "schema_version": EXPECTATION_STATE_SCHEMA_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "evaluation_date": snapshot.evaluation_date.isoformat(),
        "observation_count": len(snapshot.observations),
        "providers": sorted({item.provider_id for item in snapshot.observations}),
        "consensus_observation_count": sum(
            item.expectation_kind is ExpectationKind.MARKET_CONSENSUS
            for item in snapshot.observations
        ),
        "source_snapshot_ids": list(snapshot.source_snapshot_ids),
        "warnings": list(snapshot.warnings),
        "order_api_enabled": False,
        "files": ["expectations.json"],
    }
    return snapshot if _canonical_snapshot_matches(
        snapshot_id,
        payload,
        manifest,
        directory,
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        expected_manifest,
    ) else None


def load_canonical_forward_valuation(
    root: Path,
    snapshot_id: str,
) -> ForwardValuationStateSnapshot | None:
    envelope = _load_envelope(
        root,
        repository_name="forward_valuation",
        snapshot_id=snapshot_id,
        payload_name="forward_valuations.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        observations = tuple(
            _forward_valuation_observation(item)
            for item in _object_list(payload, "observations")
        )
        snapshot = ForwardValuationStateSnapshot(
            captured_at=_datetime(payload, "captured_at"),
            evaluation_date=_date(payload, "evaluation_date"),
            valuation_evidence_snapshot_id=_text(
                payload, "valuation_evidence_snapshot_id"
            ),
            expectation_state_snapshot_id=_text(
                payload, "expectation_state_snapshot_id"
            ),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
            observations=observations,
            warnings=_text_tuple(payload, "warnings"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = {
        "schema_version": FORWARD_VALUATION_SCHEMA_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "evaluation_date": snapshot.evaluation_date.isoformat(),
        "valuation_evidence_snapshot_id": snapshot.valuation_evidence_snapshot_id,
        "expectation_state_snapshot_id": snapshot.expectation_state_snapshot_id,
        "guardrail_evidence_id": snapshot.guardrail_evidence_id,
        "observation_count": len(snapshot.observations),
        "available_multiple_count": sum(
            item.status is ForwardValuationStatus.AVAILABLE
            for item in snapshot.observations
        ),
        "trailing_actual_substitution_enabled": False,
        "provider_aggregation_enabled": False,
        "fair_value_enabled": False,
        "target_price_enabled": False,
        "valuation_score_enabled": False,
        "order_api_enabled": False,
        "warnings": list(snapshot.warnings),
        "files": ["forward_valuations.json"],
    }
    return snapshot if _canonical_snapshot_matches(
        snapshot_id,
        payload,
        manifest,
        directory,
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        expected_manifest,
    ) else None


def load_canonical_price_implied(
    root: Path,
    snapshot_id: str,
) -> PriceImpliedRequirementSnapshot | None:
    envelope = _load_envelope(
        root,
        repository_name="price_implied_requirement",
        snapshot_id=snapshot_id,
        payload_name="price_implied_requirement.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        observations = tuple(
            _price_implied_observation(item)
            for item in _object_list(payload, "observations")
        )
        snapshot = PriceImpliedRequirementSnapshot(
            captured_at=_datetime(payload, "captured_at"),
            evaluation_date=_date(payload, "evaluation_date"),
            security_id=_text(payload, "security_id"),
            valuation_evidence_snapshot_id=_text(
                payload, "valuation_evidence_snapshot_id"
            ),
            reference_frame_snapshot_id=_text(payload, "reference_frame_snapshot_id"),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
            observations=observations,
            warnings=_text_tuple(payload, "warnings"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = {
        "schema_version": PRICE_IMPLIED_SCHEMA_VERSION,
        "object_type": "price_implied_requirement",
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "immutable": True,
        "market_expectation_claimed": False,
        "fair_value_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "automatic_execution_enabled": False,
        "files": ["price_implied_requirement.json"],
    }
    return snapshot if _canonical_snapshot_matches(
        snapshot_id,
        payload,
        manifest,
        directory,
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        expected_manifest,
    ) else None


def load_canonical_causal_graph(
    root: Path,
    snapshot_id: str,
) -> SemiconductorCausalGraphSnapshot | None:
    envelope = _load_envelope(
        root,
        repository_name="semiconductor_causal_graph",
        snapshot_id=snapshot_id,
        payload_name="causal_graph.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        nodes = tuple(_causal_node(item) for item in _object_list(payload, "nodes"))
        edges = tuple(_causal_edge(item) for item in _object_list(payload, "edges"))
        snapshot = SemiconductorCausalGraphSnapshot(
            graph_id=_text(payload, "graph_id"),
            snapshot_version=_integer(payload, "snapshot_version"),
            parent_snapshot_id=_optional_text(payload, "parent_snapshot_id"),
            captured_at=_datetime(payload, "captured_at"),
            evaluation_date=_text(payload, "evaluation_date"),
            security_id=_optional_text(payload, "security_id"),
            critical_state_variables=tuple(
                CriticalStateVariable(item)
                for item in _text_tuple(payload, "critical_state_variables")
            ),
            nodes=nodes,
            edges=edges,
            source_snapshot_ids=_text_tuple(payload, "source_snapshot_ids"),
            policy_evidence_id=_text(payload, "policy_evidence_id"),
            source_policy_evidence_id=_text(payload, "source_policy_evidence_id"),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
            warnings=_text_tuple(payload, "warnings"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = {
        "schema_version": CAUSAL_GRAPH_SCHEMA_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "evaluation_date": snapshot.evaluation_date,
        "sector": "semiconductor",
        "security_id": snapshot.security_id,
        "node_count": len(snapshot.nodes),
        "edge_count": len(snapshot.edges),
        "critical_state_count": len(snapshot.critical_state_variables),
        "policy_evidence_id": snapshot.policy_evidence_id,
        "source_policy_evidence_id": snapshot.source_policy_evidence_id,
        "guardrail_evidence_id": snapshot.guardrail_evidence_id,
        "dag_claimed": False,
        "forecast_generation_enabled": False,
        "decision_score_enabled": False,
        "investability_decision_enabled": False,
        "order_api_enabled": False,
        "files": ["causal_graph.json"],
    }
    return snapshot if _canonical_snapshot_matches(
        snapshot_id,
        payload,
        manifest,
        directory,
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        expected_manifest,
    ) else None


def load_canonical_epistemic_package(
    root: Path,
    snapshot_id: str,
) -> EpistemicDefensePackageSnapshot | None:
    envelope = _load_envelope(
        root,
        repository_name="epistemic_package",
        snapshot_id=snapshot_id,
        payload_name="epistemic_package.json",
    )
    if envelope is None:
        return None
    payload, manifest, directory = envelope
    try:
        snapshot = EpistemicDefensePackageSnapshot(
            captured_at=_datetime(payload, "captured_at"),
            thesis_snapshot_id=_text(payload, "thesis_snapshot_id"),
            counter_thesis_snapshot_id=_text(payload, "counter_thesis_snapshot_id"),
            blind_spot_snapshot_id=_text(payload, "blind_spot_snapshot_id"),
            guardrail_evidence_id=_text(payload, "guardrail_evidence_id"),
            required_contracts_present=_boolean(payload, "required_contracts_present"),
            high_materiality_counter_explanation_count=_integer(
                payload, "high_materiality_counter_explanation_count"
            ),
            high_materiality_unresolved_contradiction_count=_integer(
                payload, "high_materiality_unresolved_contradiction_count"
            ),
            uncovered_high_materiality_blind_spot_count=_integer(
                payload, "uncovered_high_materiality_blind_spot_count"
            ),
            blind_spot_promotion_candidate_count=_integer(
                payload, "blind_spot_promotion_candidate_count"
            ),
            research_flags=_text_tuple(payload, "research_flags"),
        )
    except (KeyError, TypeError, ValueError):
        return None
    expected_manifest = {
        "schema_version": EPISTEMIC_DEFENSE_SCHEMA_VERSION,
        "object_type": "epistemic_package",
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "immutable": True,
        "decision_score_enabled": False,
        "investability_decision_enabled": False,
        "automatic_execution_enabled": False,
        "files": ["epistemic_package.json"],
    }
    return snapshot if _canonical_snapshot_matches(
        snapshot_id,
        payload,
        manifest,
        directory,
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        expected_manifest,
    ) else None


def _fast_lane_evidence_contract_matches(
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    *,
    context: UnderwritingContextSnapshot,
    graph: SemiconductorCausalGraphSnapshot | None,
    expectations: ExpectationStateSnapshot | None,
    price_implied: PriceImpliedRequirementSnapshot | None,
    epistemic: EpistemicDefensePackageSnapshot | None,
) -> bool:
    active = load_decision_system_v21_guardrails()
    satisfied_map = {
        "why_now": bool(thesis.why_now.strip()),
        "catalyst": bool(thesis.catalysts),
        "transmission": bool(context.transmission_evidence_refs) or graph is not None,
        "expectation_or_priced_in_assessment": (
            expectations is not None
            and any(item.security_id == thesis.security_id for item in expectations.observations)
        )
        or (
            price_implied is not None
            and any(
                item.security_id == thesis.security_id
                and item.status is PriceImpliedRequirementStatus.AVAILABLE
                for item in price_implied.observations
            )
        ),
        "top_downside": bool(thesis.first_rejection_risk.strip()),
        "counter_thesis": epistemic is not None,
        "kill_condition": bool(thesis.kill_conditions),
        "position_uncertainty": thesis.uncertainty is not None,
    }
    required = tuple(active.fast_lane_required_elements)
    satisfied = tuple(item for item in required if satisfied_map.get(item, False))
    missing = tuple(item for item in required if not satisfied_map.get(item, False))
    if satisfied != tuple(underwriting.required_elements_satisfied):
        return False
    if missing != tuple(underwriting.required_elements_missing) or missing:
        return False
    expected_flags = _epistemic_flags(epistemic)
    return tuple(underwriting.flags) == expected_flags


def _deep_lane_evidence_contract_matches(
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    *,
    payoff: PayoffSurfaceSnapshot | None,
    context: UnderwritingContextSnapshot,
    graph: SemiconductorCausalGraphSnapshot | None,
    expectations: ExpectationStateSnapshot | None,
    forward_valuation: ForwardValuationStateSnapshot | None,
    price_implied: PriceImpliedRequirementSnapshot | None,
    epistemic: EpistemicDefensePackageSnapshot | None,
) -> bool:
    if (
        graph is None
        or expectations is None
        or forward_valuation is None
        or price_implied is None
        or epistemic is None
        or payoff is None
    ):
        return False
    if underwriting.payoff_surface_snapshot_id != payoff.snapshot_id:
        return False
    tournament = underwriting.forecast_tournament
    if not tournament.comparable:
        return False
    if not any(
        item.security_id == thesis.security_id
        and item.expectation_kind is ExpectationKind.MARKET_CONSENSUS
        and item.market_consensus_certified
        and item.metric.value == tournament.target_variable
        and item.target_period_end == tournament.target_date
        and item.unit == tournament.unit
        for item in expectations.observations
    ):
        return False
    if not any(
        item.security_id == thesis.security_id
        and item.status is ForwardValuationStatus.AVAILABLE
        for item in forward_valuation.observations
    ):
        return False
    if not any(
        item.security_id == thesis.security_id
        and item.status is PriceImpliedRequirementStatus.AVAILABLE
        for item in price_implied.observations
    ):
        return False
    if not (
        thesis.catalysts
        and thesis.kill_conditions
        and thesis.opportunity_set_refs
        and context.opportunity_set_comparison_refs
        and thesis.portfolio_overlap
        and context.portfolio_overlap_evidence_refs
    ):
        return False
    expected_flags = tuple(
        dict.fromkeys(
            tuple(tournament.flags)
            + _epistemic_flags(epistemic)
            + (("sector_level_causal_graph",) if graph.security_id is None else ())
        )
    )
    return tuple(underwriting.flags) == expected_flags


def _epistemic_flags(
    epistemic: EpistemicDefensePackageSnapshot | None,
) -> tuple[str, ...]:
    if epistemic is None:
        return ()
    flags = list(epistemic.research_flags)
    if epistemic.high_materiality_counter_explanation_count:
        flags.append("high_materiality_counter_explanation")
    if epistemic.high_materiality_unresolved_contradiction_count:
        flags.append("high_materiality_unresolved_contradiction")
    if epistemic.uncovered_high_materiality_blind_spot_count:
        flags.append("uncovered_high_materiality_blind_spot")
    if epistemic.blind_spot_promotion_candidate_count:
        flags.append("blind_spot_promotion_candidate")
    return tuple(dict.fromkeys(flags))


def _expectation_observation(
    payload: dict[str, object],
) -> CertifiedExpectationObservation:
    semantics_payload = _mapping(payload, "semantics")
    semantics = ExpectationSemantics(
        provider_id=_text(semantics_payload, "provider_id"),
        provider_semantics_certified=_boolean(
            semantics_payload, "provider_semantics_certified"
        ),
        target_period_semantics_certified=_boolean(
            semantics_payload, "target_period_semantics_certified"
        ),
        metric_semantics_certified=_boolean(
            semantics_payload, "metric_semantics_certified"
        ),
        aggregation_semantics_certified=_boolean(
            semantics_payload, "aggregation_semantics_certified"
        ),
        observation_timestamp_certified=_boolean(
            semantics_payload, "observation_timestamp_certified"
        ),
        provider_vintage_certified=_boolean(
            semantics_payload, "provider_vintage_certified"
        ),
        comparable_prior_snapshot_available=_boolean(
            semantics_payload, "comparable_prior_snapshot_available"
        ),
        comparable_snapshot_scope_certified=_boolean(
            semantics_payload, "comparable_snapshot_scope_certified"
        ),
        revision_calculation_certified=_boolean(
            semantics_payload, "revision_calculation_certified"
        ),
        numeric_evidence_available=_boolean(
            semantics_payload, "numeric_evidence_available"
        ),
        source_scope=_text(semantics_payload, "source_scope"),
    )
    return CertifiedExpectationObservation(
        security_id=_text(payload, "security_id"),
        metric=ExpectationMetric(_text(payload, "metric")),
        target_period=_text(payload, "target_period"),
        target_period_end=_date(payload, "target_period_end"),
        expectation_kind=ExpectationKind(_text(payload, "expectation_kind")),
        value=_number(payload, "value"),
        unit=_text(payload, "unit"),
        observed_at=_datetime(payload, "observed_at"),
        source_evidence_id=_text(payload, "source_evidence_id"),
        semantics=semantics,
        market_consensus_certified=_boolean(
            payload, "market_consensus_certified"
        ),
        producer_identity=_optional_text(payload, "producer_identity"),
        aggregation_method=_optional_text(payload, "aggregation_method"),
        sample_count=_optional_integer(payload, "sample_count"),
        dispersion=_optional_number(payload, "dispersion"),
    )


def _forward_valuation_observation(
    payload: dict[str, object],
) -> ForwardValuationObservation:
    metric_raw = payload.get("valuation_metric")
    metric = None if metric_raw is None else ForwardValuationMetric(_text_value(metric_raw, "valuation_metric"))
    return ForwardValuationObservation(
        security_id=_text(payload, "security_id"),
        expectation_provider_id=_text(payload, "expectation_provider_id"),
        expectation_kind=ExpectationKind(_text(payload, "expectation_kind")),
        expectation_metric=ExpectationMetric(_text(payload, "expectation_metric")),
        target_period=_text(payload, "target_period"),
        target_period_end=_date(payload, "target_period_end"),
        expectation_observed_at=_datetime(payload, "expectation_observed_at"),
        expectation_source_evidence_id=_text(
            payload, "expectation_source_evidence_id"
        ),
        expectation_value=_number(payload, "expectation_value"),
        expectation_unit=_text(payload, "expectation_unit"),
        expectation_value_krw=_number(payload, "expectation_value_krw"),
        market_cap_krw=_optional_number(payload, "market_cap_krw"),
        valuation_metric=metric,
        multiple=_optional_number(payload, "multiple"),
        status=ForwardValuationStatus(_text(payload, "status")),
    )


def _price_implied_observation(
    payload: dict[str, object],
) -> PriceImpliedRequirementObservation:
    return PriceImpliedRequirementObservation(
        security_id=_text(payload, "security_id"),
        reference_id=_text(payload, "reference_id"),
        reference_kind=ReferenceFrameKind(_text(payload, "reference_kind")),
        valuation_metric=ForwardValuationMetric(_text(payload, "valuation_metric")),
        implied_metric=ExpectationMetric(_text(payload, "implied_metric")),
        target_period=_text(payload, "target_period"),
        target_period_end=_date(payload, "target_period_end"),
        reference_multiple=_number(payload, "reference_multiple"),
        market_cap_krw=_optional_number(payload, "market_cap_krw"),
        implied_value_krw=_optional_number(payload, "implied_value_krw"),
        status=PriceImpliedRequirementStatus(_text(payload, "status")),
    )


def _causal_node(payload: dict[str, object]) -> CausalNode:
    critical_raw = payload.get("critical_state_variable")
    status_raw = payload.get("current_state_epistemic_status")
    return CausalNode(
        node_id=_text(payload, "node_id"),
        label=_text(payload, "label"),
        node_type=CausalNodeType(_text(payload, "node_type")),
        description=_text(payload, "description"),
        critical_state_variable=(
            None
            if critical_raw is None
            else CriticalStateVariable(
                _text_value(critical_raw, "critical_state_variable")
            )
        ),
        current_state_statement=_optional_text(payload, "current_state_statement"),
        current_state_epistemic_status=(
            None
            if status_raw is None
            else EpistemicStatus(
                _text_value(status_raw, "current_state_epistemic_status")
            )
        ),
        evidence_refs=_text_tuple(payload, "evidence_refs"),
        opposing_evidence_refs=_text_tuple(payload, "opposing_evidence_refs"),
    )


def _causal_edge(payload: dict[str, object]) -> CausalEdge:
    lag_payload = _mapping(payload, "lag")
    lag = TransmissionLag(
        minimum_days=_optional_integer(lag_payload, "minimum_days"),
        maximum_days=_optional_integer(lag_payload, "maximum_days"),
        condition=_optional_text(lag_payload, "condition"),
    )
    return CausalEdge(
        edge_id=_text(payload, "edge_id"),
        source_node_id=_text(payload, "source_node_id"),
        target_node_id=_text(payload, "target_node_id"),
        mechanism=_text(payload, "mechanism"),
        epistemic_status=EpistemicStatus(_text(payload, "epistemic_status")),
        direction=CausalEdgeDirection(_text(payload, "direction")),
        lag=lag,
        regime_applicability=_text_tuple(payload, "regime_applicability"),
        evidence_refs=_text_tuple(payload, "evidence_refs"),
        opposing_evidence_refs=_text_tuple(payload, "opposing_evidence_refs"),
        falsifier=_text(payload, "falsifier"),
    )


def _load_optional(snapshot_id: str | None, loader):  # type: ignore[no-untyped-def]
    return None if snapshot_id is None else loader(snapshot_id)


def _load_envelope(
    root: Path,
    *,
    repository_name: str,
    snapshot_id: str,
    payload_name: str,
) -> tuple[dict[str, object], dict[str, object], Path] | None:
    try:
        resolved_root = require_trusted_artifact_root(root)
        repository = root / repository_name
        if repository.is_symlink():
            return None
        if not repository.exists() or not repository.is_dir():
            return None
        resolved_repository = repository.resolve(strict=True)
        if resolved_repository.parent != resolved_root:
            return None
        matches = tuple(
            path
            for path in repository.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and not path.name.startswith(".")
            and path.name.endswith(f"__{snapshot_id[:12]}")
        )
        if len(matches) != 1:
            return None
        directory = matches[0]
        if directory.resolve(strict=True).parent != resolved_repository:
            return None
        payload_path = directory / payload_name
        manifest_path = directory / "manifest.json"
        for path in (payload_path, manifest_path):
            if path.is_symlink() or not path.is_file():
                return None
            if path.resolve(strict=True).parent != directory.resolve(strict=True):
                return None
        payload = _read_json(payload_path)
        manifest = _read_json(manifest_path)
    except (OSError, ValueError):
        return None
    return payload, manifest, directory


def _canonical_snapshot_matches(
    expected_snapshot_id: str,
    payload: dict[str, object],
    manifest: dict[str, object],
    directory: Path,
    reconstructed_snapshot_id: str,
    captured_at: datetime,
    canonical_payload: dict[str, object],
    canonical_manifest: dict[str, object],
) -> bool:
    expected_directory_name = (
        captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + f"__{expected_snapshot_id[:12]}"
    )
    return bool(
        reconstructed_snapshot_id == expected_snapshot_id
        and canonical_payload == payload
        and canonical_manifest == manifest
        and directory.name == expected_directory_name
    )


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def _mapping(payload: dict[str, object], field: str) -> dict[str, object]:
    raw = payload[field]
    if not isinstance(raw, dict):
        raise ValueError(f"{field} must be an object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _object_list(payload: dict[str, object], field: str) -> tuple[dict[str, object], ...]:
    raw = payload[field]
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be a list")
    result: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{field} entries must be objects")
        result.append(
            {str(key): value for key, value in cast(dict[object, object], item).items()}
        )
    return tuple(result)


def _text(payload: dict[str, object], field: str) -> str:
    return _text_value(payload[field], field)


def _text_value(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} must be non-empty text")
    return raw


def _optional_text(payload: dict[str, object], field: str) -> str | None:
    raw = payload[field]
    if raw is None:
        return None
    return _text_value(raw, field)


def _text_tuple(payload: dict[str, object], field: str) -> tuple[str, ...]:
    raw = payload[field]
    if not isinstance(raw, list):
        raise ValueError(f"{field} must be a list")
    return tuple(_text_value(item, field) for item in raw)


def _boolean(payload: dict[str, object], field: str) -> bool:
    raw = payload[field]
    if not isinstance(raw, bool):
        raise ValueError(f"{field} must be boolean")
    return raw


def _integer(payload: dict[str, object], field: str) -> int:
    raw = payload[field]
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{field} must be an integer")
    return raw


def _optional_integer(payload: dict[str, object], field: str) -> int | None:
    raw = payload[field]
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise ValueError(f"{field} must be an integer or null")
    return raw


def _number(payload: dict[str, object], field: str) -> float:
    raw = payload[field]
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"{field} must be numeric")
    return float(raw)


def _optional_number(payload: dict[str, object], field: str) -> float | None:
    raw = payload[field]
    if raw is None:
        return None
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        raise ValueError(f"{field} must be numeric or null")
    return float(raw)


def _datetime(payload: dict[str, object], field: str) -> datetime:
    value = datetime.fromisoformat(_text(payload, field))
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def _date(payload: dict[str, object], field: str) -> date:
    return date.fromisoformat(_text(payload, field))


__all__ = [
    "CanonicalResearchEvidenceError",
    "decision_gap_bound_sources_are_canonical",
    "load_canonical_causal_graph",
    "load_canonical_epistemic_package",
    "load_canonical_expectation_state",
    "load_canonical_forward_valuation",
    "load_canonical_price_implied",
    "load_canonical_underwriting_context",
    "underwriting_bound_evidence_is_valid",
]
