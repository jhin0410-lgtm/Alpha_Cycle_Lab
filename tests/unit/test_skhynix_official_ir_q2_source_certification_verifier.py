from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_source_certification as cert
from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_source_certification_verifier as verifier,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    OfficialIrQ2AttachmentEvidence,
    OfficialIrQ2PdfFingerprint,
)

OBSERVED_DATE = date(2026, 8, 15)
PDF_BYTES = b"official-pdf"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()


def _attachment() -> OfficialIrQ2AttachmentEvidence:
    fingerprint = OfficialIrQ2PdfFingerprint(
        page_count=19,
        text_chars=100,
        sk_hynix_anchor=True,
        q2_2026_anchor=False,
        revenue_by_product_anchor=True,
        dram_anchor=True,
        nand_anchor=True,
        product_mix_contexts=(),
        document_identity_verified=False,
    )
    return OfficialIrQ2AttachmentEvidence(
        evidence_id="a" * 64,
        board_evidence_id="b" * 64,
        observed_date=OBSERVED_DATE,
        candidate_seq="6850",
        candidate_title="SK hynix FY2026 Q2 Earnings Results",
        candidate_display_date="2026.01.01",
        cdn_url="https://cdn.example.test/web",
        file_url2="/attach/q2.pdf",
        pdf_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256=PDF_SHA,
        pdf_bytes=len(PDF_BYTES),
        fingerprint=fingerprint,
    )


def _certification() -> cert.OfficialIrQ2SourceCertification:
    page = cert.ProductLayoutPage(
        page_number=16,
        layout_text="Revenue by Product DRAM 73% NAND 27%",
        percentage_tokens=("73%", "27%"),
        comma_number_tokens=("79,319",),
        dram_anchor=True,
        nand_anchor=True,
    )
    provisional = {
        "attachment_evidence_id": "a" * 64,
        "observed_date": OBSERVED_DATE.isoformat(),
        "source_url": "https://cdn.example.test/web/attach/q2.pdf",
        "pdf_sha256": PDF_SHA,
        "candidate_title": "SK hynix FY2026 Q2 Earnings Results",
        "board_display_date": "2026.01.01",
        "board_display_date_used_as_publication_date": False,
        "q2_identity_anchors": ["FY2026 Q2", "’26 Q2"],
        "publication_date_candidates": ["2026-07-29"],
        "source_published_date": "2026-07-29",
        "sk_hynix_anchor": True,
        "document_identity_verified": True,
        "source_published_date_verified": True,
        "product_layout_pages": [cert._layout_payload(page)],
        "readiness_status": "layout_ready_for_contract_review",
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return cert.OfficialIrQ2SourceCertification(
        evidence_id=cert._sha_payload(provisional),
        attachment_evidence_id="a" * 64,
        observed_date=OBSERVED_DATE,
        source_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256=PDF_SHA,
        candidate_title="SK hynix FY2026 Q2 Earnings Results",
        board_display_date="2026.01.01",
        board_display_date_used_as_publication_date=False,
        q2_identity_anchors=("FY2026 Q2", "’26 Q2"),
        publication_date_candidates=("2026-07-29",),
        source_published_date="2026-07-29",
        sk_hynix_anchor=True,
        document_identity_verified=True,
        source_published_date_verified=True,
        product_layout_pages=(page,),
        readiness_status="layout_ready_for_contract_review",
    )


def _write_bundle(tmp_path: Path) -> Path:
    certification = _certification()
    pdf_path = tmp_path / "earnings_release.pdf"
    pdf_path.write_bytes(PDF_BYTES)
    attachment_pointer = tmp_path / "attachment.json"
    attachment_pointer.write_text(json.dumps({"pdf_path": str(pdf_path)}), encoding="utf-8")
    report_path = tmp_path / "source_certification.json"
    expected = cert._certification_payload(certification)
    report_path.write_text(json.dumps(expected), encoding="utf-8")
    pointer = {
        **expected,
        "attachment_pointer_path": str(attachment_pointer),
        "report_path": str(report_path),
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_verifier_rebuilds_from_attachment_and_pdf_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_path = _write_bundle(tmp_path)
    attachment = _attachment()
    certification = _certification()
    monkeypatch.setattr(
        verifier,
        "load_q2_attachment_evidence",
        lambda pointer_path, *, evaluation_date: attachment,
    )
    monkeypatch.setattr(
        cert,
        "build_q2_source_certification",
        lambda evidence, *, pdf_bytes: certification,
    )

    loaded = verifier.load_q2_source_certification(
        pointer_path,
        evaluation_date=OBSERVED_DATE,
    )

    assert loaded.evidence_id == certification.evidence_id
    assert loaded.source_published_date == "2026-07-29"


def test_verifier_rejects_persisted_pointer_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pointer_path = _write_bundle(tmp_path)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["readiness_status"] = "identity_not_verified"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    monkeypatch.setattr(
        verifier,
        "load_q2_attachment_evidence",
        lambda pointer_path, *, evaluation_date: _attachment(),
    )
    monkeypatch.setattr(
        cert,
        "build_q2_source_certification",
        lambda evidence, *, pdf_bytes: _certification(),
    )

    with pytest.raises(ValueError, match="pointer mismatch"):
        verifier.load_q2_source_certification(pointer_path, evaluation_date=OBSERVED_DATE)
