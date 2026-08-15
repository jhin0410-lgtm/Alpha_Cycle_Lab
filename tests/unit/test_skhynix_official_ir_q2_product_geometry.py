from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_geometry as geometry

OBSERVED_DATE = date(2026, 8, 15)
PDF_BYTES = b"official-pdf"


def _certification() -> SimpleNamespace:
    import hashlib

    return SimpleNamespace(
        evidence_id="a" * 64,
        observed_date=OBSERVED_DATE,
        source_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256=hashlib.sha256(PDF_BYTES).hexdigest(),
        readiness_status="layout_ready_for_contract_review",
        document_identity_verified=True,
        source_published_date_verified=True,
        product_layout_pages=(SimpleNamespace(page_number=16),),
    )


def _page() -> geometry.ProductGeometryPage:
    fragment = geometry.TextFragment(
        page_number=16,
        text="73%",
        text_matrix=(1.0, 0.0, 0.0, 1.0, 120.0, 300.0),
        current_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_size=10.0,
    )
    return geometry.ProductGeometryPage(
        page_number=16,
        width=612.0,
        height=792.0,
        fragments=(fragment,),
        focus_fragments=(fragment,),
    )


def test_focus_detection_keeps_review_tokens_without_pairing() -> None:
    assert geometry._is_focus_text("DRAM") is True
    assert geometry._is_focus_text("NAND") is True
    assert geometry._is_focus_text("'26 Q2") is True
    assert geometry._is_focus_text("73%") is True
    assert geometry._is_focus_text("79,319") is True
    assert geometry._is_focus_text("ordinary prose") is False


def test_build_geometry_stays_non_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        geometry,
        "_extract_geometry_pages",
        lambda pdf_bytes, *, page_numbers: (_page(),),
    )
    result = geometry.build_q2_product_geometry(
        _certification(),
        pdf_bytes=PDF_BYTES,
    )

    assert result.readiness_status == "geometry_ready_for_semantic_review"
    assert result.pages[0].focus_fragments[0].text == "73%"
    assert result.numeric_semantics_certified is False
    assert result.registry_write_eligible is False
    assert result.product_baseline_eligible is False
    assert result.allocation_resolver_registered is False
    assert not hasattr(result, "dram_share")
    assert not hasattr(result, "nand_share")


def test_geometry_requires_certified_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    certification = _certification()
    certification.readiness_status = "publication_date_unresolved"
    monkeypatch.setattr(
        geometry,
        "_extract_geometry_pages",
        lambda pdf_bytes, *, page_numbers: (_page(),),
    )
    with pytest.raises(ValueError, match="not ready"):
        geometry.build_q2_product_geometry(certification, pdf_bytes=PDF_BYTES)
