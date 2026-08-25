from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import alpha_cycle.research_package_assembler_v2_1 as assembler
from alpha_cycle.intelligence.decision_view_v2_1 import DecisionViewSnapshot
from alpha_cycle.intelligence.epistemic_defense import (
    EpistemicDefensePackageSnapshot,
    persist_epistemic_defense_package,
)
from alpha_cycle.intelligence.expectation_gap_contract import ExpectationSemantics
from alpha_cycle.intelligence.expectation_state import (
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
    persist_expectation_state,
)
from alpha_cycle.intelligence.forecast_ledger import ForecasterKind
from alpha_cycle.intelligence.forward_valuation import ForwardValuationMetric
from alpha_cycle.intelligence.price_implied_requirement import (
    PriceImpliedRequirementObservation,
    PriceImpliedRequirementSnapshot,
    PriceImpliedRequirementStatus,
    ReferenceFrameKind,
    persist_price_implied_requirement,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    SUPPLEMENTAL_DEEP_ELEMENTS,
    ForecastTournamentAssessment,
    UnderwritingContextSnapshot,
    UnderwritingLane,
    UnderwritingReadiness,
    UnderwritingReadinessSnapshot,
    assess_forecast_tournament,
    persist_underwriting_context,
)
from alpha_cycle.research_package_canonical_evidence_v2_1 import (
    decision_gap_bound_sources_are_canonical,
    load_canonical_underwriting_context,
    underwriting_bound_evidence_is_valid,
)

NOW = datetime(2026, 8, 24, 4, 0, tzinfo=UTC)
EVAL = date(2026, 8, 24)
TARGET = date(2026, 12, 31)
A = "a" * 64
B = "b" * 64
C = "c" * 64


def _guardrail() -> str:
    return assembler.load_decision_system_v21_guardrails().evidence_id


def _semantics() -> ExpectationSemantics:
    return ExpectationSemantics(
        provider_id="provider-a",
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
        source_scope="merge-gate-fixture",
    )


def _expectation_state() -> ExpectationStateSnapshot:
    observation = CertifiedExpectationObservation(
        security_id="000660",
        metric=ExpectationMetric.NET_INCOME,
        target_period="2026",
        target_period_end=TARGET,
        expectation_kind=ExpectationKind.MARKET_CONSENSUS,
        value=18_000_000.0,
        unit="KRW_million",
        observed_at=NOW - timedelta(hours=1),
        source_evidence_id=A,
        semantics=_semantics(),
        market_consensus_certified=True,
        aggregation_method="fixture-median",
        sample_count=3,
    )
    return ExpectationStateSnapshot(
        captured_at=NOW,
        evaluation_date=EVAL,
        observations=(observation,),
        source_snapshot_ids=(A,),
    )


def _price_implied() -> PriceImpliedRequirementSnapshot:
    observation = PriceImpliedRequirementObservation(
        security_id="000660",
        reference_id="fixture-reference",
        reference_kind=ReferenceFrameKind.EXPLICIT_SCENARIO_ASSUMPTION,
        valuation_metric=ForwardValuationMetric.FORWARD_PE,
        implied_metric=ExpectationMetric.NET_INCOME,
        target_period="2026",
        target_period_end=TARGET,
        reference_multiple=10.0,
        market_cap_krw=180_000_000_000_000.0,
        implied_value_krw=18_000_000_000_000.0,
        status=PriceImpliedRequirementStatus.AVAILABLE,
    )
    return PriceImpliedRequirementSnapshot(
        captured_at=NOW,
        evaluation_date=EVAL,
        security_id="000660",
        valuation_evidence_snapshot_id=B,
        reference_frame_snapshot_id=C,
        guardrail_evidence_id=_guardrail(),
        observations=(observation,),
    )


def _context(thesis_snapshot_id: str) -> UnderwritingContextSnapshot:
    return UnderwritingContextSnapshot(
        captured_at=NOW,
        evaluation_date=EVAL,
        thesis_snapshot_id=thesis_snapshot_id,
        security_id="000660",
        transmission_evidence_refs=(A,),
        opportunity_set_comparison_refs=(B,),
        portfolio_overlap_evidence_refs=(C,),
        guardrail_evidence_id=_guardrail(),
    )


