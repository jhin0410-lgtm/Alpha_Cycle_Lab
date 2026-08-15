from __future__ import annotations

import io
import zipfile

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    load_periodic_product_revenue_registry,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_layout import (
    parse_periodic_product_revenue_archive,
    parse_periodic_product_revenue_text,
)

DOCUMENT_ID = "skhynix_000660_2026q2_half_year_product_revenue"


def _spec():
    return load_periodic_product_revenue_registry()[DOCUMENT_ID]


def _normalized_text() -> str:
    # Shape and historical values mirror SK hynix's official 2025 half-year filing.
    return "\n".join(
        [
            "반기보고서 (2026.06)",
            "21. 매출액 (연결)",
            "고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시",
            "당반기",
            "(단위 : 백만원)",
            "부문",
            "부문 합계",
            "DRAM",
            "NAND Flash",
            "기타",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "수익(매출액)",
            "17,123,990",
            "31,160,860",
            "4,727,806",
            "7,956,641",
            "380,156",
            "753,592",
            "22,231,952",
            "39,871,093",
            "전반기",
            "(단위 : 백만원)",
            "부문",
            "부문 합계",
            "DRAM",
            "NAND Flash",
            "기타",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "수익(매출액)",
            "10,700,356",
            "18,193,804",
            "5,184,707",
            "9,591,920",
            "538,195",
            "1,067,132",
            "16,423,258",
            "28,852,856",
            "20. 매출액",
            "고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시",
            "당반기",
            "(단위 : 백만원)",
            "부문",
            "부문 합계",
            "DRAM",
            "NAND Flash",
            "기타",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "수익(매출액)",
            "16,573,043",
            "30,180,136",
            "2,877,175",
            "5,107,758",
            "99,248",
            "206,866",
            "19,549,466",
            "35,494,760",
        ]
    )


def _live_normalized_text() -> str:
    # Exact 2026 connected-note values observed in receipt 20260814003509.
    return "\n".join(
        [
            "반기보고서 (2026.06)",
            "21. 매출액 (연결)",
            "고객과의 계약에서 생기는 수익의 구분에 대한 공시",
            "당반기",
            "(단위 : 백만원)",
            "합계",
            "79,318,746",
            "131,895,033",
            "전반기",
            "(단위 : 백만원)",
            "합계",
            "22,231,952",
            "39,871,093",
            "고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시",
            "당반기",
            "(단위 : 백만원)",
            "부문",
            "부문 합계",
            "DRAM",
            "NAND Flash",
            "기타",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "수익",
            "56,982,743",
            "97,641,379",
            "21,959,898",
            "33,534,133",
            "376,105",
            "719,521",
            "79,318,746",
            "131,895,033",
            "전반기",
            "(단위 : 백만원)",
            "20. 매출액",
            "고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시",
            "당반기",
            "(단위 : 백만원)",
            "부문",
            "부문 합계",
            "DRAM",
            "NAND Flash",
            "기타",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "수익",
            "59,155,599",
            "98,913,878",
            "14,719,034",
            "22,903,501",
            "151,089",
            "266,931",
            "74,025,722",
            "122,084,310",
        ]
    )


def _product_table(
    *,
    dram: tuple[str, str],
    nand: tuple[str, str],
    other: tuple[str, str],
    total: tuple[str, str],
) -> str:
    return f"""
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
      <tr>
        <td>수익(매출액)</td>
        <td>{dram[0]}</td><td>{dram[1]}</td>
        <td>{nand[0]}</td><td>{nand[1]}</td>
        <td>{other[0]}</td><td>{other[1]}</td>
        <td>{total[0]}</td><td>{total[1]}</td>
      </tr>
    </table>
    """


def _split_header_table() -> str:
    return """
    <table>
      <tr>
        <th></th>
        <th colspan="6">부문</th>
        <th colspan="2">부문 합계</th>
      </tr>
      <tr>
        <th></th>
        <th colspan="2">DRAM</th>
        <th colspan="2">NAND Flash</th>
        <th colspan="2">기타</th>
        <th colspan="2">부문 합계</th>
      </tr>
      <tr>
        <th></th>
        <th>3개월</th><th>누적</th>
        <th>3개월</th><th>누적</th>
        <th>3개월</th><th>누적</th>
        <th>3개월</th><th>누적</th>
      </tr>
    </table>
    """


def _split_data_table(
    *,
    dram: tuple[str, str],
    nand: tuple[str, str],
    other: tuple[str, str],
    total: tuple[str, str],
) -> str:
    return f"""
    <table>
      <tr>
        <td>수익</td>
        <td>{dram[0]}</td><td>{dram[1]}</td>
        <td>{nand[0]}</td><td>{nand[1]}</td>
        <td>{other[0]}</td><td>{other[1]}</td>
        <td>{total[0]}</td><td>{total[1]}</td>
      </tr>
    </table>
    """


