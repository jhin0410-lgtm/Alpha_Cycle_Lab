"""Discover the exact SK hynix 2Q26 IR PDF from issuer-controlled web resources.

This module is intentionally a transport-discovery layer, not a generic web crawler. It
reads the official Earnings Release page, follows only issuer-controlled JavaScript assets
that the page explicitly references, and accepts only PDF URLs that are literally present
in those captured bytes. Numeric attachment IDs are never guessed or synthesized.

A PDF candidate is considered resolved only when it is hosted on the issuer site or the
known issuer CDN and its extracted content matches the pinned 2Q26 deck fingerprint. The
result remains research evidence until a separate checked-in registry PR activates the
normal official-IR collector.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import cast
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.official_semiconductor_ir_collector import extract_pdf_pages

SK_HYNIX_IR_EARNINGS_URL = "https://www.skhynix.com/ir/UI-FR-IR06/"
SK_HYNIX_OFFICIAL_CDN_HOST = "mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net"
DEFAULT_DISCOVERY_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-attachment-discovery"
)
DEFAULT_DISCOVERY_POINTER = DEFAULT_DISCOVERY_OUTPUT / "latest_skhynix_ir_attachment_discovery.json"
_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")
_MAX_SCRIPT_COUNT = 32
_MAX_SOURCE_BYTES = 8_000_000

_ABSOLUTE_PDF_URL = re.compile(
    r"https://[^\s\"'<>]+?\.pdf(?:\?[^\s\"'<>]*)?",
    flags=re.IGNORECASE,
)
_RELATIVE_ATTACH_PDF = re.compile(
    r"/web/attach/[0-9]+\.pdf(?:\?[^\s\"'<>]*)?",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ExplicitResource:
    source_label: str
    source_sha256: str
    url: str


@dataclass(frozen=True)
class OfficialIrPdfCandidate:
    url: str
    discovered_from: tuple[str, ...]
    pdf_sha256: str
    pdf_bytes: int
    page_count: int
    fingerprint_match: bool
    fingerprint_reason: str


@dataclass(frozen=True)
class OfficialIrAttachmentDiscoveryEvidence:
    evidence_id: str
    observed_date: date
    ir_page_sha256: str
    script_resources: tuple[ExplicitResource, ...]
    candidates: tuple[OfficialIrPdfCandidate, ...]
    resolved: bool
    resolved_url: str | None
    resolved_pdf_sha256: str | None
    discovery_only: bool = True
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.ir_page_sha256):
            raise ValueError("SK hynix IR attachment evidence hashes must be SHA-256")
        if self.resolved:
            if self.resolved_url is None or self.resolved_pdf_sha256 is None:
                raise ValueError("Resolved SK hynix IR attachment requires URL and PDF hash")
            matches = [item for item in self.candidates if item.fingerprint_match]
            if len(matches) != 1:
                raise ValueError("Resolved SK hynix IR attachment must have exactly one match")
            if matches[0].url != self.resolved_url:
                raise ValueError("Resolved SK hynix IR URL does not match candidate")
            if matches[0].pdf_sha256 != self.resolved_pdf_sha256:
                raise ValueError("Resolved SK hynix IR hash does not match candidate")
        elif self.resolved_url is not None or self.resolved_pdf_sha256 is not None:
            raise ValueError("Unresolved SK hynix IR attachment cannot expose resolved identity")
        if not self.discovery_only:
            raise ValueError("SK hynix IR attachment discovery must remain discovery-only")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SK hynix IR attachment discovery cannot widen model trust")


class _ResourceReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        for key, value in attrs:
            if value is None:
                continue
            if key.casefold() in {"href", "src", "data-src", "data-url", "data-href"}:
                self.references.append(value.strip())


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _issuer_controlled_host(host: str) -> bool:
    normalized = host.casefold()
    return (
        normalized == "skhynix.com"
        or normalized.endswith(".skhynix.com")
        or normalized == SK_HYNIX_OFFICIAL_CDN_HOST
    )


def _official_pdf_host(host: str) -> bool:
    normalized = host.casefold()
    return normalized in {
        "skhynix.com",
        "www.skhynix.com",
        SK_HYNIX_OFFICIAL_CDN_HOST,
    }


def _safe_script_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and _issuer_controlled_host(parsed.hostname or "")
        and parsed.path.casefold().endswith(".js")
    )


def _safe_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and _official_pdf_host(parsed.hostname or "")
        and parsed.path.casefold().endswith(".pdf")
    )


def _normalized_source_text(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return text.replace("\\/", "/")


def extract_explicit_pdf_urls(data: bytes, *, base_url: str) -> tuple[str, ...]:
    """Return only PDF URLs literally present in captured page/script bytes."""

    text = _normalized_source_text(data)
    discovered: set[str] = set()
    for match in _ABSOLUTE_PDF_URL.finditer(text):
        candidate = match.group(0).rstrip("),];}")
        if _safe_pdf_url(candidate):
            discovered.add(candidate)
    for match in _RELATIVE_ATTACH_PDF.finditer(text):
        candidate = urljoin(base_url, match.group(0).rstrip("),];}"))
        if _safe_pdf_url(candidate):
            discovered.add(candidate)
    return tuple(sorted(discovered))


def extract_explicit_script_urls(page_bytes: bytes) -> tuple[str, ...]:
    parser = _ResourceReferenceParser()
    parser.feed(page_bytes.decode("utf-8", errors="replace"))
    parser.close()
    discovered = {
        urljoin(SK_HYNIX_IR_EARNINGS_URL, item)
        for item in parser.references
        if item and item.casefold().split("?", 1)[0].endswith(".js")
    }
    return tuple(sorted(item for item in discovered if _safe_script_url(item)))


def download_issuer_resource(
    url: str,
    *,
    timeout_seconds: float = 20.0,
) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not _issuer_controlled_host(parsed.hostname or ""):
        raise ValueError("SK hynix IR discovery refuses a non-issuer-controlled resource")
    request = Request(
        url,
        headers={"User-Agent": "Alpha-Cycle-Lab/0.1 skhynix-ir-discovery-readonly"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        data = cast(bytes, response.read(_MAX_SOURCE_BYTES + 1))
    if len(data) > _MAX_SOURCE_BYTES:
        raise ValueError("SK hynix IR discovery resource exceeds the byte cap")
    return data


def _contains(text: str, anchor: str) -> bool:
    normalized_text = " ".join(text.split()).casefold()
    normalized_anchor = " ".join(anchor.split()).casefold()
    return normalized_anchor in normalized_text


def fingerprint_skhynix_2026q2_deck(pdf_bytes: bytes) -> tuple[bool, int, str]:
    """Verify source bytes against the observed company-authored 2Q26 deck semantics."""

    try:
        pages = extract_pdf_pages(pdf_bytes)
    except ValueError as exc:
        return False, 0, str(exc)
    if len(pages) != 19:
        return False, len(pages), f"expected 19 pages, found {len(pages)}"
    whole = "\n".join(pages)
    required = (
        "2026.07.29",
        "FY2026",
        "Revenue by Product",
        "Revenue by Application",
        "Q3 B/G : Approx. 10% increase QoQ",
        "Began HBM4 shipment in Q2",
    )
    missing = [anchor for anchor in required if not _contains(whole, anchor)]
    if missing:
        return False, len(pages), "missing anchors: " + ", ".join(missing)
    product_page = pages[15]
    product_required = ("79,319", "73%", "27%", "DRAM", "NAND")
    product_missing = [anchor for anchor in product_required if not _contains(product_page, anchor)]
    if product_missing:
        return False, len(pages), "product-page anchors missing: " + ", ".join(product_missing)
    return True, len(pages), "matched pinned SK hynix FY2026 Q2 deck fingerprint"


def _candidate_payload(item: OfficialIrPdfCandidate) -> dict[str, object]:
    return {
        "url": item.url,
        "discovered_from": list(item.discovered_from),
        "pdf_sha256": item.pdf_sha256,
        "pdf_bytes": item.pdf_bytes,
        "page_count": item.page_count,
        "fingerprint_match": item.fingerprint_match,
        "fingerprint_reason": item.fingerprint_reason,
    }


def build_official_ir_attachment_discovery_evidence(
    *,
    observed_date: date,
    page_bytes: bytes,
    script_bytes_by_url: dict[str, bytes],
    pdf_bytes_by_url: dict[str, bytes],
) -> OfficialIrAttachmentDiscoveryEvidence:
    expected_scripts = set(extract_explicit_script_urls(page_bytes))
    if set(script_bytes_by_url) != expected_scripts:
        raise ValueError("SK hynix IR discovery script-byte set must match explicit page scripts")
    source_map: dict[str, set[str]] = {}
    for url in extract_explicit_pdf_urls(page_bytes, base_url=SK_HYNIX_IR_EARNINGS_URL):
        source_map.setdefault(url, set()).add("official_ir_page")
    script_resources: list[ExplicitResource] = []
    for script_url, script_bytes in sorted(script_bytes_by_url.items()):
        script_resources.append(
            ExplicitResource(
                source_label=script_url,
                source_sha256=_sha_bytes(script_bytes),
                url=script_url,
            )
        )
        for url in extract_explicit_pdf_urls(script_bytes, base_url=script_url):
            source_map.setdefault(url, set()).add(script_url)
    expected_pdfs = set(source_map)
    if set(pdf_bytes_by_url) != expected_pdfs:
        raise ValueError("SK hynix IR discovery PDF-byte set must match explicit official URLs")

    candidates: list[OfficialIrPdfCandidate] = []
    for url in sorted(expected_pdfs):
        data = pdf_bytes_by_url[url]
        if not data.startswith(b"%PDF-"):
            matched, page_count, reason = False, 0, "explicit official URL did not return a PDF"
        else:
            matched, page_count, reason = fingerprint_skhynix_2026q2_deck(data)
        candidates.append(
            OfficialIrPdfCandidate(
                url=url,
                discovered_from=tuple(sorted(source_map[url])),
                pdf_sha256=_sha_bytes(data),
                pdf_bytes=len(data),
                page_count=page_count,
                fingerprint_match=matched,
                fingerprint_reason=reason,
            )
        )
    matches = [item for item in candidates if item.fingerprint_match]
    resolved = len(matches) == 1
    payload = {
        "observed_date": observed_date.isoformat(),
        "ir_page_sha256": _sha_bytes(page_bytes),
        "scripts": [
            {"url": item.url, "sha256": item.source_sha256}
            for item in script_resources
        ],
        "candidates": [_candidate_payload(item) for item in candidates],
        "resolved": resolved,
        "resolved_url": matches[0].url if resolved else None,
        "resolved_pdf_sha256": matches[0].pdf_sha256 if resolved else None,
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrAttachmentDiscoveryEvidence(
        evidence_id=_sha_payload(payload),
        observed_date=observed_date,
        ir_page_sha256=_sha_bytes(page_bytes),
        script_resources=tuple(script_resources),
        candidates=tuple(candidates),
        resolved=resolved,
        resolved_url=matches[0].url if resolved else None,
        resolved_pdf_sha256=matches[0].pdf_sha256 if resolved else None,
    )


def capture_official_ir_attachment_discovery(
    *,
    observed_date: date,
    output: str | Path = DEFAULT_DISCOVERY_OUTPUT,
    captured_at: datetime | None = None,
    timeout_seconds: float = 20.0,
) -> dict[str, object]:
    page_bytes = download_issuer_resource(
        SK_HYNIX_IR_EARNINGS_URL,
        timeout_seconds=timeout_seconds,
    )
    script_urls = extract_explicit_script_urls(page_bytes)
    if len(script_urls) > _MAX_SCRIPT_COUNT:
        raise ValueError("SK hynix IR page references too many JavaScript resources")
    script_bytes_by_url = {
        url: download_issuer_resource(url, timeout_seconds=timeout_seconds)
        for url in script_urls
    }
    pdf_urls: set[str] = set(
        extract_explicit_pdf_urls(page_bytes, base_url=SK_HYNIX_IR_EARNINGS_URL)
    )
    for script_url, script_bytes in script_bytes_by_url.items():
        pdf_urls.update(extract_explicit_pdf_urls(script_bytes, base_url=script_url))
    pdf_bytes_by_url = {
        url: download_issuer_resource(url, timeout_seconds=timeout_seconds)
        for url in sorted(pdf_urls)
    }
    evidence = build_official_ir_attachment_discovery_evidence(
        observed_date=observed_date,
        page_bytes=page_bytes,
        script_bytes_by_url=script_bytes_by_url,
        pdf_bytes_by_url=pdf_bytes_by_url,
    )
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    if captured.astimezone(_KOREA_TIME_ZONE).date() < observed_date:
        raise ValueError("captured_at cannot precede observed_date in Asia/Seoul")

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix IR discovery artifact path already exists")
    temporary.mkdir()
    try:
        (temporary / "official_ir_page.html").write_bytes(page_bytes)
        script_manifest: list[dict[str, str]] = []
        for index, (url, data) in enumerate(sorted(script_bytes_by_url.items()), start=1):
            name = f"script_{index:02d}.js"
            (temporary / name).write_bytes(data)
            script_manifest.append({"file": name, "url": url, "sha256": _sha_bytes(data)})
        pdf_manifest: list[dict[str, object]] = []
        for index, (url, data) in enumerate(sorted(pdf_bytes_by_url.items()), start=1):
            name = f"candidate_{index:02d}.pdf"
            (temporary / name).write_bytes(data)
            pdf_manifest.append({"file": name, "url": url, "sha256": _sha_bytes(data)})
        manifest = {
            "schema_version": 1,
            "status": "skhynix_official_ir_attachment_discovery_captured",
            "evidence_id": evidence.evidence_id,
            "observed_date": observed_date.isoformat(),
            "ir_page_url": SK_HYNIX_IR_EARNINGS_URL,
            "ir_page_sha256": evidence.ir_page_sha256,
            "script_count": len(script_manifest),
            "candidate_count": len(evidence.candidates),
            "matching_candidate_count": sum(item.fingerprint_match for item in evidence.candidates),
            "resolved": evidence.resolved,
            "resolved_url": evidence.resolved_url,
            "resolved_pdf_sha256": evidence.resolved_pdf_sha256,
            "scripts": script_manifest,
            "pdfs": pdf_manifest,
            "candidates": [_candidate_payload(item) for item in evidence.candidates],
            "discovery_only": True,
            "product_baseline_eligible": False,
            "allocation_resolver_registered": False,
            "numeric_forecast_enabled": False,
            "decision_score_enabled": False,
            "captured_at": captured.isoformat(),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "schema_version": 1,
        "status": "skhynix_official_ir_attachment_discovery_captured",
        "evidence_id": evidence.evidence_id,
        "observed_date": observed_date.isoformat(),
        "ir_page_url": SK_HYNIX_IR_EARNINGS_URL,
        "ir_page_sha256": evidence.ir_page_sha256,
        "script_count": len(evidence.script_resources),
        "candidate_count": len(evidence.candidates),
        "matching_candidate_count": sum(item.fingerprint_match for item in evidence.candidates),
        "resolved": evidence.resolved,
        "resolved_url": evidence.resolved_url,
        "resolved_pdf_sha256": evidence.resolved_pdf_sha256,
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "manifest_path": str((directory / "manifest.json").resolve()),
        "artifact_directory": str(directory.resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_attachment_discovery.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_DISCOVERY_POINTER.name)
    return pointer


__all__ = [
    "DEFAULT_DISCOVERY_OUTPUT",
    "DEFAULT_DISCOVERY_POINTER",
    "OfficialIrAttachmentDiscoveryEvidence",
    "OfficialIrPdfCandidate",
    "SK_HYNIX_IR_EARNINGS_URL",
    "build_official_ir_attachment_discovery_evidence",
    "capture_official_ir_attachment_discovery",
    "download_issuer_resource",
    "extract_explicit_pdf_urls",
    "extract_explicit_script_urls",
    "fingerprint_skhynix_2026q2_deck",
]
