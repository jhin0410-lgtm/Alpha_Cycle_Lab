from __future__ import annotations

import io
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pypdf import PdfWriter

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_attachment_capture as q2
from alpha_cycle.intelligence.sk_hynix_official_ir_board_api_capture import (
    BoardRowSummary,
    OfficialIrBoardApiCapture,
)

OBSERVED_DATE = date(2026, 8, 15)


def _pdf_bytes() -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def _board(*, rows: tuple[BoardRowSummary, ...] | None = None) -> OfficialIrBoardApiCapture:
    board_rows = rows or (
        BoardRowSummary(
            seq="9001",
            title="2026년 2분기 실적발표",
            display_date="2026.07.29",
            file_url1="/call.mp3",
            file_url2="/attach/2026q2.pdf",
            file_url3="/attach/2026q2_press.pdf",
            file_url4="/attach/2026q2_ceo.pdf",
            candidate_2026q2=True,
        ),
    )
    return OfficialIrBoardApiCapture(
        evidence_id="a" * 64,
        transport_evidence_id="b" * 64,
        observed_date=OBSERVED_DATE,
        request_url="https://api.example.test/board/list",
        request_params=(
            ("bcode", "105"),
            ("lang", "ENG"),
            ("page", "1"),
            ("pageSize", "200"),
        ),
        response_sha256="c" * 64,
        cdn_url="https://cdn.example.test/web",
        total=len(board_rows),
        rows=board_rows,
        candidate_seqs=tuple(item.seq for item in board_rows if item.candidate_2026q2),
    )


def test_compose_returned_pdf_url_preserves_returned_web_prefix() -> None:
    assert q2.compose_returned_pdf_url(
        "https://cdn.example.test/web",
        "/attach/2026q2.pdf",
    ) == "https://cdn.example.test/web/attach/2026q2.pdf"


@pytest.mark.parametrize(
    "file_url",
    [
        "https://evil.example/q2.pdf",
        "//evil.example/q2.pdf",
        "/attach/../secret.pdf",
        "/attach/%2e%2e/secret.pdf",
        "/attach/q2.pdf?download=1",
        "/attach/q2.pdf#fragment",
        "\\server\\share\\q2.pdf",
    ],
)
def test_compose_returned_pdf_url_rejects_unsafe_returned_paths(file_url: str) -> None:
    with pytest.raises(ValueError):
        q2.compose_returned_pdf_url("https://cdn.example.test/web", file_url)


def test_exactly_one_q2_candidate_is_required() -> None:
    first = _board().rows[0]
    second = BoardRowSummary(
        seq="9002",
        title="2Q26 Earnings Release",
        display_date="2026.07.29",
        file_url1=None,
        file_url2="/attach/second.pdf",
        file_url3=None,
        file_url4=None,
        candidate_2026q2=True,
    )
    with pytest.raises(ValueError, match="exactly one"):
        q2.build_q2_attachment_evidence(
            _board(rows=(first, second)),
            pdf_bytes=_pdf_bytes(),
        )


def test_q2_candidate_must_have_file_url2() -> None:
    row = BoardRowSummary(
        seq="9001",
        title="2Q26 Earnings Release",
        display_date="2026.07.29",
        file_url1=None,
        file_url2=None,
        file_url3=None,
        file_url4=None,
        candidate_2026q2=True,
    )
    with pytest.raises(ValueError, match="fileUrl2"):
        q2.build_q2_attachment_evidence(
            _board(rows=(row,)),
            pdf_bytes=_pdf_bytes(),
        )


def test_fingerprint_reports_product_mix_context_without_parsing_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        q2,
        "_extract_page_texts",
        lambda pdf_bytes: (
            "SK hynix 2Q26 Earnings Release",
            "Revenue by Product DRAM 73% NAND 27% total revenue 79,319",
        ),
    )

    fingerprint = q2.fingerprint_q2_pdf(b"ignored")

    assert fingerprint.page_count == 2
    assert fingerprint.sk_hynix_anchor is True
    assert fingerprint.q2_2026_anchor is True
    assert fingerprint.revenue_by_product_anchor is True
    assert fingerprint.dram_anchor is True
    assert fingerprint.nand_anchor is True
    assert fingerprint.document_identity_verified is True
    assert len(fingerprint.product_mix_contexts) == 1
    assert fingerprint.product_mix_contexts[0].page_number == 2
    assert "73%" in fingerprint.product_mix_contexts[0].context
    assert "27%" in fingerprint.product_mix_contexts[0].context


def test_build_attachment_evidence_stays_discovery_only() -> None:
    evidence = q2.build_q2_attachment_evidence(_board(), pdf_bytes=_pdf_bytes())

    assert evidence.pdf_url == "https://cdn.example.test/web/attach/2026q2.pdf"
    assert evidence.discovery_only is True
    assert evidence.product_baseline_eligible is False
    assert evidence.allocation_resolver_registered is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_capture_and_load_reverify_pdf_bytes_and_reject_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    board = _board()
    pdf_bytes = _pdf_bytes()
    monkeypatch.setattr(
        q2,
        "load_board_api_capture",
        lambda pointer_path, *, evaluation_date: board,
    )
    monkeypatch.setattr(
        q2,
        "download_returned_pdf",
        lambda pdf_url, *, timeout_seconds=30.0: pdf_bytes,
    )

    pointer = q2.capture_q2_attachment(
        tmp_path / "board.json",
        evaluation_date=OBSERVED_DATE,
        output=tmp_path / "out",
        captured_at=datetime(2026, 8, 14, 19, 0, tzinfo=UTC),
    )
    pointer_path = tmp_path / "out" / q2.DEFAULT_Q2_ATTACHMENT_POINTER.name
    loaded = q2.load_q2_attachment_evidence(
        pointer_path,
        evaluation_date=OBSERVED_DATE,
    )
    assert loaded.evidence_id == pointer["evidence_id"]

    Path(str(pointer["pdf_path"])).write_bytes(b"not-a-pdf")
    with pytest.raises(ValueError):
        q2.load_q2_attachment_evidence(
            pointer_path,
            evaluation_date=OBSERVED_DATE,
        )
