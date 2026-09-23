"""Claim-specific, replay-bound evidence for Product R1 acceptance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from weakref import WeakKeyDictionary

from alpha_cycle.intelligence.observable_universe import (
    EvidenceMaturity,
    ObservableUniverseSnapshot,
)
from alpha_cycle.intelligence.r1_opendart_reconciliation import (
    OpenDartFieldReconciliation,
    require_reconciled_universe,
)
from alpha_cycle.live_typed_source_manifest_v2_1 import (
    LiveTypedSourceManifest,
    verify_live_typed_source_manifest,
)

_VALIDATION_METHODS = frozenset({
    "official_filing_reconciliation", "independent_provider_replay", "source_bytes_replay",
})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _sha(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 id")


def _content_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, eq=False)
class PITReplayBinding:
    provider_id: str
    provider_snapshot_id: str
    replay_manifest_id: str
    cutoff_at: datetime
    validation_method: str

    def __post_init__(self) -> None:
        if not self.provider_id or not self.provider_snapshot_id:
            raise ValueError("PIT binding requires provider and snapshot identities")
        _sha(self.replay_manifest_id, "replay_manifest_id")
        object.__setattr__(self, "cutoff_at", _utc(self.cutoff_at))
        if self.validation_method not in _VALIDATION_METHODS:
            raise ValueError("unsupported PIT validation method")

    @classmethod
    def from_verified_source_manifest(
        cls,
        manifest: LiveTypedSourceManifest,
        *,
        artifact_root: str | Path,
        provider_id: str,
        provider_snapshot_id: str,
    ) -> PITReplayBinding:
        """Bind replayed bytes, without authenticating their remote origin.

        ``provider_id`` remains a caller's descriptive label on this generic
        path. A source-specific live verifier is required for real authority.
        """

        verify_live_typed_source_manifest(manifest, artifact_root=artifact_root)
        if provider_snapshot_id not in {source.snapshot_id for source in manifest.sources}:
            raise ValueError("provider snapshot is not selected by the source manifest")
        binding = cls(
            provider_id=provider_id,
            provider_snapshot_id=provider_snapshot_id,
            replay_manifest_id=manifest.manifest_id,
            cutoff_at=manifest.research_cutoff_at,
            validation_method="source_bytes_replay",
        )
        _REPLAY_BINDINGS[binding] = binding.binding_id
        return binding

    @property
    def replay_verified(self) -> bool:
        return _REPLAY_BINDINGS.get(self) == self.binding_id

    @property
    def source_origin_verified(self) -> bool:
        issued = _LIVE_BINDINGS.get(self)
        return bool(
            issued is not None and issued[0] == self.binding_id
            and issued[1].fresh_official_verification
            and self.replay_manifest_id == issued[1].content_id
            and self.provider_snapshot_id == issued[1].source_snapshot_id
            and self.replay_verified
        )

    def payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "provider_snapshot_id": self.provider_snapshot_id,
            "replay_manifest_id": self.replay_manifest_id,
            "cutoff_at": self.cutoff_at.isoformat(),
            "validation_method": self.validation_method,
        }

    @property
    def binding_id(self) -> str:
        return _content_id(self.payload())


@dataclass(frozen=True)
class AuthorityArtifact:
    provider_id: str
    evidence_reference_id: str
    semantic_authority: str
    claim_semantics: str
    period_or_window: str
    cutoff_at: datetime
    validation_method: str
    provenance_identity: str
    replay_binding_id: str
    security_id: str | None = None
    metric_id: str | None = None
    statement_basis: str | None = None
    source_field: str | None = None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.provider_id, "provider_id"),
            (self.evidence_reference_id, "evidence_reference_id"),
            (self.semantic_authority, "semantic_authority"),
            (self.claim_semantics, "claim_semantics"),
            (self.period_or_window, "period_or_window"),
        ):
            if not value:
                raise ValueError(f"{field_name} cannot be empty")
        _sha(self.provenance_identity, "provenance_identity")
        _sha(self.replay_binding_id, "replay_binding_id")
        object.__setattr__(self, "cutoff_at", _utc(self.cutoff_at))
        if self.validation_method not in _VALIDATION_METHODS:
            raise ValueError("unsupported authority validation method")
        if any(value is not None and not value.strip() for value in (
            self.security_id, self.metric_id, self.statement_basis, self.source_field,
        )):
            raise ValueError("supplied authority claim scope cannot be empty")

    def payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "evidence_reference_id": self.evidence_reference_id,
            "semantic_authority": self.semantic_authority,
            "claim_semantics": self.claim_semantics,
            "period_or_window": self.period_or_window,
            "cutoff_at": self.cutoff_at.isoformat(),
            "validation_method": self.validation_method,
            "provenance_identity": self.provenance_identity,
            "replay_binding_id": self.replay_binding_id,
            "security_id": self.security_id,
            "metric_id": self.metric_id,
            "statement_basis": self.statement_basis,
            "source_field": self.source_field,
        }

    @property
    def artifact_id(self) -> str:
        return _content_id(self.payload())


@dataclass(frozen=True, eq=False)
class R1SourceAuthorityManifest:
    snapshot_id: str
    research_cutoff_at: datetime
    pit_binding: PITReplayBinding
    decision_critical_reference_ids: tuple[str, ...]
    research_context_reference_ids: tuple[str, ...]
    authority_artifacts: tuple[AuthorityArtifact, ...]

    def __post_init__(self) -> None:
        _sha(self.snapshot_id, "snapshot_id")
        object.__setattr__(self, "research_cutoff_at", _utc(self.research_cutoff_at))
        if self.pit_binding.cutoff_at != self.research_cutoff_at:
            raise ValueError("PIT binding cutoff must match acceptance cutoff")
        for name, values in (
            ("decision_critical_reference_ids", self.decision_critical_reference_ids),
            ("research_context_reference_ids", self.research_context_reference_ids),
        ):
            if tuple(sorted(set(values))) != values or any(not value for value in values):
                raise ValueError(f"{name} must be canonical")
        artifact_ids = tuple(item.artifact_id for item in self.authority_artifacts)
        if artifact_ids != tuple(sorted(set(artifact_ids))):
            raise ValueError("authority artifacts must be unique and canonical")
        covered = tuple(sorted(item.evidence_reference_id for item in self.authority_artifacts))
        if covered != self.decision_critical_reference_ids:
            raise ValueError("authority artifacts must cover exactly decision-critical refs")
        if set(self.decision_critical_reference_ids) & set(self.research_context_reference_ids):
            raise ValueError("decision-critical and context references cannot overlap")
        if any(item.replay_binding_id != self.pit_binding.binding_id
               for item in self.authority_artifacts):
            raise ValueError("authority artifact must bind the exact PIT binding")

    @property
    def real_pit_evidence(self) -> bool:
        return self._has_live_issuance

    @property
    def source_authority_established(self) -> bool:
        return self._has_live_issuance

    @property
    def _has_live_issuance(self) -> bool:
        issued = _LIVE_MANIFESTS.get(self)
        return bool(
            issued is not None and issued[0] == self.content_id
            and issued[1].fresh_official_verification
            and self.pit_binding is issued[2]
            and self.pit_binding.source_origin_verified
            and self.decision_critical_reference_ids
            and all(item.cutoff_at <= self.research_cutoff_at
                    for item in self.authority_artifacts)
        )

    def payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "research_cutoff_at": self.research_cutoff_at.isoformat(),
            "pit_binding": self.pit_binding.payload(),
            "decision_critical_reference_ids": list(self.decision_critical_reference_ids),
            "research_context_reference_ids": list(self.research_context_reference_ids),
            "authority_artifacts": [item.payload() for item in self.authority_artifacts],
        }

    @property
    def content_id(self) -> str:
        return _content_id(self.payload())


# Identity-keyed issuance plus a content digest prevents copy/replace or nested
# mutation from carrying a verifier's proof. Nothing in the serialized payload
# restores issuance, and no generic caller-supplied artifact receives it.
_REPLAY_BINDINGS: WeakKeyDictionary[PITReplayBinding, str] = WeakKeyDictionary()
_LIVE_BINDINGS: WeakKeyDictionary[
    PITReplayBinding, tuple[str, OpenDartFieldReconciliation]
] = WeakKeyDictionary()
_LIVE_MANIFESTS: WeakKeyDictionary[
    R1SourceAuthorityManifest, tuple[str, OpenDartFieldReconciliation, PITReplayBinding]
] = WeakKeyDictionary()


def build_r1_source_authority_manifest(
    snapshot: ObservableUniverseSnapshot,
    *,
    pit_binding: PITReplayBinding,
    decision_critical_reference_ids: tuple[str, ...],
    authority_artifacts: tuple[AuthorityArtifact, ...],
    research_context_reference_ids: tuple[str, ...] = (),
) -> R1SourceAuthorityManifest:
    """Describe caller claims without issuing real PIT or source authority."""
    if snapshot.research_cutoff_at != pit_binding.cutoff_at:
        raise ValueError("PIT binding cutoff must exactly match snapshot cutoff")
    available = set(snapshot.source_evidence_refs)
    decision_refs = tuple(sorted(decision_critical_reference_ids))
    context_refs = tuple(sorted(research_context_reference_ids))
    if not set(decision_refs) <= available or not set(context_refs) <= available:
        raise ValueError("manifest references must exist in the snapshot")
    evidence_by_id = {
        evidence.reference_id: evidence
        for observation in snapshot.observations
        for evidence in observation.evidence
    }
    evidence_by_id.update(
        {
            evidence.reference_id: evidence
            for member in snapshot.members
            for evidence in member.membership_evidence
        }
    )
    for artifact in authority_artifacts:
        evidence = evidence_by_id.get(artifact.evidence_reference_id)
        if evidence is None:
            raise ValueError("authority artifact reference is not defined by the snapshot")
        if evidence.maturity is not EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY:
            raise ValueError("decision-critical authority requires independent maturity")
        if artifact.provider_id != evidence.source:
            raise ValueError("authority provider does not match evidence source")
        if artifact.semantic_authority != evidence.semantic_authority:
            raise ValueError("authority semantic does not match evidence semantic authority")
    return R1SourceAuthorityManifest(
        snapshot_id=snapshot.snapshot_id,
        research_cutoff_at=pit_binding.cutoff_at,
        pit_binding=pit_binding,
        decision_critical_reference_ids=decision_refs,
        research_context_reference_ids=context_refs,
        authority_artifacts=tuple(sorted(authority_artifacts, key=lambda item: item.artifact_id)),
    )


def build_opendart_source_authority_manifest(
    snapshot: ObservableUniverseSnapshot,
    reconciliation: OpenDartFieldReconciliation,
    *,
    decision_critical_reference_ids: tuple[str, ...],
    research_context_reference_ids: tuple[str, ...] = (),
) -> R1SourceAuthorityManifest:
    """Bind exact official-reconciled fields, never blanket snapshot authority.

    Original observations retain their replay-only maturity. This separate
    coverage certificate is valid only for the selected field references, this
    exact research cutoff, and the live verifier's in-process issued result.
    Loading its JSON later cannot restore remote-origin authentication.
    """
    if not reconciliation.fresh_official_verification:
        raise ValueError("fresh official verification is required")
    claims = json.loads(reconciliation.claims_json)
    verified_refs = {item["evidence_reference_id"] for item in claims}
    decision_refs = tuple(sorted(decision_critical_reference_ids))
    context_refs = tuple(sorted(research_context_reference_ids))
    if not decision_refs or not set(decision_refs) <= verified_refs:
        raise ValueError("decision-critical refs must be a nonempty subset of verified claims")
    defined_refs = {
        ref.reference_id for observation in snapshot.observations for ref in observation.evidence
    } | {ref.reference_id for member in snapshot.members for ref in member.membership_evidence}
    if not set(context_refs) <= defined_refs:
        raise ValueError("context references must be defined by the snapshot")

    # The live reconciliation may cover just a selected source within a broader
    # universe. Project without altering any observation or evidence payload;
    # the verifier still requires exact claim identities and complete coverage.
    selected = tuple(item for item in snapshot.observations if any(
        ref.reference_id in verified_refs for ref in item.evidence
    ))
    dimensions = {
        member.member_id: tuple(item.dimension_id for item in selected
                                if item.member_id == member.member_id)
        for member in snapshot.members
    }
    projected = replace(
        snapshot, observations=selected,
        members=tuple(replace(
            member, required_dimensions=dimensions[member.member_id],
            available_dimensions=dimensions[member.member_id], unavailable_dimensions=(),
            membership_evidence=(),
        ) for member in snapshot.members if dimensions[member.member_id]),
        source_evidence_refs=tuple(sorted(verified_refs)),
    )
    require_reconciled_universe(reconciliation, projected)
    pit = PITReplayBinding(
        provider_id="opendart",
        provider_snapshot_id=reconciliation.source_snapshot_id,
        replay_manifest_id=reconciliation.content_id,
        cutoff_at=snapshot.research_cutoff_at,
        validation_method="official_filing_reconciliation",
    )
    artifacts = tuple(AuthorityArtifact(
        provider_id="opendart",
        evidence_reference_id=claim["evidence_reference_id"],
        semantic_authority="officially_reconciled_reported_current_term_field",
        claim_semantics=claim["semantics"],
        period_or_window=claim["window"],
        cutoff_at=reconciliation.verified_at,
        validation_method="official_filing_reconciliation",
        provenance_identity=_content_id({
            "reconciliation_id": reconciliation.content_id,
            "source_snapshot_id": reconciliation.source_snapshot_id,
            "claim": claim,
        }),
        replay_binding_id=pit.binding_id,
        security_id=claim["security_id"],
        metric_id=claim["metric_id"],
        statement_basis=claim["basis"],
        source_field="thstrm_amount",
    ) for claim in claims if claim["evidence_reference_id"] in decision_refs)
    manifest = R1SourceAuthorityManifest(
        snapshot_id=snapshot.snapshot_id,
        research_cutoff_at=snapshot.research_cutoff_at,
        pit_binding=pit,
        decision_critical_reference_ids=decision_refs,
        research_context_reference_ids=context_refs,
        authority_artifacts=tuple(sorted(artifacts, key=lambda item: item.artifact_id)),
    )
    _REPLAY_BINDINGS[pit] = pit.binding_id
    _LIVE_BINDINGS[pit] = (pit.binding_id, reconciliation)
    _LIVE_MANIFESTS[manifest] = (manifest.content_id, reconciliation, pit)
    return manifest


__all__ = [
    "AuthorityArtifact",
    "PITReplayBinding",
    "R1SourceAuthorityManifest",
    "build_opendart_source_authority_manifest",
    "build_r1_source_authority_manifest",
]