def _epistemic(thesis_snapshot_id: str) -> EpistemicDefensePackageSnapshot:
    return EpistemicDefensePackageSnapshot(
        captured_at=NOW,
        thesis_snapshot_id=thesis_snapshot_id,
        counter_thesis_snapshot_id=B,
        blind_spot_snapshot_id=C,
        guardrail_evidence_id=_guardrail(),
        required_contracts_present=True,
        high_materiality_counter_explanation_count=0,
        high_materiality_unresolved_contradiction_count=0,
        uncovered_high_materiality_blind_spot_count=0,
        blind_spot_promotion_candidate_count=0,
        research_flags=(),
    )


def test_deep_ready_rejects_unsubstantiated_bound_artifact(tmp_path: Path) -> None:
    context = _context(A)
    persist_underwriting_context(context, output_root=tmp_path)
    active = assembler.load_decision_system_v21_guardrails()
    tournament = ForecastTournamentAssessment(
        comparable=True,
        forecast_snapshot_ids=(B, C),
        forecast_ids=("forecast-a", "forecast-b"),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        primary_error_metric="absolute_error",
        distinct_forecaster_count=2,
        dependency_cluster_count=2,
        blockers=(),
        flags=(),
    )
    underwriting = UnderwritingReadinessSnapshot(
        captured_at=NOW + timedelta(minutes=1),
        evaluation_date=EVAL,
        thesis_snapshot_id=A,
        security_id="000660",
        lane=UnderwritingLane.DEEP,
        readiness=UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
        guardrail_evidence_id=active.evidence_id,
        context_snapshot_id=context.snapshot_id,
        causal_graph_snapshot_id=B,
        forecast_tournament=tournament,
        expectation_state_snapshot_id=C,
        forward_valuation_snapshot_id=A,
        price_implied_requirement_snapshot_id=B,
        payoff_surface_snapshot_id=C,
        epistemic_defense_snapshot_id=A,
        required_elements_satisfied=(
            active.deep_lane_required_elements + SUPPLEMENTAL_DEEP_ELEMENTS
        ),
        required_elements_missing=(),
        blockers=(),
        flags=(),
    )
    thesis = SimpleNamespace(snapshot_id=A, security_id="000660")
    payoff = SimpleNamespace(snapshot_id=C)

    assert not underwriting_bound_evidence_is_valid(
        tmp_path,
        thesis=thesis,  # type: ignore[arg-type]
        underwriting=underwriting,
        payoff=payoff,  # type: ignore[arg-type]
    )


def test_canonical_context_rejects_unknown_self_hashed_field(tmp_path: Path) -> None:
    context = _context(A)
    pointer = persist_underwriting_context(context, output_root=tmp_path)
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    directory = Path(pointer_payload["snapshot_path"])
    payload_path = directory / "underwriting_context.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["unknown_field"] = "fabricated-but-self-hashed"
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    forged_id = hashlib.sha256(encoded).hexdigest()
    payload_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot_id"] = forged_id
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    forged_directory = directory.with_name(
        directory.name.rsplit("__", 1)[0] + f"__{forged_id[:12]}"
    )
    directory.rename(forged_directory)

    assert load_canonical_underwriting_context(tmp_path, forged_id) is None


