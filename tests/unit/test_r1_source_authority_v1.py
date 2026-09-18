from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from test_observable_universe import snapshot

from alpha_cycle.intelligence.observable_universe import (
    EvidenceMaturity,
    ObservableUniverseSnapshot,
)
from alpha_cycle.intelligence.r1_source_authority_v1 import (
    AuthorityArtifact,
    PITReplayBinding,
    build_r1_source_authority_manifest,
)


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


def test_manifest_requires_claim_specific_authority_and_pit_binding() -> None:
    current = authoritative_snapshot()
    pit = binding(current)
    authority = artifact(current, pit.binding_id)
    manifest = build_r1_source_authority_manifest(
        current,
        pit_binding=pit,
        decision_critical_reference_ids=(current.source_evidence_refs[0],),
        authority_artifacts=(authority,),
    )
    assert manifest.real_pit_evidence
    assert manifest.source_authority_established
    assert len(manifest.content_id) == 64


def test_context_refs_need_not_be_independently_authoritative() -> None:
    current = authoritative_snapshot()
    pit = binding(current)
    authority = artifact(current, pit.binding_id)
    manifest = build_r1_source_authority_manifest(
        current,
        pit_binding=pit,
        decision_critical_reference_ids=(current.source_evidence_refs[0],),
        research_context_reference_ids=(),
        authority_artifacts=(authority,),
    )
    assert manifest.source_authority_established


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
