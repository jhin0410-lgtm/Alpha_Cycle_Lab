from __future__ import annotations

from datetime import date

import pytest

from alpha_cycle.intelligence import sk_hynix_official_ir_q2_product_geometry as geometry
from alpha_cycle.intelligence import sk_hynix_official_ir_q2_share_column_certification as cert

OBSERVED_DATE = date(2026, 8, 15)


def _fragment(text: str, x: float, y: float) -> geometry.TextFragment:
    return geometry.TextFragment(
        page_number=16,
        text=text,
        text_matrix=(1.0, 0.0, 0.0, 1.0, x, y),
        current_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        font_size=1.0,
    )


def _geometry(
    *,
    current_tokens: tuple[str, str] = ("73%", "27%"),
    include_others: bool = True,
    third_column_x: float = 908.6,
) -> geometry.OfficialIrQ2ProductGeometry:
    fragments = [
        _fragment("'25 Q2 '26 Q1 '26 Q2", 436.413, 138.619),
        _fragment("DRAM", 279.708, 189.207),
        _fragment("NAND", 279.708, 231.502),
        _fragment("77%", 449.409, 292.075),
        _fragment("21%", 447.396, 391.976),
        _fragment("78%", 677.842, 399.385),
        _fragment("21%", 677.808, 700.208),
        _fragment(current_tokens[0], third_column_x, 520.396),
        _fragment(current_tokens[1], third_column_x + 0.04, 959.313),
        _fragment(
            "* NAND Revenue by application is based on USD revenue including Solidigm "
            "* Revenue by product portion is based on KRW, Solidigm results consolidated",
            1451.88,
            76.73,
        ),
    ]
    if include_others:
        fragments.insert(3, _fragment("Others", 279.708, 273.796))
    page = geometry.ProductGeometryPage(
        page_number=16,
        width=2559.96,
        height=1440.0,
        fragments=tuple(fragments),
        focus_fragments=tuple(fragments),
    )
    provisional = {
        "source_certification_evidence_id": "b" * 64,
        "observed_date": OBSERVED_DATE.isoformat(),
        "source_url": "https://cdn.example.test/web/attach/q2.pdf",
        "pdf_sha256": "c" * 64,
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
        pdf_sha256="c" * 64,
        pages=(page,),
        readiness_status="geometry_ready_for_semantic_review",
    )


def test_live_geometry_certifies_only_period_column_semantics() -> None:
    result = cert.build_q2_share_column_certification(_geometry())

    assert result.quarter_labels == ("'25 Q2", "'26 Q1", "'26 Q2")
    assert [column.percentage_tokens for column in result.columns] == [
        ("77%", "21%"),
        ("78%", "21%"),
        ("73%", "27%"),
    ]
    assert [column.percentage_sum for column in result.columns] == [98.0, 99.0, 100.0]
    assert result.current_period_label == "'26 Q2"
    assert result.current_column_percentage_tokens == ("73%", "27%")
    assert result.current_column_percentage_sum == 100.0
    assert result.period_column_semantics_certified is True
    assert result.product_assignment_certified is False
    assert result.other_zero_certified is False
    assert result.numeric_semantics_certified is False
    assert result.product_baseline_eligible is False
    assert result.allocation_resolver_registered is False


def test_current_column_sum_does_not_certify_other_zero() -> None:
    result = cert.build_q2_share_column_certification(_geometry())

    assert result.columns[0].percentage_sum == 98.0
    assert result.columns[1].percentage_sum == 99.0
    assert result.columns[2].percentage_sum == 100.0
    assert "Others" in result.product_legend_labels
    assert result.other_zero_certified is False


def test_product_legend_must_retain_others_series() -> None:
    with pytest.raises(ValueError, match="legend is incomplete"):
        cert.build_q2_share_column_certification(_geometry(include_others=False))


def test_current_column_token_drift_fails_closed() -> None:
    with pytest.raises(ValueError, match="product-share tokens drifted"):
        cert.build_q2_share_column_certification(
            _geometry(current_tokens=("72%", "28%"))
        )


def test_column_spacing_drift_fails_closed() -> None:
    with pytest.raises(ValueError, match="spacing drifted"):
        cert.build_q2_share_column_certification(_geometry(third_column_x=1150.0))
