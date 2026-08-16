from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_table_diagnostics import (
    build_failure_raw_table_signatures,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)


def _spec() -> PeriodicProductRevenueSpec:
    return PeriodicProductRevenueSpec(
        document_id="historical-raw-table-diagnostic-test",
        ticker="000660",
        issuer_name="SK하이닉스",
        source_id="opendart",
        report_name_exact="분기보고서 (2024.03)",
        discovery_begin_date=date(2024, 5, 1),
        discovery_end_date=date(2024, 5, 31),
        period_start=date(2024, 1, 1),
        period_end=date(2024, 3, 31),
        parser_id=HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
        expected_identity_anchors=("DRAM", "NAND", "3개월", "백만원"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND", "NAND Flash"),
            "other_products_services": ("기타", "기타 제품 및 서비스"),
            "reported_company_revenue": ("합계", "매출액 합계", "부문 합계"),
        },
    )


def _archive(html: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.html", html.encode("utf-8"))
    return stream.getvalue()


def _diagnostic(tmp_path: Path, archive_bytes: bytes) -> HistoricalProductRevenueFailureDiagnostic:
    archive_path = tmp_path / "opendart_document.zip"
    archive_path.write_bytes(archive_bytes)
    text = "preserved normalized text"
    text_path = tmp_path / "normalized_document.txt"
    text_path.write_text(text, encoding="utf-8")
    return HistoricalProductRevenueFailureDiagnostic(
        period_id="2024Q1",
        diagnostic_path=str(tmp_path / "diagnostic.json"),
        rcept_no="20240516001638",
        report_name="분기보고서 (2024.03)",
        archive_path=str(archive_path),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        normalized_text_path=str(text_path),
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        error_type="ValueError",
        error="historical parser candidates=0",
    )


def test_raw_table_diagnostics_ignore_market_share_and_capture_verbose_revenue_note(
    tmp_path: Path,
) -> None:
    html = """<html><body>
<p>시장점유율</p>
<table>
<tr><th>구분</th><th>2023년</th></tr>
<tr><td>DRAM</td><td>30%</td></tr>
<tr><td>NAND Flash</td><td>20%</td></tr>
</table>
<p>연결재무제표 주석</p>
<p>22. 매출액(1) 당분기와 전분기 중 매출액의 내역은 다음과 같습니다.</p>
<p>(단위 : 백만원)</p>
<table>
<tr><th>구분</th><th>당분기</th><th>전분기</th></tr>
<tr><th>구분</th><th>3개월</th><th>3개월</th></tr>
<tr><td>DRAM</td><td>100</td><td>80</td></tr>
<tr><td>NAND Flash</td><td>40</td><td>35</td></tr>
<tr><td>기타</td><td>10</td><td>8</td></tr>
<tr><td>합계</td><td>150</td><td>123</td></tr>
</table>
</body></html>"""
    archive_bytes = _archive(html)
    signatures = build_failure_raw_table_signatures(
        _diagnostic(tmp_path, archive_bytes),
        _spec(),
    )

    assert len(signatures) == 1
    signature = signatures[0]
    assert signature.revenue_heading is not None
    assert signature.revenue_heading.startswith("22. 매출액(1)")
    assert signature.connected_heading is False
    assert signature.current_period_markers == ("당분기",)
    assert signature.prior_period_markers == ("전분기",)
    assert signature.unit_markers == ("백만원",)
    assert signature.label_positions["dram_total"] == ((2, 0),)
    assert signature.label_positions["nand_and_solutions"] == ((3, 0),)
    assert signature.label_positions["other_products_services"] == ((4, 0),)
    assert signature.label_positions["reported_company_revenue"] == ((5, 0),)
    assert signature.historical_row_parser_succeeded is False
    assert signature.historical_row_parser_error == (
        "Historical product row table is outside consolidated revenue note"
    )
    assert any("DRAM" in row for row in signature.grid_excerpt)
    assert signature.source_fact_promoted is False


def test_raw_table_diagnostics_capture_split_connected_header_and_revenue_row(
    tmp_path: Path,
) -> None:
    html = """<html><body>
<p>21. 매출액 (연결)</p>
<p>(단위 : 백만원)</p>
<p>당분기</p>
<table>
<tr><th>구분</th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>합계</th></tr>
<tr><th>구분</th><th>3개월</th><th>3개월</th><th>3개월</th><th>3개월</th></tr>
</table>
<table>
<tr><td>수익</td><td>100</td><td>40</td><td>10</td><td>150</td></tr>
</table>
</body></html>"""
    archive_bytes = _archive(html)
    signatures = build_failure_raw_table_signatures(
        _diagnostic(tmp_path, archive_bytes),
        _spec(),
    )

    assert len(signatures) == 2
    assert all(item.connected_heading for item in signatures)
    assert any(item.label_positions["dram_total"] for item in signatures)
    assert any(item.revenue_row_positions for item in signatures)
    assert all(not item.historical_row_parser_succeeded for item in signatures)
    assert all(item.historical_row_parser_error for item in signatures)
    assert all(item.source_fact_promoted is False for item in signatures)
