from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_source_closure import (
    build_product_revenue_source_closure,
)


def _archive(html: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("filing.xml", html)
    return buffer.getvalue()


def _diagnostic(tmp_path: Path, archive_bytes: bytes) -> HistoricalProductRevenueFailureDiagnostic:
    archive_path = tmp_path / "source.zip"
    text_path = tmp_path / "normalized.txt"
    archive_path.write_bytes(archive_bytes)
    text_path.write_text("fixture", encoding="utf-8")
    return HistoricalProductRevenueFailureDiagnostic(
        period_id="2022Q2",
        diagnostic_path=str(tmp_path / "diagnostic.json"),
        rcept_no="20220816001536",
        report_name="반기보고서 (2022.06)",
        archive_path=str(archive_path),
        archive_sha256=hashlib.sha256(archive_bytes).hexdigest(),
        normalized_text_path=str(text_path),
        text_sha256=hashlib.sha256(b"fixture").hexdigest(),
        error_type="ValueError",
        error="fixture parse failure",
        receipt_date=date(2022, 8, 16),
        source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20220816001536",
        retrieved_at=datetime(2026, 8, 17, tzinfo=UTC),
        text_truncated=False,
        archive_bytes=len(archive_bytes),
        text_chars=len("fixture"),
    )


def test_source_closure_identifies_aggregate_bucket_without_allocation(tmp_path: Path) -> None:
    html = """
    <html><body>
    <p>2. 주요 제품 및 서비스</p><p>가. 주요 제품 등의 현황</p>
    <p>(단위 : 백만원)</p>
    <table>
      <tr><th>구분</th><th>주요 제품</th><th>매출액</th></tr>
      <tr><td>제품 외</td><td>DRAM, NAND Flash, CIS 등</td><td>25,966,654</td></tr>
    </table>
    </body></html>
    """
    result = build_product_revenue_source_closure(_diagnostic(tmp_path, _archive(html)))

    assert result.aggregate_bucket_witness_count == 1
    assert result.direct_separable_candidate_count == 0
    assert result.layout_fallback_count == 0
    assert result.aggregate_only_observed is True
    assert result.aggregate_bucket_witnesses[0].layout_mode == "structured_grid"
    assert result.direct_product_revenue_certified is False
    assert result.synthetic_product_allocation_allowed is False
    assert result.training_row_promoted is False
    assert result.fit_enabled is False


def test_source_closure_surfaces_direct_candidate_but_does_not_certify(tmp_path: Path) -> None:
    html = """
    <html><body>
    <p>매출액 제품별 현황</p><p>(단위 : 백만원)</p>
    <table>
      <tr><th>제품</th><th>매출액</th></tr>
      <tr><td>DRAM</td><td>7,000</td></tr>
      <tr><td>NAND Flash</td><td>3,000</td></tr>
    </table>
    </body></html>
    """
    result = build_product_revenue_source_closure(_diagnostic(tmp_path, _archive(html)))

    assert result.direct_separable_candidate_count == 1
    assert result.aggregate_only_observed is False
    assert result.direct_separable_candidates[0].direct_labeled_amount_row_count == 2
    assert result.direct_separable_candidates[0].layout_mode == "structured_grid"
    assert result.direct_product_revenue_certified is False
    assert result.synthetic_product_allocation_allowed is False


def test_source_closure_falls_back_on_rowspan_colspan_overlap(tmp_path: Path) -> None:
    html = """
    <html><body>
    <p>주요 제품 매출액 현황</p><p>(단위 : 백만원)</p>
    <table>
      <tr><td>제품</td><td rowspan="2">매출액</td><td>구분</td></tr>
      <tr><td colspan="2">DRAM, NAND Flash, CIS 등</td><td>25,966,654</td></tr>
    </table>
    </body></html>
    """
    result = build_product_revenue_source_closure(_diagnostic(tmp_path, _archive(html)))

    assert result.layout_fallback_count == 1
    assert len(result.layout_fallback_errors) == 1
    assert "overlaps an active rowspan" in result.layout_fallback_errors[0]
    assert result.aggregate_bucket_witness_count == 1
    assert result.aggregate_bucket_witnesses[0].layout_mode == "flat_cell_sequence_fallback"
    assert result.exhaustive_preserved_archive_scan_complete is True
    assert result.direct_product_revenue_certified is False
    assert result.synthetic_product_allocation_allowed is False
