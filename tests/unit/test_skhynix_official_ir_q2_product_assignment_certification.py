from __future__ import annotations

import hashlib
from datetime import date

import pytest

from alpha_cycle.intelligence import (
    sk_hynix_official_ir_q2_product_assignment_certification as assignment,
)
from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_geometry as geometry
from alpha_cycle.intelligence import sk_hynix_official_ir_q2_share_column_certification as share

OBSERVED_DATE = date(2026, 8, 15)
PDF_BYTES = b"%PDF-fixture-for-vector-assignment"
PDF_SHA256 = hashlib.sha256(PDF_BYTES).hexdigest()


def _fragment(text: str, x: float, y: float) -> geometry.TextFragment:
    return geometry.TextFragment(
        page_number=16,
        text=text,
        text_matrix=(1.0, 0.0, 0.0, 1.0, x, y),
        current_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_size=1.0,
    )


def _geometry() -> geometry.OfficialIrQ2ProductGeometry:
    fragments = (
        _fragment("'25 Q2 '26 Q1 '26 Q2", 436.413, 138.619),
        _fragment("DRAM", 279.708, 189.207),
        _fragment("NAND", 279.708, 231.502),
        _fragment("Others", 279.708, 273.796),
        _fragment("77%", 449.409, 292.075),
        _fragment("21%", 447.396, 391.976),
        _fragment("78%", 677.842, 399.385),
        _fragment("21%", 677.808, 700.208),
        _fragment("73%", 908.635, 520.396),
        _fragment("27%", 908.675, 959.313),
        _fragment(
            "* Revenue by product portion is based on KRW, Solidigm results consolidated",
            1451.88,
            76.73,
        ),
    )
    page = geometry.ProductGeometryPage(
        page_number=16,
        width=2559.96,
        height=1440.0,
        fragments=fragments,
        focus_fragments=fragments,
    )
    provisional = {
        "source_certification_evidence_id": "b" * 64,
        "observed_date": OBSERVED_DATE.isoformat(),
        "source_url": "https://cdn.example.test/web/attach/q2.pdf",
        "pdf_sha256": PDF_SHA256,
        "pages": [geometry._page_payload(page)],
        "readiness_status": "geometry_ready_for_semantic_review",
        "numeric_semantics_certified": False,
        "registry_write_eligible": False,
        "product_baseline_eligible": False,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return geometry.OfficialIrQ2ProductGeometry(
        evidence_id=geometry._sha_payload(provisional),
        source_certification_evidence_id="b" * 64,
        observed_date=OBSERVED_DATE,
        source_url="https://cdn.example.test/web/attach/q2.pdf",
        pdf_sha256=PDF_SHA256,
        pages=(page,),
        readiness_status="geometry_ready_for_semantic_review",
    )


def _rectangles() -> tuple[assignment.PaintedRectangle, ...]:
    gray = assignment.FillStyle("gray", (0.749,))
    red = assignment.FillStyle("rgb", (0.89, 0.098, 0.216))
    orange = assignment.FillStyle("rgb", (0.961, 0.502, 0.145))
    return (
        assignment.PaintedRectangle(265.2, 284.28, 9.96, -9.96, gray),
        assignment.PaintedRectangle(265.2, 241.92, 9.96, -9.96, red),
        assignment.PaintedRectangle(265.2, 199.68, 9.96, -9.96, orange),
        assignment.PaintedRectangle(879.96, 841.92, 114.84, -663.72, orange),
        assignment.PaintedRectangle(879.96, 1083.48, 114.84, -241.56, red),
        assignment.PaintedRectangle(879.96, 1088.52, 114.84, -5.04, gray),
    )


def _inputs() -> tuple[
    share.OfficialIrQ2ShareColumnCertification,
    geometry.OfficialIrQ2ProductGeometry,
]:
    geometry_item = _geometry()
    return share.build_q2_share_column_certification(geometry_item), geometry_item


def test_vector_colours_certify_dram_73_and_nand_27_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    share_item, geometry_item = _inputs()
    rectangles = _rectangles()
    monkeypatch.setattr(
        assignment,
        "_painted_rectangles",
        lambda pdf_bytes, *, page_number: rectangles,
    )

    result = assignment.build_q2_product_assignment_certification(
        share_item,
        geometry_item,
        pdf_bytes=PDF_BYTES,
    )

    assert result.product_assignment_certified is True
    assert result.dram_nand_share_semantics_certified is True
    assert result.dram_share_percent == 73.0
    assert result.nand_share_percent == 27.0
    assert result.others_segment_present is True
    assert result.other_share_percent is None
    assert result.other_zero_certified is False
    assert result.numeric_semantics_certified is False
    assert result.registry_write_eligible is False
    assert result.product_baseline_eligible is False
    assert result.allocation_resolver_registered is False


def test_dram_token_must_be_inside_dram_legend_colour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    share_item, geometry_item = _inputs()
    rectangles = list(_rectangles())
    rectangles[3] = assignment.PaintedRectangle(
        879.96,
        841.92,
        114.84,
        -663.72,
        assignment.FillStyle("rgb", (0.89, 0.098, 0.216)),
    )
    monkeypatch.setattr(
        assignment,
        "_painted_rectangles",
        lambda pdf_bytes, *, page_number: tuple(rectangles),
    )

    with pytest.raises(ValueError, match="DRAM token is not uniquely inside"):
        assignment.build_q2_product_assignment_certification(
            share_item,
            geometry_item,
            pdf_bytes=PDF_BYTES,
        )


def test_visible_others_segment_cannot_be_erased_into_other_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    share_item, geometry_item = _inputs()
    rectangles = _rectangles()[:-1]
    monkeypatch.setattr(
        assignment,
        "_painted_rectangles",
        lambda pdf_bytes, *, page_number: rectangles,
    )

    with pytest.raises(ValueError, match="Others display segment is not uniquely verified"):
        assignment.build_q2_product_assignment_certification(
            share_item,
            geometry_item,
            pdf_bytes=PDF_BYTES,
        )
