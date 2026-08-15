"""Certify live SK hynix 2Q26 PDF identity and preserve product-page layout.

This stage is intentionally separate from the older parser-readiness v1 artifact.  It
re-verifies the archived issuer PDF, recognizes the live deck's period/date forms, and
extracts layout-preserving text from the page that contains ``Revenue by Product``.  It
never pairs numeric tokens with accounting semantics and cannot widen any model gate.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from pypdf import PdfReader

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    DEFAULT_Q2_ATTACHMENT_POINTER,
    OfficialIrQ2AttachmentEvidence,
    load_q2_attachment_evidence,
)

DEFAULT_Q2_SOURCE_CERTIFICATION_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-q2-source-certification"
)
DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER = (
    DEFAULT_Q2_SOURCE_CERTIFICATION_OUTPUT
    / "latest_skhynix_ir_q2_source_certification.json"
)

_Q2_PATTERNS = (
    re.compile(r"\b2Q\s*['’]?26\b", flags=re.IGNORECASE),
    re.compile(r"\b2Q\s*2026\b", flags=re.IGNORECASE),
    re.compile(r"\bFY\s*2026\s*Q2\b", flags=re.IGNORECASE),
    re.compile(r"\b2026\s*Q2\b", flags=re.IGNORECASE),
    re.compile(r"(?<!\d)['’]26\s*Q2\b", flags=re.IGNORECASE),
    re.compile(r"2026\s*년\s*2\s*분기"),
)
_DATE_TOKEN = re.compile(r"(?<!\d)(20\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)")
_SK_HYNIX = re.compile(r"SK\s*hynix", flags=re.IGNORECASE)
_REVENUE_BY_PRODUCT = re.compile(r"Revenue\s+by\s+Product", flags=re.IGNORECASE)
_DRAM = re.compile(r"\bDRAM\b", flags=re.IGNORECASE)
_NAND = re.compile(r"\bNAND(?:\s+Flash)?\b", flags=re.IGNORECASE)
_PERCENTAGE = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d+)?\s*%")
_COMMA_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w.])")
_REQUIRED_FALSE_FLAGS = (
    "numeric_semantics_certified",
    "registry_write_eligible",
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)


@dataclass(frozen=True)
class ProductLayoutPage:
    page_number: int
    layout_text: str
    percentage_tokens: tuple[str, ...]
    comma_number_tokens: tuple[str, ...]
    dram_anchor: bool
    nand_anchor: bool


@dataclass(frozen=True)
class OfficialIrQ2SourceCertification:
    evidence_id: str
    attachment_evidence_id: str
    observed_date: date
    source_url: str
    pdf_sha256: str
    candidate_title: str
    board_display_date: str
    board_display_date_used_as_publication_date: bool
    q2_identity_anchors: tuple[str, ...]
    publication_date_candidates: tuple[str, ...]
    source_published_date: str | None
    sk_hynix_anchor: bool
    document_identity_verified: bool
    source_published_date_verified: bool
    product_layout_pages: tuple[ProductLayoutPage, ...]
    readiness_status: str
    numeric_semantics_certified: bool = False
    registry_write_eligible: bool = False
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.attachment_evidence_id):
            raise ValueError("SK hynix Q2 source-certification IDs must be SHA-256")
        if not _valid_sha(self.pdf_sha256):
            raise ValueError("SK hynix Q2 source-certification PDF hash must be SHA-256")
        if self.board_display_date_used_as_publication_date:
            raise ValueError("SK hynix board displayDate cannot certify publication date")
        if self.readiness_status not in {
            "identity_not_verified",
            "publication_date_unresolved",
            "product_layout_missing",
            "layout_ready_for_contract_review",
        }:
            raise ValueError("SK hynix Q2 source-certification status is invalid")
        if any(getattr(self, flag) for flag in _REQUIRED_FALSE_FLAGS):
            raise ValueError("SK hynix Q2 source certification cannot widen model trust")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _extract_pdf_pages(pdf_bytes: bytes) -> tuple[tuple[str, str], ...]:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("SK hynix Q2 source-certification bytes are not a PDF")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError("SK hynix Q2 source-certification PDF is unreadable") from exc
    output: list[tuple[str, str]] = []
    for page in reader.pages:
        try:
            plain = page.extract_text() or ""
            layout = page.extract_text(extraction_mode="layout") or ""
        except Exception as exc:
            raise ValueError("SK hynix Q2 source-certification text extraction failed") from exc
        output.append((plain, layout))
    if not output:
        raise ValueError("SK hynix Q2 source-certification PDF has no pages")
    return tuple(output)


def _valid_date_tokens(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _DATE_TOKEN.finditer(text):
        try:
            parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        values.append(parsed.isoformat())
    return _dedupe(values)


def _matched_q2_anchors(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for pattern in _Q2_PATTERNS:
        for match in pattern.finditer(text):
            values.append(" ".join(match.group(0).split()))
    return _dedupe(values)


def _layout_payload(item: ProductLayoutPage) -> dict[str, object]:
    return {
        "page_number": item.page_number,
        "layout_text": item.layout_text,
        "percentage_tokens": list(item.percentage_tokens),
        "comma_number_tokens": list(item.comma_number_tokens),
        "dram_anchor": item.dram_anchor,
        "nand_anchor": item.nand_anchor,
    }


def _certification_payload(item: OfficialIrQ2SourceCertification) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_q2_source_certification_captured",
        "evidence_id": item.evidence_id,
        "attachment_evidence_id": item.attachment_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "pdf_sha256": item.pdf_sha256,
        "candidate_title": item.candidate_title,
        "board_display_date": item.board_display_date,
        "board_display_date_used_as_publication_date": False,
        "q2_identity_anchors": list(item.q2_identity_anchors),
        "publication_date_candidates": list(item.publication_date_candidates),
        "source_published_date": item.source_published_date,
        "sk_hynix_anchor": item.sk_hynix_anchor,
        "document_identity_verified": item.document_identity_verified,
        "source_published_date_verified": item.source_published_date_verified,
        "product_layout_pages": [_layout_payload(value) for value in item.product_layout_pages],
        "readiness_status": item.readiness_status,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def build_q2_source_certification(
    evidence: OfficialIrQ2AttachmentEvidence,
    *,
    pdf_bytes: bytes,
) -> OfficialIrQ2SourceCertification:
    if hashlib.sha256(pdf_bytes).hexdigest() != evidence.pdf_sha256:
        raise ValueError("SK hynix Q2 source-certification PDF hash differs from attachment")
    pages = _extract_pdf_pages(pdf_bytes)
    combined = "\n".join(plain for plain, _layout in pages)
    q2_anchors = _matched_q2_anchors(combined)
    date_candidates = _valid_date_tokens(combined)
    source_published_date = date_candidates[0] if len(date_candidates) == 1 else None
    sk_hynix_anchor = _SK_HYNIX.search(combined) is not None
    document_identity_verified = sk_hynix_anchor and bool(q2_anchors)
    source_published_date_verified = source_published_date is not None

    layout_pages: list[ProductLayoutPage] = []
    for page_number, (plain, layout) in enumerate(pages, start=1):
        if _REVENUE_BY_PRODUCT.search(plain) is None:
            continue
        layout_pages.append(
            ProductLayoutPage(
                page_number=page_number,
                layout_text=layout[:12000],
                percentage_tokens=_dedupe(
                    [" ".join(match.group(0).split()) for match in _PERCENTAGE.finditer(layout)]
                ),
                comma_number_tokens=_dedupe(
                    [" ".join(match.group(0).split()) for match in _COMMA_NUMBER.finditer(layout)]
                ),
                dram_anchor=_DRAM.search(layout) is not None,
                nand_anchor=_NAND.search(layout) is not None,
            )
        )

    if not document_identity_verified:
        readiness_status = "identity_not_verified"
    elif not source_published_date_verified:
        readiness_status = "publication_date_unresolved"
    elif not layout_pages or not any(
        page.dram_anchor and page.nand_anchor for page in layout_pages
    ):
        readiness_status = "product_layout_missing"
    else:
        readiness_status = "layout_ready_for_contract_review"

    provisional = {
        "attachment_evidence_id": evidence.evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "source_url": evidence.pdf_url,
        "pdf_sha256": evidence.pdf_sha256,
        "candidate_title": evidence.candidate_title,
        "board_display_date": evidence.candidate_display_date,
        "board_display_date_used_as_publication_date": False,
        "q2_identity_anchors": list(q2_anchors),
        "publication_date_candidates": list(date_candidates),
        "source_published_date": source_published_date,
        "sk_hynix_anchor": sk_hynix_anchor,
        "document_identity_verified": document_identity_verified,
        "source_published_date_verified": source_published_date_verified,
        "product_layout_pages": [_layout_payload(value) for value in layout_pages],
        "readiness_status": readiness_status,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrQ2SourceCertification(
        evidence_id=_sha_payload(provisional),
        attachment_evidence_id=evidence.evidence_id,
        observed_date=evidence.observed_date,
        source_url=evidence.pdf_url,
        pdf_sha256=evidence.pdf_sha256,
        candidate_title=evidence.candidate_title,
        board_display_date=evidence.candidate_display_date,
        board_display_date_used_as_publication_date=False,
        q2_identity_anchors=q2_anchors,
        publication_date_candidates=date_candidates,
        source_published_date=source_published_date,
        sk_hynix_anchor=sk_hynix_anchor,
        document_identity_verified=document_identity_verified,
        source_published_date_verified=source_published_date_verified,
        product_layout_pages=tuple(layout_pages),
        readiness_status=readiness_status,
    )


def capture_q2_source_certification(
    attachment_pointer_path: str | Path = DEFAULT_Q2_ATTACHMENT_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_Q2_SOURCE_CERTIFICATION_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    pointer_path = Path(attachment_pointer_path)
    evidence = load_q2_attachment_evidence(pointer_path, evaluation_date=evaluation_date)
    try:
        pointer_obj: object = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 attachment pointer is unreadable for certification") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 attachment pointer must be an object")
    pdf_path = Path(str(pointer_obj.get("pdf_path", "")))
    pdf_bytes = pdf_path.read_bytes()
    certification = build_q2_source_certification(evidence, pdf_bytes=pdf_bytes)

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + certification.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix Q2 source-certification artifact path already exists")
    temporary.mkdir()
    try:
        report_path = temporary / "source_certification.json"
        report_path.write_text(
            json.dumps(
                _certification_payload(certification),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer_payload = {
        **_certification_payload(certification),
        "attachment_pointer_path": str(pointer_path.resolve()),
        "artifact_directory": str(directory.resolve()),
        "report_path": str((directory / "source_certification.json").resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_q2_source_certification.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER.name)
    return pointer_payload


__all__ = [
    "DEFAULT_Q2_SOURCE_CERTIFICATION_OUTPUT",
    "DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER",
    "OfficialIrQ2SourceCertification",
    "ProductLayoutPage",
    "build_q2_source_certification",
    "capture_q2_source_certification",
]
