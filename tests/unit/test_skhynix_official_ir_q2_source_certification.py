from __future__ import annotations

import hashlib
from datetime import date

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_source_certification as cert
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    OfficialIrQ2AttachmentEvidence,
    OfficialIrQ2PdfFingerprint,
)

OBSERVED_DATE = date(2026, 8, 15)
PDF_BYTES = b"official-pdf"
PDF_SHA = hashlib.sha256(PDF_BYTES).hexdigest()


def _evidence(*, board_display_date: str = "2026.01.01") -> OfficialIrQ2AttachmentEvidence:
    fingerprint = OfficialIrQ2PdfFingerprint(
        page_count=19,
        text_chars=11282,
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
        candidate_display_date=board_display_date,
        cdn_url="https://cdn.example.test/web",
        file_url2="/attach/q2.pdf",
        pdf_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256=PDF_SHA,
        pdf_bytes=len(PDF_BYTES),
        fingerprint=fingerprint,
    )


def _patch_pages(monkeypatch: pytest.MonkeyPatch, pages: tuple[tuple[str, str], ...]) -> None:
    monkeypatch.setattr(cert, "_extract_pdf_pages", lambda pdf_bytes: pages)


def test_live_q2_forms_and_pdf_date_override_board_year_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pages(
        monkeypatch,
        (
            (
                "SK hynix FY2026 Q2 Earnings Results 2026.07.29",
                "SK hynix FY2026 Q2 Earnings Results                         2026.07.29",
            ),
            (
                "’25 Q2 ’26 Q1 ’26 Q2 Revenue by Product DRAM NAND 73% 27% 79,319",
                "Revenue by Product\n"
                "                    ’25 Q2      ’26 Q1      ’26 Q2\n"
                "DRAM                  77%          78%          73%\n"
                "NAND                  21%          21%          27%\n"
                "Revenue                                         79,319\n",
            ),
        ),
    )

    result = cert.build_q2_source_certification(_evidence(), pdf_bytes=PDF_BYTES)

    assert result.document_identity_verified is True
    assert result.source_published_date_verified is True
    assert result.source_published_date == "2026-07-29"
    assert result.board_display_date == "2026.01.01"
    assert result.board_display_date_used_as_publication_date is False
    assert "FY2026 Q2" in result.q2_identity_anchors
    assert "’26 Q2" in result.q2_identity_anchors
    assert result.readiness_status == "layout_ready_for_contract_review"
    assert len(result.product_layout_pages) == 1
    assert "DRAM                  77%" in result.product_layout_pages[0].layout_text
    assert result.numeric_semantics_certified is False
    assert result.registry_write_eligible is False
    assert result.product_baseline_eligible is False
    assert result.allocation_resolver_registered is False
    assert result.numeric_forecast_enabled is False
    assert result.decision_score_enabled is False


def test_multiple_pdf_calendar_dates_do_not_guess_publication_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pages(
        monkeypatch,
        (
            (
                "SK hynix FY2026 Q2 2026.07.29 reference 2026.06.30",
                "SK hynix FY2026 Q2 2026.07.29 reference 2026.06.30",
            ),
            (
                "Revenue by Product DRAM NAND",
                "Revenue by Product DRAM NAND",
            ),
        ),
    )

    result = cert.build_q2_source_certification(_evidence(), pdf_bytes=PDF_BYTES)

    assert result.document_identity_verified is True
    assert result.publication_date_candidates == ("2026-07-29", "2026-06-30")
    assert result.source_published_date is None
    assert result.source_published_date_verified is False
    assert result.readiness_status == "publication_date_unresolved"


def test_product_layout_must_contain_both_memory_anchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pages(
        monkeypatch,
        (
            (
                "SK hynix FY2026 Q2 2026.07.29 Revenue by Product DRAM",
                "SK hynix FY2026 Q2 2026.07.29 Revenue by Product DRAM 73%",
            ),
        ),
    )

    result = cert.build_q2_source_certification(_evidence(), pdf_bytes=PDF_BYTES)

    assert result.document_identity_verified is True
    assert result.source_published_date_verified is True
    assert result.readiness_status == "product_layout_missing"
    assert result.product_layout_pages[0].dram_anchor is True
    assert result.product_layout_pages[0].nand_anchor is False


def test_pdf_hash_must_match_reverified_attachment() -> None:
    with pytest.raises(ValueError, match="PDF hash differs"):
        cert.build_q2_source_certification(_evidence(), pdf_bytes=b"tampered")
