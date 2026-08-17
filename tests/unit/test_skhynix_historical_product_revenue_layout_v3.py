from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_layout_v2 import (
    parse_historical_product_revenue_archive_v2,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_archive,
    parse_periodic_product_revenue_text,
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


def _spec(year: int, quarter: int) -> PeriodicProductRevenueSpec:
    month = quarter * 3
    start_month = (quarter - 1) * 3 + 1
    return PeriodicProductRevenueSpec(
        document_id=f"historical-{year}-q{quarter}-layout-v3-test",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact=(
            f"분기보고서 ({year}.{month:02d})"
            if quarter in {1, 3}
            else f"반기보고서 ({year}.{month:02d})"
        ),
        discovery_begin_date=date(year, min(month + 2, 12), 1),
        discovery_end_date=date(year, min(month + 2, 12), 28),
        period_start=date(year, start_month, 1),
        period_end=date(year, month, 31 if month in {3, 12} else 30),
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


def _legacy_non_q1_fixture(
    *,
    heading: str,
    current_marker: str,
    prior_marker: str,
    values: tuple[tuple[str, str, str, str, str], ...],
) -> tuple[str, str]:
    text_lines = [
        heading,
        "(단위: 백만원)",
        "구 분",
        current_marker,
        current_marker,
        prior_marker,
        prior_marker,
        "구 분",
        "3개월",
        "누 적",
        "3개월",
        "누 적",
    ]
    for row in values:
        text_lines.extend(row)
    unit_row = "".join("<th>(단위: 백만원)</th>" for _ in range(5))
    rows = "".join(
        f"<tr><td>{label}</td><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>"
        for label, a, b, c, d in values
    )
    html = f"""<html><body><p>{heading}</p><p>(단위: 백만원)</p>
<table>
<tr>{unit_row}</tr>
<tr><th>구 분</th><th>{current_marker}</th><th>{current_marker}</th><th>{prior_marker}</th><th>{prior_marker}</th></tr>
<tr><th>구 분</th><th>3개월</th><th>누 적</th><th>3개월</th><th>누 적</th></tr>
{rows}
</table></body></html>"""
    return "\n".join(text_lines), html


def test_2023_q2_internal_space_cumulative_marker_replays_direct_current_quarter() -> None:
    spec = _spec(2023, 2)
    heading = "22. 매출액(1) 당반기와 전반기 중 매출액의 내역은 다음과 같습니다."
    text, html = _legacy_non_q1_fixture(
        heading=heading,
        current_marker="당반기",
        prior_marker="전반기",
        values=(
            ("DRAM", "4,414,132", "7,332,824", "8,781,735", "16,639,311"),
            ("NAND Flash", "2,240,211", "3,928,245", "4,517,859", "8,431,254"),
            ("기타", "651,590", "1,132,975", "511,407", "896,089"),
            ("합 계", "7,305,933", "12,394,044", "13,811,001", "25,966,654"),
        ),
    )
    expected = (4_414_132.0, 2_240_211.0, 651_590.0, 7_305_933.0)
    assert _amounts(parse_periodic_product_revenue_text(spec, text)) == expected
    assert _amounts(parse_periodic_product_revenue_archive(spec, _archive(html))) == expected


def test_2023_q3_internal_space_cumulative_marker_replays_direct_current_quarter() -> None:
    spec = _spec(2023, 3)
    heading = "22. 매출액(1) 당분기와 전분기 중 매출액의 내역은 다음과 같습니다."
    text, html = _legacy_non_q1_fixture(
        heading=heading,
        current_marker="당분기",
        prior_marker="전분기",
        values=(
            ("DRAM", "6,085,615", "13,418,439", "6,954,326", "23,593,637"),
            ("NAND Flash", "2,426,210", "6,354,455", "3,388,185", "11,819,440"),
            ("기타", "554,346", "1,687,320", "640,372", "1,536,460"),
            ("합 계", "9,066,171", "21,460,214", "10,982,883", "36,949,537"),
        ),
    )
    expected = (6_085_615.0, 2_426_210.0, 554_346.0, 9_066_171.0)
    assert _amounts(parse_periodic_product_revenue_text(spec, text)) == expected
    assert _amounts(parse_periodic_product_revenue_archive(spec, _archive(html))) == expected


def _real_style_q1_archive(*, total_label: str, amounts: tuple[str, str, str, str]) -> bytes:
    dram, nand, other, total = amounts
    html = f"""<html><body>
<p>21. 매출액 (연결)</p>
<p>고객과의 계약에서 생기는 수익의 품목별 구분에 대한 공시</p>
<p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>{total_label}</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td>{dram}</td><td>{nand}</td><td>{other}</td><td>{total}</td></tr></table>
<p>전분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>{total_label}</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td>1,000</td><td>2,000</td><td>3,000</td><td>6,000</td></tr></table>
<p>20. 매출액</p><p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>{total_label}</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td>9,000</td><td>8,000</td><td>7,000</td><td>24,000</td></tr></table>
</body></html>"""
    return _archive(html)


@pytest.mark.parametrize(
    ("year", "total_label", "amounts", "expected"),
    [
        (
            2024,
            "제품과 용역 합계",
            ("7,493,448", "4,407,213", "528,937", "12,429,598"),
            (7_493_448.0, 4_407_213.0, 528_937.0, 12_429_598.0),
        ),
        (
            2025,
            "부문 합계",
            ("14,036,870", "3,228,835", "373,436", "17,639,141"),
            (14_036_870.0, 3_228_835.0, 373_436.0, 17_639_141.0),
        ),
        (
            2026,
            "부문 합계",
            ("40,658,636", "11,574,235", "343,416", "52,576,287"),
            (40_658_636.0, 11_574_235.0, 343_416.0, 52_576_287.0),
        ),
    ],
)
def test_q1_three_table_raw_family_uses_connected_current_values(
    year: int,
    total_label: str,
    amounts: tuple[str, str, str, str],
    expected: tuple[float, float, float, float],
) -> None:
    spec = _spec(year, 1)
    archive_bytes = _real_style_q1_archive(total_label=total_label, amounts=amounts)
    with pytest.raises(ValueError, match="q1_split_archive"):
        parse_historical_product_revenue_archive_v2(spec, archive_bytes)
    assert _amounts(parse_periodic_product_revenue_archive(spec, archive_bytes)) == expected


def test_q1_three_table_family_refuses_arbitrary_table_distance() -> None:
    spec = _spec(2025, 1)
    html = """<html><body>
<p>21. 매출액 (연결)</p><p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
<p>수익(매출액)</p>
<table><tr><td>14,036,870</td><td>3,228,835</td><td>373,436</td><td>17,639,141</td></tr></table>
<table><tr><td>unrelated intervening table</td></tr></table>
<p>전분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
</body></html>"""
    with pytest.raises(ValueError, match="v3=.*candidates=0"):
        parse_periodic_product_revenue_archive(spec, _archive(html))
