"""Reverify archived SK hynix official-IR attachment discovery from source bytes."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    OfficialIrAttachmentDiscoveryEvidence,
    OfficialIrPdfCandidate,
    build_official_ir_attachment_discovery_evidence,
    extract_explicit_pdf_urls,
    extract_explicit_script_urls,
)

_REQUIRED_FALSE_FLAGS = (
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def _require_discovery_only(payload: dict[str, object], label: str) -> None:
    if payload.get("discovery_only") is not True:
        raise ValueError(f"{label} must remain discovery-only")
    for flag in _REQUIRED_FALSE_FLAGS:
        if payload.get(flag) is not False:
            raise ValueError(f"{label} requires {flag}=false")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _candidate_row(item: OfficialIrPdfCandidate) -> dict[str, object]:
    return {
        "url": item.url,
        "discovered_from": list(item.discovered_from),
        "pdf_sha256": item.pdf_sha256,
        "pdf_bytes": item.pdf_bytes,
        "page_count": item.page_count,
        "fingerprint_match": item.fingerprint_match,
        "fingerprint_reason": item.fingerprint_reason,
    }


def load_official_ir_attachment_discovery_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> OfficialIrAttachmentDiscoveryEvidence:
    pointer = _json_object(Path(pointer_path), "SK hynix IR discovery pointer")
    if pointer.get("status") != "skhynix_official_ir_attachment_discovery_captured":
        raise ValueError("SK hynix IR discovery pointer status is invalid")
    _require_discovery_only(pointer, "SK hynix IR discovery pointer")
    observed_date = date.fromisoformat(str(pointer.get("observed_date", "")))
    if observed_date > evaluation_date:
        raise ValueError("SK hynix IR discovery evidence was not yet observed")

    artifact_directory = Path(str(pointer.get("artifact_directory", "")))
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "SK hynix IR discovery manifest",
    )
    if manifest.get("status") != "skhynix_official_ir_attachment_discovery_captured":
        raise ValueError("SK hynix IR discovery manifest status is invalid")
    _require_discovery_only(manifest, "SK hynix IR discovery manifest")

    try:
        page_bytes = (artifact_directory / "official_ir_page.html").read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SK hynix IR discovery archived page bytes are missing") from exc
    page_sha = _sha_bytes(page_bytes)
    if page_sha != str(pointer.get("ir_page_sha256", "")):
        raise ValueError("SK hynix IR discovery page hash does not reproduce")
    if page_sha != str(manifest.get("ir_page_sha256", "")):
        raise ValueError("SK hynix IR discovery manifest page hash does not reproduce")

    script_urls = extract_explicit_script_urls(page_bytes)
    raw_scripts = manifest.get("scripts")
    if not isinstance(raw_scripts, list) or len(raw_scripts) != len(script_urls):
        raise ValueError("SK hynix IR discovery script manifest does not match page")
    script_bytes_by_url: dict[str, bytes] = {}
    for raw in raw_scripts:
        if not isinstance(raw, dict):
            raise ValueError("SK hynix IR discovery script manifest row is invalid")
        row = cast(dict[object, object], raw)
        file_name = str(row.get("file", ""))
        url = str(row.get("url", ""))
        if Path(file_name).name != file_name or url not in script_urls:
            raise ValueError("SK hynix IR discovery script identity is unsafe")
        try:
            data = (artifact_directory / file_name).read_bytes()
        except FileNotFoundError as exc:
            raise ValueError("SK hynix IR discovery archived script bytes are missing") from exc
        if _sha_bytes(data) != str(row.get("sha256", "")):
            raise ValueError("SK hynix IR discovery script hash does not reproduce")
        script_bytes_by_url[url] = data
    if set(script_bytes_by_url) != set(script_urls):
        raise ValueError("SK hynix IR discovery script identities are duplicated or missing")

    explicit_pdf_urls = set(
        extract_explicit_pdf_urls(
            page_bytes,
            base_url=str(pointer.get("ir_page_url", "")),
        )
    )
    for script_url, script_bytes in script_bytes_by_url.items():
        explicit_pdf_urls.update(
            extract_explicit_pdf_urls(script_bytes, base_url=script_url)
        )
    raw_pdfs = manifest.get("pdfs")
    if not isinstance(raw_pdfs, list) or len(raw_pdfs) != len(explicit_pdf_urls):
        raise ValueError("SK hynix IR discovery PDF manifest does not match explicit URLs")
    pdf_bytes_by_url: dict[str, bytes] = {}
    for raw in raw_pdfs:
        if not isinstance(raw, dict):
            raise ValueError("SK hynix IR discovery PDF manifest row is invalid")
        row = cast(dict[object, object], raw)
        file_name = str(row.get("file", ""))
        url = str(row.get("url", ""))
        if Path(file_name).name != file_name or url not in explicit_pdf_urls:
            raise ValueError("SK hynix IR discovery PDF identity is unsafe")
        try:
            data = (artifact_directory / file_name).read_bytes()
        except FileNotFoundError as exc:
            raise ValueError("SK hynix IR discovery archived PDF bytes are missing") from exc
        if _sha_bytes(data) != str(row.get("sha256", "")):
            raise ValueError("SK hynix IR discovery PDF hash does not reproduce")
        pdf_bytes_by_url[url] = data
    if set(pdf_bytes_by_url) != explicit_pdf_urls:
        raise ValueError("SK hynix IR discovery PDF identities are duplicated or missing")

    reconstructed = build_official_ir_attachment_discovery_evidence(
        observed_date=observed_date,
        page_bytes=page_bytes,
        script_bytes_by_url=script_bytes_by_url,
        pdf_bytes_by_url=pdf_bytes_by_url,
    )
    persisted_id = str(pointer.get("evidence_id", ""))
    if reconstructed.evidence_id != persisted_id:
        raise ValueError("SK hynix IR discovery evidence does not reproduce from source bytes")
    if str(manifest.get("evidence_id", "")) != persisted_id:
        raise ValueError("SK hynix IR discovery manifest evidence ID mismatch")
    if reconstructed.resolved != bool(pointer.get("resolved")):
        raise ValueError("SK hynix IR discovery resolved flag mismatch")
    if reconstructed.resolved_url != pointer.get("resolved_url"):
        raise ValueError("SK hynix IR discovery resolved URL mismatch")
    if reconstructed.resolved_pdf_sha256 != pointer.get("resolved_pdf_sha256"):
        raise ValueError("SK hynix IR discovery resolved PDF hash mismatch")
    if reconstructed.resolved != bool(manifest.get("resolved")):
        raise ValueError("SK hynix IR discovery manifest resolved flag mismatch")
    if reconstructed.resolved_url != manifest.get("resolved_url"):
        raise ValueError("SK hynix IR discovery manifest resolved URL mismatch")
    if reconstructed.resolved_pdf_sha256 != manifest.get("resolved_pdf_sha256"):
        raise ValueError("SK hynix IR discovery manifest resolved PDF hash mismatch")
    raw_candidates = manifest.get("candidates")
    expected_candidates = [_candidate_row(item) for item in reconstructed.candidates]
    if raw_candidates != expected_candidates:
        raise ValueError("SK hynix IR discovery persisted candidates do not reproduce")
    return reconstructed


__all__ = ["load_official_ir_attachment_discovery_evidence"]
