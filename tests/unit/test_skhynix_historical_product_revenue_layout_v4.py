from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v3 import (
    parse_historical_product_revenue_archive_v3,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_archive,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)


def _labels() -> dict[str, tuple[str, ...]]:
    return {
        "dram_total": ("DRAM",),
        "nand_and_solutions": ("NAND", "NAND Flash"),
        "other_products_services": ("기타", "기타 제품 및 서비스"),
        "reported_company_revenue": (
            "합계",
            "합 계",
            "매출액 합계",
            "부문 합계",
            "제품과 용역 합계",
        ),
    }


def _spec(year: int) -> PeriodicProductRevenueSpec:
    return PeriodicProductRevenueSpec(
        document_id=f"historical-{year}-q1-prefix-witness-v4-test",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact=f"분기보고서 ({year}.03)",
        discovery_begin_date=date(year, 5, 1),
        discovery_end_date=date(year, 5, 28),
        period_start=date(year, 1, 1),
        period_end=date(year, 3, 31),
        parser_id=HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
        expected_identity_anchors=("DRAM", "NAND", "백만원"),
        product_labels=_labels(),
    )


def _archive(html: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.xml", html.encode("utf-8"))
    return stream.getvalue()


def _amounts(metrics: object) -> tuple[float, float, float, float]:
    return (
        metrics.dram_total,  # type: ignore[attr-defined]
        metrics.nand_and_solutions,  # type: ignore[attr-defined]
        metrics.other_products_services,  # type: ignore[attr-defined]
        metrics.reported_company_revenue,  # type: ignore[attr-defined]
    )


def _observed_q1_archive(
    *,
    total_label: str,
    amounts: tuple[str, str, str, str],
    standalone_amounts: tuple[str, str, str, str],
) -> bytes:
    dram, nand, other, total = amounts
    s_dram, s_nand, s_other, s_total = standalone_amounts
    html = f"""<html><body>
<p>21. 매출액 (연결)</p>
<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>
<p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>{total_label}</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td><span>{dram}</span><span>{nand}</span><span>{other}</span><span>{total}</span></td></tr></table>
<p>전분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>{total_label}</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td><span>1,000</span><span>2,000</span><span>3,000</span><span>6,000</span></td></tr></table>
<p>20. 매출액</p>
<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>
<p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>{total_label}</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td><span>{s_dram}</span><span>{s_nand}</span><span>{s_other}</span><span>{s_total}</span></td></tr></table>
<p>전분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>{total_label}</th></tr></table>
</body></html>"""
    return _archive(html)


@pytest.mark.parametrize(
    ("year", "total_label", "amounts", "standalone", "expected"),
    [
        (
            2024,
            "제품과 용역 합계",
            ("7,493,448", "4,407,213", "528,937", "12,429,598"),
            ("7,481,860", "2,705,339", "214,620", "10,401,819"),
            (7_493_448.0, 4_407_213.0, 528_937.0, 12_429_598.0),
        ),
        (
            2025,
            "부문 합계",
            ("14,036,870", "3,228,835", "373,436", "17,639,141"),
            ("13,607,092", "2,230,583", "107,619", "15,945,294"),
            (14_036_870.0, 3_228_835.0, 373_436.0, 17_639_141.0),
        ),
        (
            2026,
            "부문 합계",
            ("40,658,636", "11,574,235", "343,416", "52,576,287"),
            ("39,758,279", "8,184,467", "115,842", "48,058,588"),
            (40_658_636.0, 11_574_235.0, 343_416.0, 52_576_287.0),
        ),
    ],
)
def test_q1_prefix_witness_recovers_connected_direct_values_from_joined_data_cell(
    year: int,
    total_label: str,
    amounts: tuple[str, str, str, str],
    standalone: tuple[str, str, str, str],
    expected: tuple[float, float, float, float],
) -> None:
    spec = _spec(year)
    archive_bytes = _observed_q1_archive(
        total_label=total_label,
        amounts=amounts,
        standalone_amounts=standalone,
    )
    with pytest.raises(ValueError, match="q1_three_table_archive"):
        parse_historical_product_revenue_archive_v3(spec, archive_bytes)
    assert _amounts(parse_periodic_product_revenue_archive(spec, archive_bytes)) == expected


def test_q1_prefix_witness_requires_exact_two_table_index_spacing() -> None:
    spec = _spec(2025)
    html = """<html><body>
<p>21. 매출액 (연결)</p><p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td><span>14,036,870</span><span>3,228,835</span><span>373,436</span><span>17,639,141</span></td></tr></table>
<table><tr><td>unexpected extra table</td></tr></table>
<p>전분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
</body></html>"""
    with pytest.raises(ValueError, match="v4=.*candidates=0"):
        parse_periodic_product_revenue_archive(spec, _archive(html))


def test_q1_prefix_witness_rejects_standalone_only_note() -> None:
    spec = _spec(2025)
    html = """<html><body>
<p>20. 매출액</p><p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td><span>13,607,092</span><span>2,230,583</span><span>107,619</span><span>15,945,294</span></td></tr></table>
<p>전분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
</body></html>"""
    with pytest.raises(ValueError, match="v4=.*candidates=0"):
        parse_periodic_product_revenue_archive(spec, _archive(html))
