"""Evidence manifest for Product R1 acceptance.

This adapter is deliberately read-only.  It binds acceptance evidence to an
already validated point-in-time snapshot; it does not promote provider data or
invent source authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from alpha_cycle.intelligence.observable_universe import (
    EvidenceMaturity,
    ObservableUniverseSnapshot,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    return value.astimezone(UTC)


def _content_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class R1SourceAuthorityManifest:
    """Validated evidence boundary consumed by an R1 acceptance report."""

    snapshot_id: str
    research_cutoff_at: datetime
    required_reference_ids: tuple[str, ...]
    authenticated_reference_ids: tuple[str, ...]
    authority_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.snapshot_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.snapshot_id
        ):
            raise ValueError("snapshot_id must be a lowercase SHA-256 id")
        object.__setattr__(self, "research_cutoff_at", _utc(self.research_cutoff_at))
        for name, values in (
            ("required_reference_ids", self.required_reference_ids),
            ("authenticated_reference_ids", self.authenticated_reference_ids),
            ("authority_ids", self.authority_ids),
        ):
            if tuple(sorted(set(values))) != values or any(not value for value in values):
                raise ValueError(f"{name} must be non-empty and canonical")
        if not self.required_reference_ids:
            raise ValueError("required_reference_ids cannot be empty")
        if not set(self.authenticated_reference_ids) <= set(self.required_reference_ids):
            raise ValueError("authenticated references must be required references")

    @property
    def real_pit_evidence(self) -> bool:
        return bool(self.required_reference_ids)

    @property
    def source_authority_established(self) -> bool:
        return (
            bool(self.authority_ids)
            and set(self.authenticated_reference_ids) == set(self.required_reference_ids)
        )

    def payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "research_cutoff_at": self.research_cutoff_at.isoformat(),
            "required_reference_ids": list(self.required_reference_ids),
            "authenticated_reference_ids": list(self.authenticated_reference_ids),
            "authority_ids": list(self.authority_ids),
        }

    @property
    def content_id(self) -> str:
        return _content_id(self.payload())


def build_r1_source_authority_manifest(
    snapshot: ObservableUniverseSnapshot,
    *,
    research_cutoff_at: datetime,
    authenticated_reference_ids: tuple[str, ...] = (),
    authority_ids: tuple[str, ...] = (),
) -> R1SourceAuthorityManifest:
    """Bind a manifest to exact snapshot identity, cutoff, and evidence refs."""

    cutoff = _utc(research_cutoff_at)
    if snapshot.research_cutoff_at != cutoff:
        raise ValueError("acceptance cutoff must exactly match snapshot cutoff")
    refs = tuple(sorted(snapshot.source_evidence_refs))
    authenticated = tuple(sorted(authenticated_reference_ids))
    if not set(authenticated) <= set(refs):
        raise ValueError("authenticated references must exist in the snapshot")
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
    if any(reference_id not in evidence_by_id for reference_id in authenticated):
        raise ValueError("authenticated references must have snapshot definitions")
    if any(
        evidence_by_id[reference_id].maturity
        is not EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY
        for reference_id in authenticated
    ):
        raise ValueError("authenticated references require independently validated authority")
    return R1SourceAuthorityManifest(
        snapshot_id=snapshot.snapshot_id,
        research_cutoff_at=cutoff,
        required_reference_ids=refs,
        authenticated_reference_ids=authenticated,
        authority_ids=tuple(sorted(authority_ids)),
    )


__all__ = ["R1SourceAuthorityManifest", "build_r1_source_authority_manifest"]
