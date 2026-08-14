"""Capture the official SK hynix 2Q26 Earnings Release PDF from verified board bytes.

This stage consumes a reverified SK hynix board API artifact.  It never searches for an
attachment and never guesses a CDN identifier.  Exactly one board row must already be
classified as the 2026 Q2 candidate, that row must contain ``fileUrl2``, and the download
URL is formed only by the issuer JavaScript contract ``returned cdnUrl + returned fileUrl2``.

The PDF is archived and fingerprinted for document identity, but remains discovery evidence.
No product baseline, allocation resolver, forecast, valuation, score, order, or trade path
is enabled by this module.
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
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from alpha_cycle.intelligence.sk_hynix_official_ir_board_api_capture import BoardRowSummary
from alpha_cycle.intelligence.sk_hynix_official_ir_board_api_pipeline import (
    DEFAULT_BOARD_API_POINTER,
    OfficialIrBoardApiCapture,
    load_board_api_capture,
)

DEFAULT_Q2_ATTACHMENT_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-q2-attachment"
)
DEFAULT_Q2_ATTACHMENT_POINTER = (
    DEFAULT_Q2_ATTACHMENT_OUTPUT / "latest_skhynix_ir_q2_attachment.json"
)

_REQUIRED_FALSE_FLAGS = (
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)
_Q2_2026_PATTERNS = (
    re.compile(r"\b2Q\s*['’]?26\b", flags=re.IGNORECASE),
    re.compile(r"\b2Q\s*2026\b", flags=re.IGNORECASE),
    re.compile(r"\b2026\s*Q2\b", flags=re.IGNORECASE),
    re.compile(r"2026\s*년\s*2\s*분기"),
)
_SK_HYNIX_PATTERN = re.compile(r"SK\s*hynix", flags=re.IGNORECASE)
_REVENUE_BY_PRODUCT_PATTERN = re.compile(r"Revenue\s+by\s+Product", flags=re.IGNORECASE)
_DRAM_PATTERN = re.compile(r"\bDRAM\b", flags=re.IGNORECASE)
_NAND_PATTERN = re.compile(r"\bNAND\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class PdfContext:
    page_number: int
    anchor: str
    context: str


@dataclass(frozen=True)
class OfficialIrQ2PdfFingerprint:
    page_count: int
    text_chars: int
    sk_hynix_anchor: bool
    q2_2026_anchor: bool
    revenue_by_product_anchor: bool
    dram_anchor: bool
    nand_anchor: bool
    product_mix_contexts: tuple[PdfContext, ...]
    document_identity_verified: bool


@dataclass(frozen=True)
class OfficialIrQ2AttachmentEvidence:
    evidence_id: str
    board_evidence_id: str
    observed_date: date
    candidate_seq: str
    candidate_title: str
    candidate_display_date: str
    cdn_url: str
    file_url2: str
    pdf_url: str
    pdf_sha256: str
    pdf_bytes: int
    fingerprint: OfficialIrQ2PdfFingerprint
    discovery_only: bool = True
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id) or not _valid_sha(self.board_evidence_id):
            raise ValueError("SK hynix Q2 attachment evidence IDs must be SHA-256")
        if not _valid_sha(self.pdf_sha256):
            raise ValueError("SK hynix Q2 attachment PDF hash must be SHA-256")
        if not self.pdf_url.startswith("https://"):
            raise ValueError("SK hynix Q2 attachment URL must use HTTPS")
        if self.pdf_bytes <= 0 or self.fingerprint.page_count <= 0:
            raise ValueError("SK hynix Q2 attachment PDF must be non-empty")
        if not self.discovery_only:
            raise ValueError("SK hynix Q2 attachment evidence must remain discovery-only")
        if (
            self.product_baseline_eligible
            or self.allocation_resolver_registered
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("SK hynix Q2 attachment cannot widen model trust")


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sha_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _compact(value: str) -> str:
    return " ".join(value.split())


def _context_payload(item: PdfContext) -> dict[str, object]:
    return {
        "page_number": item.page_number,
        "anchor": item.anchor,
        "context": item.context,
    }


def _fingerprint_payload(item: OfficialIrQ2PdfFingerprint) -> dict[str, object]:
    return {
        "page_count": item.page_count,
        "text_chars": item.text_chars,
        "sk_hynix_anchor": item.sk_hynix_anchor,
        "q2_2026_anchor": item.q2_2026_anchor,
        "revenue_by_product_anchor": item.revenue_by_product_anchor,
        "dram_anchor": item.dram_anchor,
        "nand_anchor": item.nand_anchor,
        "product_mix_contexts": [_context_payload(value) for value in item.product_mix_contexts],
        "document_identity_verified": item.document_identity_verified,
    }


def _evidence_payload(item: OfficialIrQ2AttachmentEvidence) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_q2_attachment_captured",
        "evidence_id": item.evidence_id,
        "board_evidence_id": item.board_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "candidate_seq": item.candidate_seq,
        "candidate_title": item.candidate_title,
        "candidate_display_date": item.candidate_display_date,
        "cdn_url": item.cdn_url,
        "file_url2": item.file_url2,
        "pdf_url": item.pdf_url,
        "pdf_sha256": item.pdf_sha256,
        "pdf_bytes": item.pdf_bytes,
        "fingerprint": _fingerprint_payload(item.fingerprint),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def _only_q2_candidate(board: OfficialIrBoardApiCapture) -> BoardRowSummary:
    candidates = [item for item in board.rows if item.candidate_2026q2]
    if len(candidates) != 1:
        raise ValueError(
            "SK hynix board capture must contain exactly one 2026 Q2 candidate row; "
            f"found {len(candidates)}"
        )
    candidate = candidates[0]
    if not candidate.file_url2:
        raise ValueError("SK hynix 2026 Q2 board row is missing fileUrl2")
    return candidate


def compose_returned_pdf_url(cdn_url: str, file_url2: str) -> str:
    """Apply the issuer's literal string-concatenation contract safely."""

    cdn = urlparse(cdn_url)
    if cdn.scheme != "https" or not cdn.hostname or cdn.query or cdn.fragment:
        raise ValueError("SK hynix returned cdnUrl is not a clean HTTPS base")

    raw_file = file_url2.strip()
    if not raw_file or "\\" in raw_file or any(ord(char) < 32 for char in raw_file):
        raise ValueError("SK hynix returned fileUrl2 contains unsafe characters")
    file_parts = urlparse(raw_file)
    if file_parts.scheme or file_parts.netloc or file_parts.query or file_parts.fragment:
        raise ValueError("SK hynix returned fileUrl2 must be a relative path")
    decoded_segments = [unquote(part) for part in file_parts.path.split("/")]
    if any(part in {".", ".."} for part in decoded_segments):
        raise ValueError("SK hynix returned fileUrl2 contains path traversal")

    pdf_url = cdn_url.rstrip("/") + "/" + file_parts.path.lstrip("/")
    parsed_pdf = urlparse(pdf_url)
    if parsed_pdf.scheme != "https" or parsed_pdf.hostname != cdn.hostname:
        raise ValueError("SK hynix composed PDF URL escaped the returned CDN host")
    return pdf_url