def test_fast_ready_recomputes_thesis_derived_requirements(tmp_path: Path) -> None:
    context = _context(A)
    price = _price_implied()
    epistemic = _epistemic(A)
    persist_underwriting_context(context, output_root=tmp_path)
    persist_price_implied_requirement(price, output_root=tmp_path)
    persist_epistemic_defense_package(epistemic, output_root=tmp_path)
    active = assembler.load_decision_system_v21_guardrails()
    underwriting = UnderwritingReadinessSnapshot(
        captured_at=NOW + timedelta(minutes=1),
        evaluation_date=EVAL,
        thesis_snapshot_id=A,
        security_id="000660",
        lane=UnderwritingLane.FAST,
        readiness=UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW,
        guardrail_evidence_id=active.evidence_id,
        context_snapshot_id=context.snapshot_id,
        causal_graph_snapshot_id=None,
        forecast_tournament=assess_forecast_tournament(
            (),
            thesis_security_id="000660",
            evaluation_date=EVAL,
        ),
        expectation_state_snapshot_id=None,
        forward_valuation_snapshot_id=None,
        price_implied_requirement_snapshot_id=price.snapshot_id,
        payoff_surface_snapshot_id=None,
        epistemic_defense_snapshot_id=epistemic.snapshot_id,
        required_elements_satisfied=tuple(active.fast_lane_required_elements),
        required_elements_missing=(),
        blockers=(),
        flags=(),
    )
    thesis = SimpleNamespace(
        snapshot_id=A,
        security_id="000660",
        why_now="Why now remains present.",
        catalysts=(),
        first_rejection_risk="Downside remains explicit.",
        kill_conditions=("kill",),
        uncertainty=object(),
    )

    assert not underwriting_bound_evidence_is_valid(
        tmp_path,
        thesis=thesis,  # type: ignore[arg-type]
        underwriting=underwriting,
        payoff=None,
    )


def test_gap_must_rebuild_from_bound_expectation_state(tmp_path: Path) -> None:
    expectations = _expectation_state()
    persist_expectation_state(expectations, output_root=tmp_path / "expectation_state")
    view = DecisionViewSnapshot(
        captured_at=NOW + timedelta(minutes=1),
        evaluation_date=EVAL,
        selection_rule_snapshot_id=A,
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecast_snapshot_id=B,
        selected_forecast_id="forecast-a",
        selected_forecaster_kind=ForecasterKind.MODEL,
        selected_model_family="fixture-model",
        selected_forecast_value=20_000_000.0,
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        tournament_forecast_snapshot_ids=(B, C),
        tournament_dependency_overlap=False,
        guardrail_evidence_id=_guardrail(),
    )
    from alpha_cycle.intelligence.decision_view_v2_1 import build_decision_expectation_gap

    canonical_gap = build_decision_expectation_gap(
        view,
        expectations,
        captured_at=NOW + timedelta(minutes=2),
        evaluation_date=EVAL,
    )
    forged_observation = replace(
        canonical_gap.consensus_gaps[0],
        consensus_value=17_000_000.0,
        absolute_gap=3_000_000.0,
        relative_gap=3_000_000.0 / 17_000_000.0,
    )
    forged_gap = replace(canonical_gap, consensus_gaps=(forged_observation,))

    assert not decision_gap_bound_sources_are_canonical(
        tmp_path,
        view=view,
        gap=forged_gap,
    )


def test_existing_pointer_cas_preserves_concurrent_replacement(tmp_path: Path) -> None:
    root = tmp_path / "opportunity_candidate"
    root.mkdir()
    pointer = root / "latest_opportunity_candidate.json"
    old = b"old-pointer\n"
    pointer.write_bytes(old)
    expected_identity = assembler._capture_file_identity(pointer)
    replacement = assembler._write_owned_pointer_temp(
        root,
        pointer.name,
        b"our-new-pointer\n",
    )
    foreign = root / ".foreign-pointer.tmp"
    foreign.write_bytes(b"concurrent-pointer\n")
    foreign.replace(pointer)
    try:
        assert not assembler._replace_pointer_if_version_matches(
            replacement,
            pointer,
            expected_bytes=old,
            expected_identity=expected_identity,
        )
        assert pointer.read_bytes() == b"concurrent-pointer\n"
    finally:
        replacement.unlink(missing_ok=True)


def test_owned_file_rollback_preserves_foreign_replacement(tmp_path: Path) -> None:
    path = tmp_path / "research-round.json"
    path.write_bytes(b"our-publication\n")
    publication = assembler._capture_owned_file(path)
    foreign = tmp_path / ".foreign-round.tmp"
    foreign.write_bytes(b"foreign-publication\n")
    foreign.replace(path)

    assert not assembler._unlink_owned_file_if_current(publication)
    assert path.read_bytes() == b"foreign-publication\n"
