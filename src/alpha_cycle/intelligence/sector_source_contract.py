"""Validate sector-specific primary-source evidence claims.

The shared contract validates provenance and semantics but does not homogenize
sector economics. Each sector registry determines which source role may support
which dimension and which generic proxies are prohibited. Issuer IR entries have
no global domain because domains must be bound explicitly per covered issuer.
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


@dataclass(frozen=True)
class SectorPrimarySource:
    source_id: str
    owner: str
    role: str
    domains: tuple[str, ...]
    dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.owner.strip() or not self.role.strip():
            raise ValueError("Sector primary source identity cannot be blank")
        if not self.dimensions:
            raise ValueError("Sector primary source requires supported dimensions")


@dataclass(frozen=True)
class SectorSourceDefinition:
    sector_id: str
    sources: tuple[SectorPrimarySource, ...]
    prohibited_generic_proxies: tuple[str, ...] = ()
    certified_or_licensed_required: tuple[str, ...] = ()
    event_probability_requires: tuple[str, ...] = ()
    delegates_to: str | None = None

    def __post_init__(self) -> None:
        if not self.sector_id.strip():
            raise ValueError("Sector source definition sector_id cannot be blank")
        if not self.sources and self.delegates_to is None:
            raise ValueError("Sector source definition requires sources or delegate")
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError(f"Sector source definition repeats source_id: {self.sector_id}")


@dataclass(frozen=True)
class SectorEvidenceClaim:
    claim_id: str
    sector_id: str
    subject: str
    dimension: str
    source_id: str
    source_role: str
    source_url: str
    source_published_date: date
    evaluation_date: date
    statement: str
    issuer_specific: bool
    semantics_certified: bool
    license_or_reuse_basis_documented: bool
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.claim_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.claim_id
        ):
            raise ValueError("Sector evidence claim_id must be SHA-256")
        if not all(
            value.strip()
            for value in (
                self.sector_id,
                self.subject,
                self.dimension,
                self.source_id,
                self.source_role,
                self.source_url,
                self.statement,
            )
        ):
            raise ValueError("Sector evidence claim fields cannot be blank")
        if self.source_published_date > self.evaluation_date:
            raise ValueError("Sector evidence cannot use a future-published source")
        if self.decision_score_enabled:
            raise ValueError("Sector source contract evidence must remain non-scoring")


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"Sector source {field} must be an array")
    return tuple(str(item).strip() for item in value if str(item).strip())


def load_sector_source_registry(path: str | Path) -> dict[str, SectorSourceDefinition]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("sectors"), dict):
        raise ValueError("Sector primary-source registry must contain sectors")
    definitions: dict[str, SectorSourceDefinition] = {}
    for raw_sector, raw_value in cast(dict[object, object], payload["sectors"]).items():
        sector_id = str(raw_sector).strip()
        if not isinstance(raw_value, dict):
            raise ValueError(f"Sector source entry must be an object: {sector_id}")
        raw = cast(dict[object, object], raw_value)
        delegate = str(raw.get("delegates_to", "")).strip() or None
        raw_sources = raw.get("sources", {})
        if not isinstance(raw_sources, dict):
            raise ValueError(f"Sector sources must be an object: {sector_id}")
        sources: list[SectorPrimarySource] = []
        for raw_source_id, raw_source_value in cast(
            dict[object, object], raw_sources
        ).items():
            source_id = str(raw_source_id).strip()
            if not isinstance(raw_source_value, dict):
                raise ValueError(f"Sector source must be an object: {sector_id}/{source_id}")
            source_raw = cast(dict[object, object], raw_source_value)
            sources.append(
                SectorPrimarySource(
                    source_id=source_id,
                    owner=str(source_raw.get("owner", "")).strip(),
                    role=str(source_raw.get("role", "")).strip(),
                    domains=tuple(
                        str(item).strip().casefold()
                        for item in _string_tuple(source_raw.get("domains", []), "domains")
                    ),
                    dimensions=_string_tuple(
                        source_raw.get("dimensions", []), "dimensions"
                    ),
                )
            )
        definitions[sector_id] = SectorSourceDefinition(
            sector_id=sector_id,
            sources=tuple(sources),
            prohibited_generic_proxies=_string_tuple(
                raw.get("prohibited_generic_proxies", []),
                "prohibited_generic_proxies",
            ),
            certified_or_licensed_required=_string_tuple(
                raw.get("certified_or_licensed_required", []),
                "certified_or_licensed_required",
            ),
            event_probability_requires=_string_tuple(
                raw.get("event_probability_requires", []),
                "event_probability_requires",
            ),
            delegates_to=delegate,
        )
    if not definitions:
        raise ValueError("Sector primary-source registry is empty")
    return definitions


def _host_matches(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return bool(host) and any(host == domain or host.endswith("." + domain) for domain in domains)


def _claim_id(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def validate_sector_evidence_claim(
    raw: dict[str, object],
    registry: dict[str, SectorSourceDefinition],
    *,
    evaluation_date: date,
    issuer_domains: dict[str, tuple[str, ...]] | None = None,
) -> SectorEvidenceClaim:
    sector_id = str(raw.get("sector_id", "")).strip()
    if sector_id not in registry:
        raise ValueError(f"Sector source contract is not registered: {sector_id}")
    definition = registry[sector_id]
    if definition.delegates_to is not None:
        raise ValueError(
            f"Sector {sector_id} delegates to a dedicated evidence contract: {definition.delegates_to}"
        )
    source_id = str(raw.get("source_id", "")).strip()
    source_lookup = {source.source_id: source for source in definition.sources}
    if source_id not in source_lookup:
        raise ValueError(f"Unknown sector source: {sector_id}/{source_id}")
    source = source_lookup[source_id]
    dimension = str(raw.get("dimension", "")).strip()
    if dimension not in source.dimensions:
        raise ValueError(f"Source {sector_id}/{source_id} cannot support dimension {dimension}")
    source_url = str(raw.get("source_url", "")).strip()
    if not source_url.startswith("https://"):
        raise ValueError("Sector source URL must use HTTPS")
    allowed_domains = source.domains
    if source.role == "issuer_ir" and not allowed_domains:
        subject = str(raw.get("subject", "")).strip()
        bindings = issuer_domains or {}
        allowed_domains = bindings.get(subject, ())
        if not allowed_domains:
            raise ValueError(
                f"Issuer IR requires explicit domain binding for subject {subject}"
            )
    if not _host_matches(source_url, allowed_domains):
        raise ValueError(f"Sector source URL is outside registered domains: {sector_id}/{source_id}")

    semantics_certified = bool(raw.get("semantics_certified", False))
    reuse_documented = bool(raw.get("license_or_reuse_basis_documented", False))
    if dimension in definition.certified_or_licensed_required:
        if not semantics_certified or not reuse_documented:
            raise ValueError(
                f"Sector dimension requires certified semantics and reuse/license basis: {dimension}"
            )

    published = date.fromisoformat(str(raw.get("source_published_date", "")))
    subject = str(raw.get("subject", "")).strip()
    statement = str(raw.get("statement", "")).strip()
    payload: dict[str, object] = {
        "sector_id": sector_id,
        "subject": subject,
        "dimension": dimension,
        "source_id": source_id,
        "source_role": source.role,
        "source_url": source_url,
        "source_published_date": published.isoformat(),
        "evaluation_date": evaluation_date.isoformat(),
        "statement": statement,
        "issuer_specific": bool(raw.get("issuer_specific", source.role == "issuer_ir")),
        "semantics_certified": semantics_certified,
        "license_or_reuse_basis_documented": reuse_documented,
        "decision_score_enabled": False,
    }
    return SectorEvidenceClaim(
        claim_id=_claim_id(payload),
        sector_id=sector_id,
        subject=subject,
        dimension=dimension,
        source_id=source_id,
        source_role=source.role,
        source_url=source_url,
        source_published_date=published,
        evaluation_date=evaluation_date,
        statement=statement,
        issuer_specific=bool(payload["issuer_specific"]),
        semantics_certified=semantics_certified,
        license_or_reuse_basis_documented=reuse_documented,
        decision_score_enabled=False,
    )


def prohibited_proxy_rules(
    registry: dict[str, SectorSourceDefinition],
) -> dict[str, tuple[str, ...]]:
    return {
        sector_id: definition.prohibited_generic_proxies
        for sector_id, definition in registry.items()
        if definition.prohibited_generic_proxies
    }


__all__ = [
    "SectorEvidenceClaim",
    "SectorPrimarySource",
    "SectorSourceDefinition",
    "load_sector_source_registry",
    "prohibited_proxy_rules",
    "validate_sector_evidence_claim",
]