def _archive(*, include_consolidated: bool = True) -> bytes:
    parts = ["<html><body><h1>반기보고서 (2026.06)</h1>"]
    if include_consolidated:
        parts.extend(
            [
                "<h3>21. 매출액 (연결)</h3>",
                "<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>",
                "<p>당반기</p><p>(단위 : 백만원)</p>",
                _product_table(
                    dram=("17,123,990", "31,160,860"),
                    nand=("4,727,806", "7,956,641"),
                    other=("380,156", "753,592"),
                    total=("22,231,952", "39,871,093"),
                ),
                "<p>전반기</p>",
            ]
        )
    parts.extend(
        [
            "<h3>20. 매출액</h3>",
            "<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>",
            "<p>당반기</p><p>(단위 : 백만원)</p>",
            _product_table(
                dram=("16,573,043", "30,180,136"),
                nand=("2,877,175", "5,107,758"),
                other=("99,248", "206,866"),
                total=("19,549,466", "35,494,760"),
            ),
            "</body></html>",
        ]
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.xml", "".join(parts))
    return buffer.getvalue()


def _live_split_archive() -> bytes:
    markup = "".join(
        [
            "<html><body><h1>반기보고서 (2026.06)</h1>",
            "<h3>21. 매출액 (연결)</h3>",
            "<p>고객과의 계약에서 생기는 수익의 구분에 대한 공시</p>",
            "<p>당반기</p><p>(단위 : 백만원)</p>",
            "<table><tr><th>구분</th><th>3개월</th><th>누적</th></tr>",
            "<tr><td>합계</td><td>79,318,746</td><td>131,895,033</td></tr></table>",
            "<p>전반기</p><p>(단위 : 백만원)</p>",
            "<table><tr><th>구분</th><th>3개월</th><th>누적</th></tr>",
            "<tr><td>합계</td><td>22,231,952</td><td>39,871,093</td></tr></table>",
            "<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>",
            "<p>당반기</p><p>(단위 : 백만원)</p>",
            _split_header_table(),
            _split_data_table(
                dram=("56,982,743", "97,641,379"),
                nand=("21,959,898", "33,534,133"),
                other=("376,105", "719,521"),
                total=("79,318,746", "131,895,033"),
            ),
            "<p>전반기</p>",
            "<h3>20. 매출액</h3>",
            "<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>",
            "<p>당반기</p><p>(단위 : 백만원)</p>",
            _split_header_table(),
            _split_data_table(
                dram=("59,155,599", "98,913,878"),
                nand=("14,719,034", "22,903,501"),
                other=("151,089", "266,931"),
                total=("74,025,722", "122,084,310"),
            ),
            "</body></html>",
        ]
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("20260814003509.xml", markup)
    return buffer.getvalue()


def test_text_parser_selects_consolidated_product_columns_not_separate_table() -> None:
    metrics = parse_periodic_product_revenue_text(_spec(), _normalized_text())
    assert metrics.dram_total == 17_123_990
    assert metrics.nand_and_solutions == 4_727_806
    assert metrics.other_products_services == 380_156
    assert metrics.reported_company_revenue == 22_231_952
    assert metrics.reconciliation_delta == 0


def test_text_parser_accepts_live_2026_plain_revenue_label() -> None:
    metrics = parse_periodic_product_revenue_text(_spec(), _live_normalized_text())
    assert metrics.dram_total == 56_982_743
    assert metrics.nand_and_solutions == 21_959_898
    assert metrics.other_products_services == 376_105
    assert metrics.reported_company_revenue == 79_318_746
    assert metrics.reconciliation_delta == 0


def test_structural_parser_selects_consolidated_product_columns_not_separate_table() -> None:
    metrics = parse_periodic_product_revenue_archive(_spec(), _archive())
    assert metrics.dram_total == 17_123_990
    assert metrics.nand_and_solutions == 4_727_806
    assert metrics.other_products_services == 380_156
    assert metrics.reported_company_revenue == 22_231_952
    assert metrics.reconciliation_delta == 0


def test_structural_parser_accepts_live_2026_split_header_and_data_tables() -> None:
    metrics = parse_periodic_product_revenue_archive(_spec(), _live_split_archive())
    assert metrics.dram_total == 56_982_743
    assert metrics.nand_and_solutions == 21_959_898
    assert metrics.other_products_services == 376_105
    assert metrics.reported_company_revenue == 79_318_746
    assert metrics.reconciliation_delta == 0


def test_structural_parser_fails_closed_without_consolidated_scope() -> None:
    with pytest.raises(ValueError, match="resolve uniquely"):
        parse_periodic_product_revenue_archive(
            _spec(),
            _archive(include_consolidated=False),
        )
