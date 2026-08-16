from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
    parse_historical_product_revenue_archive_fallback,
    parse_historical_product_revenue_text_fallback,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_archive,
    parse_periodic_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)


def _spec(*, q1: bool) -> PeriodicProductRevenueSpec:
    year = 2024
    report_name = "분기보고서 (2024.03)" if q1 else "반기보고서 (2024.06)"
    period_end = date(year, 3, 31) if q1 else date(year, 6, 30)
    period_start = date(year, 1, 1) if q1 else date(year, 4, 1)
    return PeriodicProductRevenueSpec(
        document_id="historical-test",
        ticker="000660",
        issuer_name="SK하이닉스",
        source_id="opendart",
        report_name_exact=report_name,
        discovery_begin_date=period_end,
        discovery_end_date=date(year, 8, 31),
        period_start=period_start,
        period_end=period_end,
        parser_id=HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
        expected_identity_anchors=(
            "SK하이닉스",
            report_name,
            "(연결)",
            "DRAM",
            "NAND Flash",
            "기타",
            "3개월",
            "백만원",
        ),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND Flash",),
            "other_products_services": ("기타",),
            "reported_company_revenue": ("부문 합계", "합계"),
        },
    )


def _row_html(*, q1: bool, total: str = "150") -> str:
    report_name = "분기보고서 (2024.03)" if q1 else "반기보고서 (2024.06)"
    if q1:
        header = """
<tr><th>구분</th><th>당분기</th><th>전분기</th></tr>
<tr><th>구분</th><th>3개월</th><th>3개월</th></tr>
"""
        rows = f"""
<tr><td>DRAM</td><td>100</td><td>80</td></tr>
<tr><td>NAND Flash</td><td>40</td><td>35</td></tr>
<tr><td>기타</td><td>10</td><td>8</td></tr>
<tr><td>합계</td><td>{total}</td><td>123</td></tr>
"""
    else:
        header = """
<tr><th>구분</th><th>당반기</th><th>당반기</th><th>전반기</th></tr>
<tr><th>구분</th><th>3개월</th><th>누적</th><th>3개월</th></tr>
"""
        rows = f"""
<tr><td>DRAM</td><td>100</td><td>300</td><td>80</td></tr>
<tr><td>NAND Flash</td><td>40</td><td>120</td><td>35</td></tr>
<tr><td>기타</td><td>10</td><td>30</td><td>8</td></tr>
<tr><td>합계</td><td>{total}</td><td>450</td><td>123</td></tr>
"""
    return f"""<html><body>
<p>SK하이닉스</p><p>{report_name}</p>
<p>21. 매출액 (연결)</p><p>(단위: 백만원)</p>
<table>{header}{rows}</table>
</body></html>"""


def _normalized_text(*, q1: bool, total: str = "150") -> str:
    report_name = "분기보고서 (2024.03)" if q1 else "반기보고서 (2024.06)"
    if q1:
        header = ["구분", "당분기", "전분기", "구분", "3개월", "3개월"]
        rows = [
            "DRAM",
            "100",
            "80",
            "NAND Flash",
            "40",
            "35",
            "기타",
            "10",
            "8",
            "합계",
            total,
            "123",
        ]
    else:
        header = [
            "구분",
            "당반기",
            "당반기",
            "전반기",
            "구분",
            "3개월",
            "누적",
            "3개월",
        ]
        rows = [
            "DRAM",
            "100",
            "300",
            "80",
            "NAND Flash",
            "40",
            "120",
            "35",
            "기타",
            "10",
            "30",
            "8",
            "합계",
            total,
            "450",
            "123",
        ]
    return "\n".join(
        [
            "SK하이닉스",
            report_name,
            "21. 매출액 (연결)",
            "(단위: 백만원)",
            *header,
            *rows,
        ]
    )


def _archive(html: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.html", html.encode("utf-8"))
    return stream.getvalue()


@pytest.mark.parametrize("q1", [False, True])
def test_historical_row_family_replays_same_direct_values_from_text_and_raw(q1: bool) -> None:
    spec = _spec(q1=q1)
    expected = (100.0, 40.0, 10.0, 150.0)

    text_metrics = parse_historical_product_revenue_text_fallback(
        spec,
        _normalized_text(q1=q1),
    )
    raw_metrics = parse_historical_product_revenue_archive_fallback(
        spec,
        _archive(_row_html(q1=q1)),
    )

    assert (
        text_metrics.dram_total,
        text_metrics.nand_and_solutions,
        text_metrics.other_products_services,
        text_metrics.reported_company_revenue,
    ) == expected
    assert raw_metrics == text_metrics


@pytest.mark.parametrize("q1", [False, True])
def test_production_dispatch_uses_historical_family_when_current_layout_does_not(q1: bool) -> None:
    spec = _spec(q1=q1)
    text_metrics = parse_periodic_product_revenue_text(spec, _normalized_text(q1=q1))
    raw_metrics = parse_periodic_product_revenue_archive(
        spec,
        _archive(_row_html(q1=q1)),
    )
    assert raw_metrics == text_metrics
    assert raw_metrics.direct_sum == 150.0
    assert raw_metrics.reconciliation_delta == 0.0


def test_historical_family_rejects_direct_rows_that_do_not_reconcile() -> None:
    spec = _spec(q1=False)
    with pytest.raises(ValueError, match="resolve uniquely|do not reconcile"):
        parse_historical_product_revenue_text_fallback(
            spec,
            _normalized_text(q1=False, total="151"),
        )
    with pytest.raises(ValueError, match="resolve uniquely"):
        parse_historical_product_revenue_archive_fallback(
            spec,
            _archive(_row_html(q1=False, total="151")),
        )


def test_historical_fallback_refuses_unbound_parser_id() -> None:
    spec = _spec(q1=False)
    unbound = PeriodicProductRevenueSpec(
        **{**spec.__dict__, "parser_id": "different_parser"}
    )
    with pytest.raises(ValueError, match="Unsupported historical"):
        parse_historical_product_revenue_text_fallback(
            unbound,
            _normalized_text(q1=False),
        )
