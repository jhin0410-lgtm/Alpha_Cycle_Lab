from __future__ import annotations

import io
import zipfile

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_table import (
    parse_periodic_product_revenue_archive,
)

DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


def _archive(*, current: str = "당분기", duplicate_current: bool = False) -> bytes:
    second_group = current if duplicate_current else "전분기"
    markup = f"""
    <html><body>
      <p>(단위 : 백만원)</p>
      <table>
        <tr>
          <th rowspan="2">구분</th>
          <th colspan="2">{current}</th>
          <th colspan="2">{second_group}</th>
        </tr>
        <tr><th>3개월</th><th>누적</th><th>3개월</th><th>누적</th></tr>
        <tr><td>DRAM</td><td>730</td><td>1,400</td><td>600</td><td>1,100</td></tr>
        <tr><td>NAND</td><td>260</td><td>500</td><td>300</td><td>550</td></tr>
        <tr><td>기타</td><td>10</td><td>20</td><td>10</td><td>20</td></tr>
        <tr><td>합계</td><td>1,000</td><td>1,920</td><td>910</td><td>1,670</td></tr>
      </table>
    </body></html>
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", markup)
    return buffer.getvalue()


def test_structural_parser_accepts_explicit_quarter_period_header_variant() -> None:
    spec = load_periodic_product_revenue_registry()[DOCUMENT_ID]
    metrics = parse_periodic_product_revenue_archive(spec, _archive())
    assert metrics.dram_total == 730
    assert metrics.nand_and_solutions == 260
    assert metrics.other_products_services == 10
    assert metrics.reported_company_revenue == 1_000
    assert metrics.reconciliation_delta == 0


def test_structural_parser_accepts_explicit_half_year_header_variant() -> None:
    spec = load_periodic_product_revenue_registry()[DOCUMENT_ID]
    metrics = parse_periodic_product_revenue_archive(spec, _archive(current="당반기"))
    assert metrics.reported_company_revenue == 1_000


def test_structural_parser_rejects_ambiguous_current_three_month_columns() -> None:
    spec = load_periodic_product_revenue_registry()[DOCUMENT_ID]
    with pytest.raises(ValueError, match="resolve uniquely"):
        parse_periodic_product_revenue_archive(
            spec,
            _archive(duplicate_current=True),
        )