def _extract_page_texts(pdf_bytes: bytes) -> tuple[str, ...]:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("SK hynix attachment bytes do not start with a PDF signature")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError("SK hynix attachment bytes are not a readable PDF") from exc
    if not reader.pages:
        raise ValueError("SK hynix attachment PDF has no pages")
    texts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise ValueError("SK hynix attachment PDF text extraction failed") from exc
        texts.append(text)
    return tuple(texts)


def _anchor_context(text: str, match: re.Match[str], *, width: int = 850) -> str:
    half = width // 2
    return _compact(
        text[max(0, match.start() - half) : min(len(text), match.end() + half)]
    )[:width]


def fingerprint_q2_pdf(pdf_bytes: bytes) -> OfficialIrQ2PdfFingerprint:
    page_texts = _extract_page_texts(pdf_bytes)
    combined = "\n".join(page_texts)
    q2_anchor = any(pattern.search(combined) is not None for pattern in _Q2_2026_PATTERNS)
    sk_hynix_anchor = _SK_HYNIX_PATTERN.search(combined) is not None
    revenue_anchor = _REVENUE_BY_PRODUCT_PATTERN.search(combined) is not None
    dram_anchor = _DRAM_PATTERN.search(combined) is not None
    nand_anchor = _NAND_PATTERN.search(combined) is not None

    contexts: list[PdfContext] = []
    for page_number, text in enumerate(page_texts, start=1):
        for match in _REVENUE_BY_PRODUCT_PATTERN.finditer(text):
            contexts.append(
                PdfContext(
                    page_number=page_number,
                    anchor="Revenue by Product",
                    context=_anchor_context(text, match),
                )
            )
            if len(contexts) >= 4:
                break
        if len(contexts) >= 4:
            break

    return OfficialIrQ2PdfFingerprint(
        page_count=len(page_texts),
        text_chars=sum(len(value) for value in page_texts),
        sk_hynix_anchor=sk_hynix_anchor,
        q2_2026_anchor=q2_anchor,
        revenue_by_product_anchor=revenue_anchor,
        dram_anchor=dram_anchor,
        nand_anchor=nand_anchor,
        product_mix_contexts=tuple(contexts),
        document_identity_verified=sk_hynix_anchor and q2_anchor,
    )


