"""Preserve text geometry for the official SK hynix 2Q26 Revenue by Product page.

This stage consumes the already reverified source-certification artifact and archived
issuer PDF. It records pypdf text fragments plus their text/current matrices so the next
contract review can inspect chart row/column placement without guessing from flattened
text. Coordinates are evidence only: no percentage/revenue pairing is certified here.
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
from typing import Any

from pypdf import PdfReader

from alpha_cycle.intelligence.sk_hynix_official_ir_q2_source_certification import (
    DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER,
    OfficialIrQ2SourceCertification,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_source_certification_verifier import (
    load_q2_source_certification,
)

DEFAULT_Q2_PRODUCT_GEOMETRY_OUTPUT = Path(
    "data/private/research/skhynix-official-ir-q2-product-geometry"
)
DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER = (
    DEFAULT_Q2_PRODUCT_GEOMETRY_OUTPUT / "latest_skhynix_ir_q2_product_geometry.json"
)
_REQUIRED_FALSE_FLAGS = (
    "numeric_semantics_certified",
    "registry_write_eligible",
    "product_baseline_eligible",
    "allocation_resolver_registered",
    "numeric_forecast_enabled",
    "decision_score_enabled",
)
_PERCENTAGE = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d+)?\s*%")
_COMMA_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w.])")
_FOCUS = re.compile(
    r"Revenue\s+by\s+(?:Product|Application)|\bDRAM\b|\bNAND\b|\bOthers\b|"
    r"['’]?2[56]\s*Q[12]|FY2026\s+Q2",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class TextFragment:
    page_number: int
    text: str
    text_matrix: tuple[float, float, float, float, float, float]
    current_matrix: tuple[float, float, float, float, float, float]
    font_size: float

    @property
    def text_x(self) -> float:
        return self.text_matrix[4]

    @property
    def text_y(self) -> float:
        return self.text_matrix[5]


@dataclass(frozen=True)
class ProductGeometryPage:
    page_number: int
    width: float
    height: float
    fragments: tuple[TextFragment, ...]
    focus_fragments: tuple[TextFragment, ...]


@dataclass(frozen=True)
class OfficialIrQ2ProductGeometry:
    evidence_id: str
    source_certification_evidence_id: str
    observed_date: date
    source_url: str
    pdf_sha256: str
    pages: tuple[ProductGeometryPage, ...]
    readiness_status: str
    numeric_semantics_certified: bool = False
    registry_write_eligible: bool = False
    product_baseline_eligible: bool = False
    allocation_resolver_registered: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("SK hynix Q2 geometry evidence ID must be SHA-256")
        if not _valid_sha(self.source_certification_evidence_id):
            raise ValueError("SK hynix Q2 geometry certification ID must be SHA-256")
        if not _valid_sha(self.pdf_sha256):
            raise ValueError("SK hynix Q2 geometry PDF hash must be SHA-256")
        if not self.source_url.startswith("https://"):
            raise ValueError("SK hynix Q2 geometry source URL must use HTTPS")
        if self.readiness_status not in {
            "geometry_missing",
            "geometry_ready_for_semantic_review",
        }:
            raise ValueError("SK hynix Q2 geometry readiness status is invalid")
        if any(getattr(self, flag) for flag in _REQUIRED_FALSE_FLAGS):
            raise ValueError("SK hynix Q2 geometry cannot widen model trust")


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


def _matrix(
    value: list[float] | tuple[float, ...],
) -> tuple[float, float, float, float, float, float]:
    if len(value) != 6:
        raise ValueError("PDF text matrix must contain six values")
    return (
        float(value[0]),
        float(value[1]),
        float(value[2]),
        float(value[3]),
        float(value[4]),
        float(value[5]),
    )


def _fragment_payload(item: TextFragment) -> dict[str, object]:
    return {
        "page_number": item.page_number,
        "text": item.text,
        "text_matrix": list(item.text_matrix),
        "current_matrix": list(item.current_matrix),
        "text_x": item.text_x,
        "text_y": item.text_y,
        "font_size": item.font_size,
    }


def _page_payload(item: ProductGeometryPage) -> dict[str, object]:
    return {
        "page_number": item.page_number,
        "width": item.width,
        "height": item.height,
        "fragment_count": len(item.fragments),
        "focus_fragment_count": len(item.focus_fragments),
        "fragments": [_fragment_payload(value) for value in item.fragments],
        "focus_fragments": [_fragment_payload(value) for value in item.focus_fragments],
    }


def _geometry_payload(item: OfficialIrQ2ProductGeometry) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "skhynix_official_ir_q2_product_geometry_captured",
        "evidence_id": item.evidence_id,
        "source_certification_evidence_id": item.source_certification_evidence_id,
        "observed_date": item.observed_date.isoformat(),
        "source_url": item.source_url,
        "pdf_sha256": item.pdf_sha256,
        "pages": [_page_payload(value) for value in item.pages],
        "readiness_status": item.readiness_status,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }


def _is_focus_text(text: str) -> bool:
    return bool(_FOCUS.search(text) or _PERCENTAGE.search(text) or _COMMA_NUMBER.search(text))


def _extract_page_geometry(page: Any, *, page_number: int) -> ProductGeometryPage:
    fragments: list[TextFragment] = []

    def visitor_text(
        text: str,
        cm: list[float],
        tm: list[float],
        font_dict: dict[str, Any] | None,
        font_size: float,
    ) -> None:
        del font_dict
        cleaned = " ".join(text.split())
        if not cleaned:
            return
        fragments.append(
            TextFragment(
                page_number=page_number,
                text=cleaned[:500],
                text_matrix=_matrix(tm),
                current_matrix=_matrix(cm),
                font_size=float(font_size),
            )
        )

    try:
        page.extract_text(visitor_text=visitor_text)
    except Exception as exc:
        raise ValueError("SK hynix Q2 geometry text extraction failed") from exc

    focus = tuple(item for item in fragments if _is_focus_text(item.text))
    return ProductGeometryPage(
        page_number=page_number,
        width=float(page.mediabox.width),
        height=float(page.mediabox.height),
        fragments=tuple(fragments),
        focus_fragments=focus,
    )


def _extract_geometry_pages(
    pdf_bytes: bytes,
    *,
    page_numbers: tuple[int, ...],
) -> tuple[ProductGeometryPage, ...]:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("SK hynix Q2 geometry bytes do not start with a PDF signature")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise ValueError("SK hynix Q2 geometry PDF is unreadable") from exc

    pages: list[ProductGeometryPage] = []
    for page_number in page_numbers:
        if page_number <= 0 or page_number > len(reader.pages):
            raise ValueError("SK hynix Q2 geometry page number is out of range")
        pages.append(
            _extract_page_geometry(
                reader.pages[page_number - 1],
                page_number=page_number,
            )
        )
    return tuple(pages)


def build_q2_product_geometry(
    certification: OfficialIrQ2SourceCertification,
    *,
    pdf_bytes: bytes,
) -> OfficialIrQ2ProductGeometry:
    if certification.readiness_status != "layout_ready_for_contract_review":
        raise ValueError("SK hynix Q2 source certification is not ready for geometry review")
    if not certification.document_identity_verified:
        raise ValueError("SK hynix Q2 source identity is not verified")
    if not certification.source_published_date_verified:
        raise ValueError("SK hynix Q2 source publication date is not verified")
    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
    if pdf_sha != certification.pdf_sha256:
        raise ValueError("SK hynix Q2 geometry PDF hash differs from source certification")

    page_numbers = tuple(
        sorted({item.page_number for item in certification.product_layout_pages})
    )
    if not page_numbers:
        raise ValueError("SK hynix Q2 source certification has no product layout pages")
    pages = _extract_geometry_pages(pdf_bytes, page_numbers=page_numbers)
    readiness_status = (
        "geometry_ready_for_semantic_review"
        if pages and all(page.focus_fragments for page in pages)
        else "geometry_missing"
    )
    provisional = {
        "source_certification_evidence_id": certification.evidence_id,
        "observed_date": certification.observed_date.isoformat(),
        "source_url": certification.source_url,
        "pdf_sha256": certification.pdf_sha256,
        "pages": [_page_payload(value) for value in pages],
        "readiness_status": readiness_status,
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return OfficialIrQ2ProductGeometry(
        evidence_id=_sha_payload(provisional),
        source_certification_evidence_id=certification.evidence_id,
        observed_date=certification.observed_date,
        source_url=certification.source_url,
        pdf_sha256=certification.pdf_sha256,
        pages=pages,
        readiness_status=readiness_status,
    )


def _load_pdf_bytes_from_certification_pointer(pointer_path: Path) -> bytes:
    try:
        pointer_obj: object = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 source-certification pointer is unreadable") from exc
    if not isinstance(pointer_obj, dict):
        raise ValueError("SK hynix Q2 source-certification pointer must be an object")
    attachment_pointer = Path(str(pointer_obj.get("attachment_pointer_path", "")))
    try:
        attachment_obj: object = json.loads(attachment_pointer.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("SK hynix Q2 attachment pointer is unreadable for geometry") from exc
    if not isinstance(attachment_obj, dict):
        raise ValueError("SK hynix Q2 attachment pointer must be an object")
    pdf_path = Path(str(attachment_obj.get("pdf_path", "")))
    return pdf_path.read_bytes()


def capture_q2_product_geometry(
    certification_pointer_path: str | Path = DEFAULT_Q2_SOURCE_CERTIFICATION_POINTER,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_Q2_PRODUCT_GEOMETRY_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    pointer_path = Path(certification_pointer_path)
    certification = load_q2_source_certification(
        pointer_path,
        evaluation_date=evaluation_date,
    )
    pdf_bytes = _load_pdf_bytes_from_certification_pointer(pointer_path)
    geometry = build_q2_product_geometry(certification, pdf_bytes=pdf_bytes)

    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + geometry.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("SK hynix Q2 product-geometry artifact path already exists")
    temporary.mkdir()
    try:
        report_path = temporary / "product_geometry.json"
        report_path.write_text(
            json.dumps(
                _geometry_payload(geometry),
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
        **_geometry_payload(geometry),
        "source_certification_pointer_path": str(pointer_path.resolve()),
        "artifact_directory": str(directory.resolve()),
        "report_path": str((directory / "product_geometry.json").resolve()),
    }
    temporary_pointer = root / ".latest_skhynix_ir_q2_product_geometry.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(root / DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER.name)
    return pointer_payload


__all__ = [
    "DEFAULT_Q2_PRODUCT_GEOMETRY_OUTPUT",
    "DEFAULT_Q2_PRODUCT_GEOMETRY_POINTER",
    "OfficialIrQ2ProductGeometry",
    "ProductGeometryPage",
    "TextFragment",
    "build_q2_product_geometry",
    "capture_q2_product_geometry",
]
