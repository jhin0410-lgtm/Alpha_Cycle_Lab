from __future__ import annotations

import io
import zipfile

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_semantic_replay import (
    parse_periodic_product_revenue_archive,
)

DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


def _spec():
    return load_periodic_product_revenue_registry()[DOCUMENT_ID]


def _header_table() -> str:
    return """
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
    """


def _data_table(*, total: str = "79,318,746") -> str:
    return f"""
    <table>
      <tr>
        <td>수익</td>
        <td>56,982,743</td><td>97,641,379</td>
        <td>21,959,898</td><td>33,534,133</td>
        <td>376,105</td><td>719,521</td>
        <td>{total}</td><td>131,895,033</td>
      </tr>
    </table>
    """


def _archive(*, include_separate: bool = True, bad_total: bool = False) -> bytes:
    parts = [
        "<html><body>",
        "<h1>반기보고서 (2026.06)</h1>",
        "<h3>21. 매출액 (연결)</h3>",
        "<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>",
        "<p>당반기</p><p>(단위 : 백만원)</p>",
        _header_table(),
        "<table><tr><td>helper-layout-a</td></tr></table>",
        "<table><tr><td>helper-layout-b</td></tr></table>",
        "<table><tr><td>helper-layout-c</td></tr></table>",
        _data_table(total="79,318,745" if bad_total else "79,318,746"),
        "<p>전반기</p>",
    ]
    if include_separate:
        parts.extend(
            [
                "<h3>20. 매출액</h3>",
                "<p>당반기</p><p>(단위 : 백만원)</p>",
                _header_table(),
                _data_table(total="79,318,746"),
            ]
        )
    parts.append("</body></html>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", "".join(parts))
    return buffer.getvalue()


def test_semantic_replay_binds_nonadjacent_live_2026_header_and_data_tables() -> None:
    metrics = parse_periodic_product_revenue_archive(_spec(), _archive())

    assert metrics.dram_total == 56_982_743
    assert metrics.nand_and_solutions == 21_959_898
    assert metrics.other_products_services == 376_105
    assert metrics.reported_company_revenue == 79_318_746
    assert metrics.direct_sum == 79_318_746
    assert metrics.reconciliation_delta == 0


def test_semantic_replay_excludes_standalone_revenue_note() -> None:
    metrics = parse_periodic_product_revenue_archive(
        _spec(),
        _archive(include_separate=True),
    )
    assert metrics.reported_company_revenue == 79_318_746


def test_semantic_replay_fails_closed_when_direct_amounts_do_not_reconcile() -> None:
    with pytest.raises(ValueError, match="resolve uniquely"):
        parse_periodic_product_revenue_archive(
            _spec(),
            _archive(include_separate=False, bad_total=True),
        )
