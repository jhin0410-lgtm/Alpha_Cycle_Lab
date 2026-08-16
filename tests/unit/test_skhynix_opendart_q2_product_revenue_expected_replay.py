from __future__ import annotations

import io
import zipfile

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_expected_replay import (
    parse_periodic_product_revenue_archive,
)

_DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


def _archive() -> bytes:
    html = """
    <html><body>
      <h1>반기보고서 (2026.06)</h1>
      <h3>21. 매출액 (연결)</h3>
      <p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>
      <p>당반기</p><p>(단위 : 백만원)</p>
      <table>
        <tr>
          <th rowspan="2">부문</th>
          <th colspan="2">DRAM</th>
          <th colspan="2">NAND Flash</th>
          <th colspan="2">기타</th>
          <th colspan="2">부문 합계</th>
        </tr>
        <tr>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
          <th>3개월</th><th>누적</th>
        </tr>
      </table>
      <p>전반기</p>
      <p>수익</p>
      <table><tr>
        <td>56,982,743</td><td>97,641,379</td>
        <td>21,959,898</td><td>33,534,133</td>
        <td>376,105</td><td>719,521</td>
        <td>79,318,746</td><td>131,895,033</td>
      </tr></table>
    </body></html>
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", html)
    return buffer.getvalue()


def test_expected_replay_uses_structural_current_period_not_latest_raw_marker() -> None:
    spec = load_periodic_product_revenue_registry()[_DOCUMENT_ID]
    metrics = parse_periodic_product_revenue_archive(spec, _archive())

    assert metrics.dram_total == 56_982_743
    assert metrics.nand_and_solutions == 21_959_898
    assert metrics.other_products_services == 376_105
    assert metrics.reported_company_revenue == 79_318_746
    assert metrics.reconciliation_delta == 0
