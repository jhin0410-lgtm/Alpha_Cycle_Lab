"""Synthetic trust-boundary regressions, not real provider acceptance receipts."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_observable_universe import snapshot
from test_r1_opendart_observations import selection
from test_r1_opendart_reconciliation import reconcile, setup_source
from test_valuation_authority_v2_1 import CAPTURED

import alpha_cycle.intelligence.r1_opendart_reconciliation as official
from alpha_cycle.intelligence.observable_universe import (
    EvidenceMaturity,
    ObservableUniverseSnapshot,
)
from alpha_cycle.intelligence.r1_opendart_observations import load_opendart_universe
from alpha_cycle.intelligence.r1_opendart_reconciliation import OpenDartFieldReconciliation
from alpha_cycle.intelligence.r1_source_authority_v1 import (
    AuthorityArtifact,
    PITReplayBinding,
    R1SourceAuthorityManifest,
    build_opendart_source_authority_manifest,
    build_r1_source_authority_manifest,
)
from alpha_cycle.live_typed_source_manifest_v2_1 import freeze_live_typed_source_manifest


def authoritative_snapshot() -> ObservableUniverseSnapshot:
    base = snapshot()
    observation = base.observations[0]
    reference = replace(
        observation.evidence[0], maturity=EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY
    )
    return ObservableUniverseSnapshot(
        universe_id=base.universe_id,
        version=base.version,
        research_cutoff_at=base.research_cutoff_at,
        members=base.members,
        observations=(replace(observation, evidence=(reference,)),),
        source_evidence_refs=(reference.reference_id,),
    )


def binding(snapshot_value: ObservableUniverseSnapshot) -> PITReplayBinding:
    return PITReplayBinding(
        provider_id="market_writer",
        provider_snapshot_id="provider-snapshot-1",
        replay_manifest_id="a" * 64,
        cutoff_at=snapshot_value.research_cutoff_at,
        validation_method="independent_provider_replay",
    )


def artifact(snapshot_value: ObservableUniverseSnapshot, replay_id: str) -> AuthorityArtifact:
    reference = snapshot_value.observations[0].evidence[0]
    return AuthorityArtifact(
        provider_id=reference.source,
        evidence_reference_id=reference.reference_id,
        semantic_authority=reference.semantic_authority,
        claim_semantics="adjusted_close_return",
        period_or_window=reference.reference_id.rsplit("-", 1)[-1],
        cutoff_at=snapshot_value.research_cutoff_at,
        validation_method="independent_provider_replay",
        provenance_identity="b" * 64,
        replay_binding_id=replay_id,
    )


def test_caller_asserted_maturity_and_artifacts_do_not_establish_authority() -> None:
    current = authoritative_snapshot()
    pit = binding(current)
    authority = artifact(current, pit.binding_id)
    manifest = build_r1_source_authority_manifest(
        current,
        pit_binding=pit,
        decision_critical_reference_ids=(current.source_evidence_refs[0],),
        authority_artifacts=(authority,),
    )
    assert not manifest.real_pit_evidence
    assert not manifest.source_authority_established
    assert not pit.replay_verified
    assert not pit.source_origin_verified
    assert len(manifest.content_id) == 64


def test_manifest_rejects_wrong_cutoff_or_non_authority_maturity() -> None:
    current = snapshot()
    pit = binding(current)
    with pytest.raises(ValueError, match="independent maturity"):
        build_r1_source_authority_manifest(
            current,
            pit_binding=pit,
            decision_critical_reference_ids=(current.source_evidence_refs[0],),
            authority_artifacts=(artifact(current, pit.binding_id),),
        )
    with pytest.raises(ValueError, match="exactly match"):
        build_r1_source_authority_manifest(
            current,
            pit_binding=replace(pit, cutoff_at=datetime(2026, 8, 2, tzinfo=UTC)),
            decision_critical_reference_ids=(current.source_evidence_refs[0],),
            authority_artifacts=(),
        )


def test_synthetic_source_bytes_replay_never_authenticates_origin(tmp_path: Path) -> None:
    source = tmp_path / "market"
    source.mkdir()
    (source / "data.json").write_text('{"price": 1}', encoding="utf-8")
    (source / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshot_id": "c" * 64,
                "captured_at": "2026-08-01T00:00:00+00:00",
                "files": ["data.json"],
            }
        ),
        encoding="utf-8",
    )
    replay = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": source},
        evaluation_date=datetime(2026, 8, 1, tzinfo=UTC).date(),
        research_cutoff_at=datetime(2026, 8, 1, tzinfo=UTC),
        frozen_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    verified = PITReplayBinding.from_verified_source_manifest(
        replay,
        artifact_root=tmp_path,
        provider_id="opendart",
        provider_snapshot_id="c" * 64,
    )
    assert verified.replay_verified
    assert verified.validation_method == "source_bytes_replay"
    assert not verified.source_origin_verified
    assert not replace(verified).replay_verified
    assert not copy.copy(verified).replay_verified
    current = authoritative_snapshot()
    manifest = build_r1_source_authority_manifest(
        current, pit_binding=verified,
        decision_critical_reference_ids=current.source_evidence_refs,
        authority_artifacts=(artifact(current, verified.binding_id),),
    )
    assert not manifest.real_pit_evidence
    assert not manifest.source_authority_established
    with pytest.raises(ValueError, match="not selected"):
        PITReplayBinding.from_verified_source_manifest(
            replay, artifact_root=tmp_path, provider_id="opendart",
            provider_snapshot_id="provider-snapshot-1",
        )
    object.__setattr__(verified, "provider_snapshot_id", "d" * 64)
    assert not verified.replay_verified


def issued_inputs(
    tmp_path: Path,
) -> tuple[ObservableUniverseSnapshot, OpenDartFieldReconciliation]:
    source, directory = setup_source(tmp_path)
    report = reconcile(directory, source.raw_opendart, at=CAPTURED + timedelta(seconds=1))
    # Exercise issuance consumption with synthetic data only. No provider was
    # contacted, and this fixture must never serve as a real acceptance receipt.
    official._LIVE_VERIFICATIONS[report] = report.content_id
    universe = load_opendart_universe(
        directory, selections=(selection(),), universe_id="synthetic-authority", version="1",
        cutoff_at=CAPTURED + timedelta(seconds=2),
    )
    return universe, report


def issued_manifest(
    universe: ObservableUniverseSnapshot, report: OpenDartFieldReconciliation,
) -> R1SourceAuthorityManifest:
    return build_opendart_source_authority_manifest(
        universe, report, decision_critical_reference_ids=universe.source_evidence_refs,
    )


def test_official_claim_factory_binds_exact_scope_without_promoting_observation(tmp_path: Path):
    universe, report = issued_inputs(tmp_path)
    original = universe.payload()
    manifest = issued_manifest(universe, report)
    assert manifest.real_pit_evidence
    assert manifest.source_authority_established
    assert manifest.snapshot_id == universe.snapshot_id
    assert manifest.research_cutoff_at == universe.research_cutoff_at
    assert manifest.pit_binding.replay_verified
    assert manifest.pit_binding.source_origin_verified
    assert manifest.pit_binding.provider_snapshot_id == report.source_snapshot_id
    assert manifest.pit_binding.replay_manifest_id == report.content_id
    claim = manifest.authority_artifacts[0]
    assert claim.provider_id == "opendart"
    assert claim.security_id == selection().security_id
    assert claim.metric_id == selection().metric_id
    assert claim.statement_basis == "CFS"
    assert claim.source_field == "thstrm_amount"
    assert claim.period_or_window == "FY:2025-12-31:thstrm_amount"
    assert claim.cutoff_at == report.verified_at
    assert universe.payload() == original
    assert universe.observations[0].maturity is EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE


def test_copy_replace_and_same_content_nested_replacement_lose_issuance(tmp_path: Path):
    universe, report = issued_inputs(tmp_path)
    manifest = issued_manifest(universe, report)
    for copied in (copy.copy(manifest), copy.deepcopy(manifest), replace(manifest)):
        assert copied.content_id == manifest.content_id
        assert not copied.real_pit_evidence
        assert not copied.source_authority_established
    pit = manifest.pit_binding
    for copied_pit in (copy.copy(pit), copy.deepcopy(pit), replace(pit)):
        assert copied_pit.binding_id == pit.binding_id
        assert not copied_pit.replay_verified
        assert not copied_pit.source_origin_verified
    object.__setattr__(manifest, "pit_binding", replace(pit))
    assert not manifest.real_pit_evidence
    assert not manifest.source_authority_established


@pytest.mark.parametrize("target", ["manifest", "pit", "artifact", "report"])
def test_nested_mutation_revokes_live_authority(tmp_path: Path, target: str):
    universe, report = issued_inputs(tmp_path)
    manifest = issued_manifest(universe, report)
    assert manifest.source_authority_established
    if target == "manifest":
        object.__setattr__(manifest, "snapshot_id", "e" * 64)
    elif target == "pit":
        object.__setattr__(manifest.pit_binding, "provider_id", "other-provider")
        assert not manifest.pit_binding.replay_verified
        assert not manifest.pit_binding.source_origin_verified
    elif target == "artifact":
        object.__setattr__(manifest.authority_artifacts[0], "security_id", "005930")
    else:
        object.__setattr__(report, "verified_at", report.verified_at + timedelta(seconds=1))
        assert not manifest.pit_binding.source_origin_verified
    assert not manifest.real_pit_evidence
    assert not manifest.source_authority_established


def test_lower_maturity_context_is_retained_without_claim_promotion(tmp_path: Path):
    universe, report = issued_inputs(tmp_path)
    observed = universe.observations[0]
    reference = replace(
        observed.evidence[0], reference_id="synthetic-context", source="cited-research",
        maturity=EvidenceMaturity.CITED_CONTEXT, semantic_authority="context_only",
    )
    context = replace(
        observed, dimension_id="research_context", metric_id="context_note", value="uncertain",
        maturity=EvidenceMaturity.CITED_CONTEXT, evidence=(reference,),
    )
    member = replace(
        universe.members[0],
        available_dimensions=(*universe.members[0].available_dimensions, context.dimension_id),
    )
    broader = replace(
        universe, members=(member,), observations=(*universe.observations, context),
        source_evidence_refs=(*universe.source_evidence_refs, reference.reference_id),
    )
    manifest = build_opendart_source_authority_manifest(
        broader, report, decision_critical_reference_ids=universe.source_evidence_refs,
        research_context_reference_ids=(reference.reference_id,),
    )
    assert manifest.source_authority_established
    assert manifest.snapshot_id == broader.snapshot_id
    assert manifest.research_context_reference_ids == (reference.reference_id,)
    assert len(manifest.authority_artifacts) == 1
    assert manifest.authority_artifacts[0].evidence_reference_id != reference.reference_id
    assert context.maturity is EvidenceMaturity.CITED_CONTEXT
    with pytest.raises(ValueError, match="subset of verified claims"):
        build_opendart_source_authority_manifest(
            broader, report, decision_critical_reference_ids=(reference.reference_id,),
        )


def test_factory_rejects_unissued_report_and_backdated_cutoff(tmp_path: Path):
    universe, report = issued_inputs(tmp_path)
    with pytest.raises(ValueError, match="fresh official"):
        issued_manifest(universe, replace(report))
    with pytest.raises(ValueError, match="exceeds"):
        issued_manifest(replace(universe, research_cutoff_at=CAPTURED), report)


@pytest.mark.parametrize("field,value", [
    ("value", 1), ("metric_id", "future_eps"), ("basis", "OFS"),
    ("window", "H1:2025-12-31:thstrm_amount"),
    ("semantics", "forecast_annual_profit"),
])
def test_factory_rejects_changed_claim_scope(tmp_path: Path, field: str, value):
    universe, report = issued_inputs(tmp_path)
    changed = replace(universe.observations[0], **{field: value})
    with pytest.raises(ValueError, match="exactly cover"):
        issued_manifest(replace(universe, observations=(changed,)), report)


def test_factory_rejects_unknown_duplicate_or_overlapping_references(tmp_path: Path):
    universe, report = issued_inputs(tmp_path)
    refs = universe.source_evidence_refs
    with pytest.raises(ValueError, match="nonempty subset"):
        build_opendart_source_authority_manifest(
            universe, report, decision_critical_reference_ids=(),
        )
    with pytest.raises(ValueError, match="canonical"):
        build_opendart_source_authority_manifest(
            universe, report, decision_critical_reference_ids=refs + refs,
        )
    with pytest.raises(ValueError, match="cannot overlap"):
        build_opendart_source_authority_manifest(
            universe, report, decision_critical_reference_ids=refs,
            research_context_reference_ids=refs,
        )
    # A loose top-level reference is not actual evidence defined in the universe.
    loose = replace(universe, source_evidence_refs=(*refs, "undefined-context"))
    with pytest.raises(ValueError, match="defined by the snapshot"):
        build_opendart_source_authority_manifest(
            loose, report, decision_critical_reference_ids=refs,
            research_context_reference_ids=("undefined-context",),
        )
