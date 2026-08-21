from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v5 import (
    parse_historical_product_revenue_archive_v5,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_archive,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)


def _spec(period: str = "2016Q1") -> PeriodicProductRevenueSpec:
    if period == "2016Q1":
        start, end = date(2016, 1, 1), date(2016, 3, 31)
        report = "분기보고서 (2016.03)"
    elif period == "2016Q2":
        start, end = date(2016, 4, 1), date(2016, 6, 30)
        report = "반기보고서 (2016.06)"
    elif period == "2021Q1":
        start, end = date(2021, 1, 1), date(2021, 3, 31)
        report = "분기보고서 (2021.03)"
    else:  # pragma: no cover - helper guard
        raise AssertionError(period)
    return PeriodicProductRevenueSpec(
        document_id=f"skhynix_{period.casefold()}_layout_v5_test",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact=report,
        discovery_begin_date=date(end.year, end.month + 1 if end.month < 12 else 12, 1),
        discovery_end_date=date(end.year, min(end.month + 2, 12), 28),
        period_start=start,
        period_end=end,
        parser_id="skhynix_opendart_periodic_product_revenue_v1",
        expected_identity_anchors=("DRAM", "NAND", "3개월", "백만원"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND", "NAND Flash"),
            "other_products_services": ("기타", "기타 제품 및 서비스"),
            "reported_company_revenue": ("합계", "합 계", "매출액 합계"),
        },
    )


def _zip(html: str, *, member: str = "20160516001896.xml") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, html)
    return output.getvalue()


def _q1_html(*, marker: bool = True, ambiguous_current: bool = False) -> str:
    context = (
        "<p>(2) 당분기와 전분기 중 매출액의 품목별 세부내역은 다음과 같습니다.</p>"
        if marker
        else "<p>(2) 당분기와 전분기 중 주요 영업 내역은 다음과 같습니다.</p>"
    )
    extra = "<th>당기</th>" if ambiguous_current else ""
    extra_values = "<td>2,766,614</td>" if ambiguous_current else ""
    extra_nand = "<td>778,961</td>" if ambiguous_current else ""
    extra_other = "<td>110,142</td>" if ambiguous_current else ""
    extra_total = "<td>3,655,717</td>" if ambiguous_current else ""
    return f"""
    <html><body>
      <p>연결재무제표 주석</p>
      {context}
      <p>(단위: 백만원)</p>
      <table>
        <tr><th>구 분</th><th>당분기</th>{extra}<th>전분기</th></tr>
        <tr><td>DRAM</td><td>2,766,614</td>{extra_values}<td>3,632,987</td></tr>
        <tr><td>NAND Flash</td><td>778,961</td>{extra_nand}<td>1,044,841</td></tr>
        <tr><td>기 타</td><td>110,142</td>{extra_other}<td>140,513</td></tr>
        <tr><td>합 계</td><td>3,655,717</td>{extra_total}<td>4,818,341</td></tr>
      </table>
    </body></html>
    """


def _q2_html() -> str:
    return """
    <html><body>
      <p>연결재무제표 주석</p>
      <p>(2) 당반기와 전반기 중 매출액의 품목별 세부내역은 다음과 같습니다.</p>
      <p>(단위: 백만원)</p>
      <table>
        <tr>
          <th>구 분</th>
          <th>당반기 3개월</th><th>당반기 누적</th>
          <th>전반기 3개월</th><th>전반기 누적</th>
        </tr>
        <tr><td>DRAM</td><td>60</td><td>120</td><td>55</td><td>110</td></tr>
        <tr><td>NAND Flash</td><td>30</td><td>60</td><td>25</td><td>50</td></tr>
        <tr><td>기 타</td><td>10</td><td>20</td><td>10</td><td>20</td></tr>
        <tr><td>합 계</td><td>100</td><td>200</td><td>90</td><td>180</td></tr>
      </table>
    </body></html>
    """


def test_2016_q1_local_detail_context_uses_direct_current_period_rows() -> None:
    metrics = parse_historical_product_revenue_archive_v5(_spec("2016Q1"), _zip(_q1_html()))

    assert metrics.dram_total == 2_766_614.0
    assert metrics.nand_and_solutions == 778_961.0
    assert metrics.other_products_services == 110_142.0
    assert metrics.reported_company_revenue == 3_655_717.0
    assert metrics.reconciliation_delta == 0.0


def test_dispatch_normalizes_receipt_root_member_before_2016_layout() -> None:
    metrics = parse_periodic_product_revenue_archive(
        _spec("2016Q1"),
        _zip(_q1_html(), member="/20160516001896.xml"),
    )

    assert metrics.reported_company_revenue == 3_655_717.0


def test_2016_q2_reads_only_unique_current_three_month_column() -> None:
    metrics = parse_historical_product_revenue_archive_v5(_spec("2016Q2"), _zip(_q2_html()))

    assert metrics.dram_total == 60.0
    assert metrics.nand_and_solutions == 30.0
    assert metrics.other_products_services == 10.0
    assert metrics.reported_company_revenue == 100.0


def test_product_rows_without_local_product_detail_context_are_rejected() -> None:
    with pytest.raises(ValueError, match="must resolve uniquely: candidates=0"):
        parse_historical_product_revenue_archive_v5(
            _spec("2016Q1"),
            _zip(_q1_html(marker=False)),
        )


def test_2016_q1_ambiguous_current_columns_are_rejected() -> None:
    with pytest.raises(ValueError, match="must resolve uniquely: candidates=0"):
        parse_historical_product_revenue_archive_v5(
            _spec("2016Q1"),
            _zip(_q1_html(ambiguous_current=True)),
        )


def test_layout_v5_cannot_apply_to_frozen_2021_period() -> None:
    with pytest.raises(ValueError, match="limited to observed 2016 Q1/Q2"):
        parse_historical_product_revenue_archive_v5(
            _spec("2021Q1"),
            _zip(_q1_html()),
        )