def download_returned_pdf(pdf_url: str, *, timeout_seconds: float = 30.0) -> bytes:
    request = Request(
        pdf_url,
        headers={
            "Accept": "application/pdf,*/*;q=0.8",
            "User-Agent": "Alpha-Cycle-Lab/0.1 skhynix-ir-readonly",
            "Referer": "https://www.skhynix.com/ir/UI-FR-IR06/",
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return bytes(response.read())


def build_q2_attachment_evidence(
    board: OfficialIrBoardApiCapture,
    *,
    pdf_bytes: bytes,
) -> OfficialIrQ2AttachmentEvidence:
    candidate = _only_q2_candidate(board)
    assert candidate.file_url2 is not None
    pdf_url = compose_returned_pdf_url(board.cdn_url, candidate.file_url2)
    fingerprint = fingerprint_q2_pdf(pdf_bytes)
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    payload = {
        "board_evidence_id": board.evidence_id,
        "observed_date": board.observed_date.isoformat(),
        "candidate_seq": candidate.seq,
        "candidate_title": candidate.title,
        "candidate_display_date": candidate.display_date,
        "cdn_url": board.cdn_url,
        "file_url2": candidate.file_url2,
        "pdf_url": pdf_url,
        "pdf_sha256": pdf_sha,
        "pdf_bytes": len(pdf_bytes),
        "fingerprint": _fingerprint_payload(fingerprint),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrQ2AttachmentEvidence(
        evidence_id=_sha_payload(payload),
        board_evidence_id=board.evidence_id,
        observed_date=board.observed_date,
        candidate_seq=candidate.seq,
        candidate_title=candidate.title,
        candidate_display_date=candidate.display_date,
        cdn_url=board.cdn_url,
        file_url2=candidate.file_url2,
        pdf_url=pdf_url,
        pdf_sha256=pdf_sha,
        pdf_bytes=len(pdf_bytes),
        fingerprint=fingerprint,
    )


def capture_q2_attachment(
    board_pointer_path: str | Path = DEFAULT_BOARD_API_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_Q2_ATTACHMENT_OUTPUT,
    timeout_seconds: float = 30.0,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    board = load_board_api_capture(
        board_pointer_path,
        evaluation_date=evaluation_date,
    )
    candidate = _only_q2_candidate(board)
    assert candidate.file_url2 is not None
    pdf_url = compose_returned_pdf_url(board.cdn_url, candidate.file_url2)
    pdf_bytes = download_returned_pdf(pdf_url, timeout_seconds=timeout_seconds)
    evidence = build_q2_attachment_evidence(board, pdf_bytes=pdf_bytes)

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + evidence.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix Q2 attachment artifact path already exists")
    temporary.mkdir()
    try:
        (temporary / "earnings_release.pdf").write_bytes(pdf_bytes)
        (temporary / "attachment_evidence.json").write_text(
            json.dumps(_evidence_payload(evidence), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    pointer = {
        "schema_version": 1,
        "status": "skhynix_official_ir_q2_attachment_captured",
        "evidence_id": evidence.evidence_id,
        "board_evidence_id": evidence.board_evidence_id,
        "observed_date": evidence.observed_date.isoformat(),
        "candidate_seq": evidence.candidate_seq,
        "candidate_title": evidence.candidate_title,
        "candidate_display_date": evidence.candidate_display_date,
        "pdf_url": evidence.pdf_url,
        "pdf_sha256": evidence.pdf_sha256,
        "pdf_bytes": evidence.pdf_bytes,
        "fingerprint": _fingerprint_payload(evidence.fingerprint),
        "discovery_only": True,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "board_pointer_path": str(Path(board_pointer_path).resolve()),
        "artifact_directory": str(directory.resolve()),
        "pdf_path": str((directory / "earnings_release.pdf").resolve()),
        "evidence_path": str((directory / "attachment_evidence.json").resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_q2_attachment.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_Q2_ATTACHMENT_POINTER.name)
    return pointer


def load_q2_attachment_evidence(
    pointer_path: str | Path = DEFAULT_Q2_ATTACHMENT_POINTER,
    *,
    evaluation_date: date,
) -> OfficialIrQ2AttachmentEvidence:
    pointer_file = Path(pointer_path)
    try:
        pointer_obj: object = json.loads(pointer_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 attachment pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 attachment pointer must be an object")
    pointer = {str(key): value for key, value in pointer_obj.items()}
    if pointer.get("status") != "skhynix_official_ir_q2_attachment_captured":
        raise ValueError("SK hynix Q2 attachment pointer status is invalid")
    if pointer.get("discovery_only") is not True:
        raise ValueError("SK hynix Q2 attachment pointer must remain discovery-only")
    for flag in _REQUIRED_FALSE_FLAGS:
        if pointer.get(flag) is not False:
            raise ValueError(f"SK hynix Q2 attachment pointer requires {flag}=false")

    board = load_board_api_capture(
        Path(str(pointer.get("board_pointer_path", ""))),
        evaluation_date=evaluation_date,
    )
    if board.evidence_id != str(pointer.get("board_evidence_id", "")):
        raise ValueError("SK hynix Q2 attachment board evidence no longer reproduces")
    pdf_path = Path(str(pointer.get("pdf_path", "")))
    pdf_bytes = pdf_path.read_bytes()
    reconstructed = build_q2_attachment_evidence(board, pdf_bytes=pdf_bytes)
    if reconstructed.evidence_id != str(pointer.get("evidence_id", "")):
        raise ValueError("SK hynix Q2 attachment does not reproduce from archived bytes")
    if reconstructed.pdf_sha256 != str(pointer.get("pdf_sha256", "")):
        raise ValueError("SK hynix Q2 attachment PDF hash mismatch")

    evidence_path = Path(str(pointer.get("evidence_path", "")))
    try:
        report_obj: object = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 attachment evidence report is unreadable") from exc
    if not isinstance(report_obj, dict):
        raise ValueError("SK hynix Q2 attachment evidence report must be an object")
    report = {str(key): value for key, value in report_obj.items()}
    expected = _evidence_payload(reconstructed)
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(f"SK hynix Q2 attachment evidence mismatch: {key}")
    return reconstructed


__all__ = [
    "DEFAULT_Q2_ATTACHMENT_OUTPUT",
    "DEFAULT_Q2_ATTACHMENT_POINTER",
    "OfficialIrQ2AttachmentEvidence",
    "OfficialIrQ2PdfFingerprint",
    "PdfContext",
    "build_q2_attachment_evidence",
    "capture_q2_attachment",
    "compose_returned_pdf_url",
    "download_returned_pdf",
    "fingerprint_q2_pdf",
    "load_q2_attachment_evidence",
]
