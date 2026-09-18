"""Claim-specific, replay-bound evidence for Product R1 acceptance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence.observable_universe import (
    EvidenceMaturity,
    ObservableUniverseSnapshot,
)
from alpha_cycle.live_typed_source_manifest_v2_1 import (
    LiveTypedSourceManifest,
    verify_live_typed_source_manifest,
)

_VALIDATION_METHODS = frozenset({"official_filing_reconciliation", "independent_provider_replay"})
_VERIFIED_TOKEN = object()


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


@dataclass(frozen=True)
class PITReplayBinding:
    provider_id: str
    provider_snapshot_id: str
    replay_manifest_id: str
    cutoff_at: datetime
    validation_method: str
    _verification_token: object = field(default=None, repr=False, compare=False)

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
        """Create a real PIT binding only after replaying persisted source bytes."""

        verify_live_typed_source_manifest(manifest, artifact_root=artifact_root)
        return cls(
            provider_id=provider_id,
            provider_snapshot_id=provider_snapshot_id,
            replay_manifest_id=manifest.manifest_id,
            cutoff_at=manifest.research_cutoff_at,
            validation_method="independent_provider_replay",
            _verification_token=_VERIFIED_TOKEN,
        )

    @property
    def replay_verified(self) -> bool:
        return self._verification_token is _VERIFIED_TOKEN

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
        }

    @property
    def artifact_id(self) -> str:
        return _content_id(self.payload())


@dataclass(frozen=True)
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

    @property
    def real_pit_evidence(self) -> bool:
        return bool(
            self.pit_binding.replay_verified
            and self.pit_binding.binding_id
            and self.decision_critical_reference_ids
        )

    @property
    def source_authority_established(self) -> bool:
        return bool(self.authority_artifacts) and all(
            item.cutoff_at <= self.research_cutoff_at for item in self.authority_artifacts
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


def build_r1_source_authority_manifest(
    snapshot: ObservableUniverseSnapshot,
    *,
    pit_binding: PITReplayBinding,
    decision_critical_reference_ids: tuple[str, ...],
    authority_artifacts: tuple[AuthorityArtifact, ...],
    research_context_reference_ids: tuple[str, ...] = (),
) -> R1SourceAuthorityManifest:
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


__all__ = [
    "AuthorityArtifact",
    "PITReplayBinding",
    "R1SourceAuthorityManifest",
    "build_r1_source_authority_manifest",
]
