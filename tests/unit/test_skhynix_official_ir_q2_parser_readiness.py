from __future__ import annotations

from datetime import date

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_parser_readiness as readiness
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_attachment_capture import (
    OfficialIrQ2AttachmentEvidence,
    OfficialIrQ2PdfFingerprint,
)

OBSERVED_DATE = date(2026, 8, 15)


def _fingerprint(*, identity: bool = True) -> OfficialIrQ2PdfFingerprint:
    return OfficialIrQ2PdfFingerprint(
        page_count=19,
        text_chars=5000,
        sk_hynix_anchor=identity,
        q2_2026_anchor=identity,
        revenue_by_product_anchor=True,
        dram_anchor=True,
        nand_anchor=True,
        product_mix_contexts=(),
        document_identity_verified=identity,
    )


def _evidence(*, identity: bool = True) -> OfficialIrQ2AttachmentEvidence:
    return OfficialIrQ2AttachmentEvidence(
        evidence_id="a" * 64,
        board_evidence_id="b" * 64,
        observed_date=OBSERVED_DATE,
        candidate_seq="9001",
        candidate_title="2026년 2분기 실적발표",
        candidate_display_date="2026.07.29",
        cdn_url="https://cdn.example.test/web",
        file_url2="/attach/q2.pdf",
        pdf_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256="c" * 64,
        pdf_bytes=1000,
        fingerprint=_fingerprint(identity=identity),
    )


def _patch_pdf_text(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fingerprint: OfficialIrQ2PdfFingerprint,
    pages: tuple[str, ...],
) -> None:
    monkeypatch.setattr(
        readiness.attachment,
        "fingerprint_q2_pdf",
        lambda pdf_bytes: fingerprint,
    )
    monkeypatch.setattr(
        readiness.attachment,
        "_extract_page_texts",
        lambda pdf_bytes: pages,
    )


def test_parser_readiness_extracts_raw_tokens_without_certifying_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence()
    _patch_pdf_text(
        monkeypatch,
        fingerprint=evidence.fingerprint,
        pages=(
            "SK hynix 2Q26 Earnings Release",
            (
                "Revenue by Product\n"
                "DRAM 73%\n"
                "NAND 27%\n"
                "Revenue 79,319\n"
            ),
        ),
    )

    result = readiness.build_q2_parser_readiness(evidence, pdf_bytes=b"official-pdf")

    assert result.readiness_status == "context_ready_for_parser_contract_review"
    assert result.percentage_tokens == ("73%", "27%")
    assert result.comma_number_tokens == ("79,319",)
    assert len(result.contexts) == 1
    assert result.contexts[0].dram_anchor is True
    assert result.contexts[0].nand_anchor is True
    assert "DRAM 73%" in result.contexts[0].relevant_lines
    assert "NAND 27%" in result.contexts[0].relevant_lines
    assert result.numeric_semantics_certified is False
    assert result.registry_write_eligible is False
    assert result.product_baseline_eligible is False
    assert result.allocation_resolver_registered is False


def test_parser_readiness_does_not_pair_or_interpret_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence()
    _patch_pdf_text(
        monkeypatch,
        fingerprint=evidence.fingerprint,
        pages=(
            "SK hynix 2Q26",
            "Revenue by Product DRAM NAND 27% 73% 79,319 11,574",
        ),
    )

    result = readiness.build_q2_parser_readiness(evidence, pdf_bytes=b"official-pdf")

    assert result.percentage_tokens == ("27%", "73%")
    assert result.comma_number_tokens == ("79,319", "11,574")
    assert result.numeric_semantics_certified is False
    assert not hasattr(result, "dram_share")
    assert not hasattr(result, "nand_share")


def test_identity_failure_blocks_parser_contract_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence(identity=False)
    _patch_pdf_text(
        monkeypatch,
        fingerprint=evidence.fingerprint,
        pages=("Revenue by Product DRAM 73% NAND 27%",),
    )

    result = readiness.build_q2_parser_readiness(evidence, pdf_bytes=b"official-pdf")

    assert result.readiness_status == "identity_not_verified"
    assert result.registry_write_eligible is False


def test_missing_product_mix_context_stays_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _evidence()
    _patch_pdf_text(
        monkeypatch,
        fingerprint=evidence.fingerprint,
        pages=("SK hynix 2Q26 Earnings Release DRAM NAND",),
    )

    result = readiness.build_q2_parser_readiness(evidence, pdf_bytes=b"official-pdf")

    assert result.readiness_status == "product_mix_context_missing"
    assert result.contexts == ()
    assert result.numeric_semantics_certified is False


def test_board_display_date_must_be_parseable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = OfficialIrQ2AttachmentEvidence(
        evidence_id="a" * 64,
        board_evidence_id="b" * 64,
        observed_date=OBSERVED_DATE,
        candidate_seq="9001",
        candidate_title="2Q26 Earnings Release",
        candidate_display_date="unknown",
        cdn_url="https://cdn.example.test/web",
        file_url2="/attach/q2.pdf",
        pdf_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256="c" * 64,
        pdf_bytes=1000,
        fingerprint=_fingerprint(),
    )
    _patch_pdf_text(
        monkeypatch,
        fingerprint=evidence.fingerprint,
        pages=("Revenue by Product DRAM 73% NAND 27%",),
    )

    with pytest.raises(ValueError, match="normalize board display date"):
        readiness.build_q2_parser_readiness(evidence, pdf_bytes=b"official-pdf")
