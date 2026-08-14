"""Source-bounded structural semiconductor evidence.

Structural evidence covers HBM demand/mix, capacity/yield/packaging, customer
qualification, competitive position, end-demand, memory-pricing direction, and
export-control policy.  It is intentionally separate from numeric memory-price
series: issuer/peer commentary may support a qualitative pricing claim but can
never be promoted into a numeric DRAM/NAND/HBM price signal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast
from urllib.parse import urlparse

import yaml

_ALLOWED_ROLES = frozenset(
    {"issuer_ir", "peer_ir", "customer_ir", "government_regulation", "certified_price_data"}
)
_ALLOWED_KINDS = frozenset({"qualitative", "numeric"})


@dataclass(frozen=True)
class SemiconductorStructuralSource:
    source_id: str
    owner: str
    role: str
    primary_source: bool
    domains: tuple[str, ...]
    allowed_dimensions: tuple[str, ...]
    numeric_memory_price_eligible: bool = False
    requires_semantics_certification: bool = False
    requires_unit_and_product_scope: bool = False
    requires_license_or_public_reuse_basis: bool = False

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.owner.strip():
            raise ValueError("Structural source id/owner cannot be blank")
        if self.role not in _ALLOWED_ROLES:
            raise ValueError(f"Unsupported structural source role: {self.role}")
        if not self.allowed_dimensions:
            raise ValueError("Structural source requires allowed dimensions")
        if self.numeric_memory_price_eligible and self.role != "certified_price_data":
            raise ValueError("Only certified price data may be numeric-memory-price eligible")


@dataclass(frozen=True)
class SemiconductorStructuralClaim:
    claim_id: str
    subject: str
    dimension: str
    as_of_date: date
    source_id: str
    source_url: str
    source_published_date: date
    evidence_kind: str
    statement: str
    numeric_value: float | None = None
    unit: str | None = None
    product_scope: str | None = None
    semantics_certified: bool = False
    reuse_basis_documented: bool = False
    issuer_specific: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.claim_id) != 64 or any(char not in "0123456789abcdef" for char in self.claim_id):
            raise ValueError("Structural claim_id must be SHA-256")
        if not self.subject.strip() or not self.dimension.strip() or not self.statement.strip():
            raise ValueError("Structural claim subject/dimension/statement cannot be blank")
        if self.evidence_kind not in _ALLOWED_KINDS:
            raise ValueError(f"Unsupported structural evidence kind: {self.evidence_kind}")
        if self.source_published_date > self.as_of_date:
            raise ValueError("Structural claim cannot use a source published after as_of_date")
        if self.evidence_kind == "numeric" and self.numeric_value is None:
            raise ValueError("Numeric structural evidence requires numeric_value")
        if self.evidence_kind == "qualitative" and self.numeric_value is not None:
            raise ValueError("Qualitative structural evidence cannot publish numeric_value")
        if self.decision_score_enabled:
            raise ValueError("Structural evidence must remain non-scoring")


@dataclass(frozen=True)
class SemiconductorStructuralEvidenceBundle:
    bundle_id: str
    evaluation_date: date
    claims: tuple[SemiconductorStructuralClaim, ...]
    numeric_memory_price_signal_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.bundle_id) != 64 or any(char not in "0123456789abcdef" for char in self.bundle_id):
            raise ValueError("Structural bundle_id must be SHA-256")
        if not self.claims:
            raise ValueError("Structural evidence bundle requires at least one claim")
        if any(claim.as_of_date != self.evaluation_date for claim in self.claims):
            raise ValueError("Structural claims must share the bundle evaluation date")
        if self.decision_score_enabled:
            raise ValueError("Structural evidence bundle must remain non-scoring")
        if self.numeric_memory_price_signal_enabled:
            raise ValueError("Numeric memory-price signal is not enabled by structural evidence")


def load_structural_source_registry(
    path: str | Path,
) -> dict[str, SemiconductorStructuralSource]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), dict):
        raise ValueError("Structural source registry must contain sources")
    result: dict[str, SemiconductorStructuralSource] = {}
    for raw_id, raw_value in cast(dict[object, object], payload["sources"]).items():
        source_id = str(raw_id).strip()
        if not isinstance(raw_value, dict):
            raise ValueError(f"Structural source entry must be an object: {source_id}")
        raw = cast(dict[object, object], raw_value)
        result[source_id] = SemiconductorStructuralSource(
            source_id=source_id,
            owner=str(raw.get("owner", "")).strip(),
            role=str(raw.get("role", "")).strip(),
            primary_source=bool(raw.get("primary_source", False)),
            domains=tuple(str(value).strip().casefold() for value in raw.get("domains", []) if str(value).strip()),
            allowed_dimensions=tuple(str(value).strip() for value in raw.get("allowed_dimensions", []) if str(value).strip()),
            numeric_memory_price_eligible=bool(raw.get("numeric_memory_price_eligible", False)),
            requires_semantics_certification=bool(raw.get("requires_semantics_certification", False)),
            requires_unit_and_product_scope=bool(raw.get("requires_unit_and_product_scope", False)),
            requires_license_or_public_reuse_basis=bool(raw.get("requires_license_or_public_reuse_basis", False)),
        )
    if not result:
        raise ValueError("Structural source registry is empty")
    return result


def _host_allowed(source: SemiconductorStructuralSource, url: str) -> bool:
    if source.role == "certified_price_data" and not source.domains:
        return True
    host = (urlparse(url).hostname or "").casefold()
    return any(host == domain or host.endswith("." + domain) for domain in source.domains)


def _claim_id(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def validate_structural_claim(
    raw: dict[str, object],
    registry: dict[str, SemiconductorStructuralSource],
    *,
    evaluation_date: date,
) -> SemiconductorStructuralClaim:
    source_id = str(raw.get("source_id", "")).strip()
    if source_id not in registry:
        raise ValueError(f"Unknown semiconductor structural source: {source_id}")
    source = registry[source_id]
    dimension = str(raw.get("dimension", "")).strip()
    if dimension not in source.allowed_dimensions:
        raise ValueError(f"Source {source_id} cannot support dimension {dimension}")
    source_url = str(raw.get("source_url", "")).strip()
    if not source_url.startswith("https://") or not _host_allowed(source, source_url):
        raise ValueError(f"Structural source URL is outside registered domains: {source_id}")
    published = date.fromisoformat(str(raw.get("source_published_date", "")))
    kind = str(raw.get("evidence_kind", "qualitative")).strip()
    numeric_raw = raw.get("numeric_value")
    numeric_value = None if numeric_raw is None else float(str(numeric_raw))
    unit = str(raw.get("unit", "")).strip() or None
    product_scope = str(raw.get("product_scope", "")).strip() or None
    semantics_certified = bool(raw.get("semantics_certified", False))
    reuse_basis = bool(raw.get("reuse_basis_documented", False))

    if dimension == "memory_numeric_price":
        if not source.numeric_memory_price_eligible:
            raise ValueError("Company/customer/government commentary cannot become numeric memory price")
        if kind != "numeric":
            raise ValueError("memory_numeric_price requires numeric evidence")
        if source.requires_semantics_certification and not semantics_certified:
            raise ValueError("Numeric memory price requires certified provider semantics")
        if source.requires_unit_and_product_scope and (not unit or not product_scope):
            raise ValueError("Numeric memory price requires unit and product_scope")
        if source.requires_license_or_public_reuse_basis and not reuse_basis:
            raise ValueError("Numeric memory price requires documented reuse/license basis")
    elif kind == "numeric" and not source.primary_source:
        raise ValueError("Non-primary structural numeric evidence is only allowed for certified price data")

    payload = {
        "subject": str(raw.get("subject", "")).strip(),
        "dimension": dimension,
        "as_of_date": evaluation_date.isoformat(),
        "source_id": source_id,
        "source_url": source_url,
        "source_published_date": published.isoformat(),
        "evidence_kind": kind,
        "statement": str(raw.get("statement", "")).strip(),
        "numeric_value": numeric_value,
        "unit": unit,
        "product_scope": product_scope,
        "semantics_certified": semantics_certified,
        "reuse_basis_documented": reuse_basis,
        "issuer_specific": bool(raw.get("issuer_specific", False)),
        "decision_score_enabled": False,
    }
    return SemiconductorStructuralClaim(claim_id=_claim_id(payload), **payload)  # type: ignore[arg-type]


def build_structural_evidence_bundle(
    raw_claims: list[dict[str, object]],
    registry: dict[str, SemiconductorStructuralSource],
    *,
    evaluation_date: date,
) -> SemiconductorStructuralEvidenceBundle:
    claims = tuple(
        validate_structural_claim(raw, registry, evaluation_date=evaluation_date)
        for raw in raw_claims
    )
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise ValueError("Structural evidence bundle contains duplicate claims")
    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "claims": [
            {
                "claim_id": claim.claim_id,
                "subject": claim.subject,
                "dimension": claim.dimension,
                "source_id": claim.source_id,
                "source_url": claim.source_url,
                "source_published_date": claim.source_published_date.isoformat(),
                "evidence_kind": claim.evidence_kind,
                "numeric_value": claim.numeric_value,
                "unit": claim.unit,
                "product_scope": claim.product_scope,
                "semantics_certified": claim.semantics_certified,
                "reuse_basis_documented": claim.reuse_basis_documented,
                "issuer_specific": claim.issuer_specific,
            }
            for claim in claims
        ],
        "numeric_memory_price_signal_enabled": False,
        "decision_score_enabled": False,
    }
    bundle_id = _claim_id(payload)
    return SemiconductorStructuralEvidenceBundle(
        bundle_id=bundle_id,
        evaluation_date=evaluation_date,
        claims=claims,
        numeric_memory_price_signal_enabled=False,
        decision_score_enabled=False,
    )


__all__ = [
    "SemiconductorStructuralClaim",
    "SemiconductorStructuralEvidenceBundle",
    "SemiconductorStructuralSource",
    "build_structural_evidence_bundle",
    "load_structural_source_registry",
    "validate_structural_claim",
]
