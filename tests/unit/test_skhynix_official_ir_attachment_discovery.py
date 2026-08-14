from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_attachment_discovery as discovery
from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery import (
    DEFAULT_DISCOVERY_POINTER,
    SK_HYNIX_IR_EARNINGS_URL,
    build_official_ir_attachment_discovery_evidence,
    capture_official_ir_attachment_discovery,
    extract_explicit_pdf_urls,
    extract_explicit_script_urls,
    fingerprint_skhynix_2026q2_deck,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_attachment_discovery_verifier import (
    load_official_ir_attachment_discovery_evidence,
)

OFFICIAL_PDF = (
    "https://mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net/"
    "web/attach/12345678901234567.pdf"
)
OFFICIAL_PDF_2 = (
    "https://mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net/"
    "web/attach/22345678901234567.pdf"
)
OFFICIAL_SCRIPT = "https://www.skhynix.com/assets/ir-page.js"


def test_explicit_pdf_extraction_never_promotes_third_party_or_guesses_ids() -> None:
    payload = (
        f'<a href="{OFFICIAL_PDF}">official</a>'
        '<a href="https://files.example.com/web/attach/999.pdf">third party</a>'
        '<span>/web/attach/77777777777777777.pdf</span>'
        '<span>attachment id 88888888888888888</span>'
    ).encode()
    urls = extract_explicit_pdf_urls(payload, base_url=SK_HYNIX_IR_EARNINGS_URL)
    assert OFFICIAL_PDF in urls
    assert "https://www.skhynix.com/web/attach/77777777777777777.pdf" in urls
    assert all("files.example.com" not in item for item in urls)
    assert all("88888888888888888" not in item for item in urls)


def test_script_extraction_stays_on_issuer_controlled_resources() -> None:
    page = (
        b'<script src="/assets/ir-page.js"></script>'
        b'<script src="https://cdn.example.com/foreign.js"></script>'
        b'<script src="/assets/not-javascript.css"></script>'
    )
    assert extract_explicit_script_urls(page) == (OFFICIAL_SCRIPT,)


def test_pinned_q2_deck_fingerprint_requires_product_share_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [""] * 19
    pages[0] = "2026.07.29 Investor Relations FY2026 Earnings"
    pages[8] = "Q3 B/G : Approx. 10% increase QoQ"
    pages[9] = "Began HBM4 shipment in Q2"
    pages[15] = (
        "Revenue by Product Revenue by Application Revenue 79,319 "
        "DRAM 73% NAND 27%"
    )
    monkeypatch.setattr(discovery, "extract_pdf_pages", lambda data: tuple(pages))
    matched, page_count, reason = fingerprint_skhynix_2026q2_deck(b"%PDF-test")
    assert matched is True
    assert page_count == 19
    assert "matched pinned" in reason

    pages[15] = "Revenue by Product Revenue by Application Revenue 79,319 DRAM 73% NAND"
    matched, _, reason = fingerprint_skhynix_2026q2_deck(b"%PDF-test")
    assert matched is False
    assert "27%" in reason


def test_one_explicit_matching_official_pdf_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = (
        f'<script src="{OFFICIAL_SCRIPT}"></script>'
        f'<a href="{OFFICIAL_PDF}">deck</a>'
    ).encode()
    monkeypatch.setattr(
        discovery,
        "fingerprint_skhynix_2026q2_deck",
        lambda data: (data == b"%PDF-match", 19, "test fingerprint"),
    )
    evidence = build_official_ir_attachment_discovery_evidence(
        observed_date=date(2026, 8, 15),
        page_bytes=page,
        script_bytes_by_url={OFFICIAL_SCRIPT: b"console.log('ir')"},
        pdf_bytes_by_url={OFFICIAL_PDF: b"%PDF-match"},
    )
    assert evidence.resolved is True
    assert evidence.resolved_url == OFFICIAL_PDF
    assert evidence.resolved_pdf_sha256 is not None
    assert evidence.product_baseline_eligible is False
    assert evidence.allocation_resolver_registered is False


def test_multiple_matching_official_pdfs_remain_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = (
        f'<a href="{OFFICIAL_PDF}">deck1</a>'
        f'<a href="{OFFICIAL_PDF_2}">deck2</a>'
    ).encode()
    monkeypatch.setattr(
        discovery,
        "fingerprint_skhynix_2026q2_deck",
        lambda data: (True, 19, "test fingerprint"),
    )
    evidence = build_official_ir_attachment_discovery_evidence(
        observed_date=date(2026, 8, 15),
        page_bytes=page,
        script_bytes_by_url={},
        pdf_bytes_by_url={
            OFFICIAL_PDF: b"%PDF-one",
            OFFICIAL_PDF_2: b"%PDF-two",
        },
    )
    assert evidence.resolved is False
    assert evidence.resolved_url is None
    assert sum(item.fingerprint_match for item in evidence.candidates) == 2


def test_capture_and_verifier_reject_archived_pdf_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = (
        f'<script src="{OFFICIAL_SCRIPT}"></script>'
        f'<a href="{OFFICIAL_PDF}">deck</a>'
    ).encode()
    resources = {
        SK_HYNIX_IR_EARNINGS_URL: page,
        OFFICIAL_SCRIPT: b"console.log('ir')",
        OFFICIAL_PDF: b"%PDF-match",
    }

    def fake_download(url: str, *, timeout_seconds: float = 20.0) -> bytes:
        assert timeout_seconds == 20.0
        return resources[url]

    monkeypatch.setattr(discovery, "download_issuer_resource", fake_download)
    monkeypatch.setattr(
        discovery,
        "fingerprint_skhynix_2026q2_deck",
        lambda data: (data == b"%PDF-match", 19, "test fingerprint"),
    )
    pointer = capture_official_ir_attachment_discovery(
        observed_date=date(2026, 8, 15),
        output=tmp_path,
        captured_at=datetime(2026, 8, 14, 18, 0, tzinfo=UTC),
    )
    pointer_path = tmp_path / DEFAULT_DISCOVERY_POINTER.name
    loaded = load_official_ir_attachment_discovery_evidence(
        pointer_path,
        evaluation_date=date(2026, 8, 15),
    )
    assert loaded.resolved is True
    artifact_directory = Path(str(pointer["artifact_directory"]))
    (artifact_directory / "candidate_01.pdf").write_bytes(b"%PDF-tampered")
    with pytest.raises(ValueError, match="does not reproduce"):
        load_official_ir_attachment_discovery_evidence(
            pointer_path,
            evaluation_date=date(2026, 8, 15),
        )
