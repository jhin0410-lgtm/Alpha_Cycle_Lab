from __future__ import annotations

import io
import zipfile
from datetime import date

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    load_historical_product_revenue_specs,
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
    report_name = (
        f"분기보고서 ({year}.{month:02d})"
        if quarter in {1, 3}
        else f"반기보고서 ({year}.{month:02d})"
    )
    return PeriodicProductRevenueSpec(
        document_id=f"historical-{year}-q{quarter}-layout-v2-test",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact=report_name,
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


def test_registry_binds_observed_historical_total_aliases() -> None:
    specs = load_historical_product_revenue_specs()
    labels = specs[0].product_labels["reported_company_revenue"]
    assert "합 계" in labels
    assert "제품과 용역 합계" in labels


def test_2023_q1_verbose_consolidated_row_family_beats_standalone_note() -> None:
    spec = _spec(2023, 1)
    heading = "22. 매출액(1) 당분기와 전분기 중 매출액의 내역은 다음과 같습니다."
    text = "\n".join(
        [
            "3개월",
            heading,
            "(단위: 백만원)",
            "구 분",
            "당분기",
            "전분기",
            "DRAM",
            "2,918,692",
            "7,857,576",
            "NAND Flash",
            "1,688,034",
            "3,913,395",
            "기타",
            "481,385",
            "384,682",
            "합 계",
            "5,088,111",
            "12,155,653",
            "21. 매출액",
            "DRAM",
            "3,213,116",
            "NAND Flash",
            "1,102,866",
            "기타",
            "127,493",
            "합 계",
            "4,443,475",
        ]
    )
    unit_row = "".join("<th>(단위: 백만원)</th>" for _ in range(3))
    html = f"""<html><body>
<p>3개월</p><p>{heading}</p><p>(단위: 백만원)</p>
<table>
<tr>{unit_row}</tr>
<tr><th>구 분</th><th>당분기</th><th>전분기</th></tr>
<tr><td>DRAM</td><td>2,918,692</td><td>7,857,576</td></tr>
<tr><td>NAND Flash</td><td>1,688,034</td><td>3,913,395</td></tr>
<tr><td>기타</td><td>481,385</td><td>384,682</td></tr>
<tr><td>합 계</td><td>5,088,111</td><td>12,155,653</td></tr>
</table>
<p>21. 매출액</p>
<table>
<tr><th>구 분</th><th>당분기</th><th>전분기</th></tr>
<tr><td>DRAM</td><td>3,213,116</td><td>7,870,803</td></tr>
<tr><td>NAND Flash</td><td>1,102,866</td><td>2,590,596</td></tr>
<tr><td>기타</td><td>127,493</td><td>176,173</td></tr>
<tr><td>합 계</td><td>4,443,475</td><td>10,637,572</td></tr>
</table>
</body></html>"""
    expected = (2_918_692.0, 1_688_034.0, 481_385.0, 5_088_111.0)
    assert _amounts(parse_periodic_product_revenue_text(spec, text)) == expected
    assert _amounts(parse_periodic_product_revenue_archive(spec, _archive(html))) == expected


def test_2023_q2_row_family_uses_current_three_month_not_cumulative() -> None:
    spec = _spec(2023, 2)
    heading = "22. 매출액(1) 당반기와 전반기 중 매출액의 내역은 다음과 같습니다."
    text = "\n".join(
        [
            heading,
            "(단위: 백만원)",
            "구 분",
            "당반기",
            "당반기",
            "전반기",
            "전반기",
            "구 분",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "DRAM",
            "4,414,132",
            "7,332,824",
            "8,781,735",
            "16,639,311",
            "NAND Flash",
            "2,240,211",
            "3,928,245",
            "4,517,859",
            "8,431,254",
            "기타",
            "651,590",
            "1,132,975",
            "511,407",
            "896,089",
            "합 계",
            "7,305,933",
            "12,394,044",
            "13,811,001",
            "25,966,654",
        ]
    )
    unit_row = "".join("<th>(단위: 백만원)</th>" for _ in range(5))
    html = f"""<html><body><p>{heading}</p><p>(단위: 백만원)</p>
<table>
<tr>{unit_row}</tr>
<tr><th>구 분</th><th>당반기</th><th>당반기</th><th>전반기</th><th>전반기</th></tr>
<tr><th>구 분</th><th>3개월</th><th>누적</th><th>3개월</th><th>누적</th></tr>
<tr><td>DRAM</td><td>4,414,132</td><td>7,332,824</td><td>8,781,735</td><td>16,639,311</td></tr>
<tr><td>NAND Flash</td><td>2,240,211</td><td>3,928,245</td><td>4,517,859</td><td>8,431,254</td></tr>
<tr><td>기타</td><td>651,590</td><td>1,132,975</td><td>511,407</td><td>896,089</td></tr>
<tr><td>합 계</td><td>7,305,933</td><td>12,394,044</td><td>13,811,001</td><td>25,966,654</td></tr>
</table></body></html>"""
    expected = (4_414_132.0, 2_240_211.0, 651_590.0, 7_305_933.0)
    assert _amounts(parse_periodic_product_revenue_text(spec, text)) == expected
    assert _amounts(parse_periodic_product_revenue_archive(spec, _archive(html))) == expected


def test_q1_split_column_family_scopes_connected_current_quarter() -> None:
    spec = _spec(2025, 1)
    text = "\n".join(
        [
            "21. 매출액 (연결)",
            "당분기",
            "(단위 : 백만원)",
            "DRAM",
            "NAND Flash",
            "기타",
            "부문 합계",
            "수익(매출액)",
            "14,036,870",
            "3,228,835",
            "373,436",
            "17,639,141",
            "전분기",
            "(단위 : 백만원)",
            "DRAM",
            "NAND Flash",
            "기타",
            "부문 합계",
            "수익(매출액)",
            "12,000,000",
            "3,000,000",
            "400,000",
            "15,400,000",
            "20. 매출액",
            "당분기",
            "(단위 : 백만원)",
            "DRAM",
            "NAND Flash",
            "기타",
            "부문 합계",
            "수익(매출액)",
            "13,607,092",
            "2,230,583",
            "107,619",
            "15,945,294",
        ]
    )
    html = """<html><body>
<p>21. 매출액 (연결)</p><p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
<table><tr><td>수익(매출액)</td><td>14,036,870</td><td>3,228,835</td><td>373,436</td><td>17,639,141</td></tr></table>
<p>전분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
<table><tr><td>수익(매출액)</td><td>12,000,000</td><td>3,000,000</td><td>400,000</td><td>15,400,000</td></tr></table>
<p>20. 매출액</p><p>당분기</p><p>(단위 : 백만원)</p>
<table><tr><th></th><th>DRAM</th><th>NAND Flash</th><th>기타</th><th>부문 합계</th></tr></table>
<table><tr><td>수익(매출액)</td><td>13,607,092</td><td>2,230,583</td><td>107,619</td><td>15,945,294</td></tr></table>
</body></html>"""
    expected = (14_036_870.0, 3_228_835.0, 373_436.0, 17_639_141.0)
    assert _amounts(parse_periodic_product_revenue_text(spec, text)) == expected
    assert _amounts(parse_periodic_product_revenue_archive(spec, _archive(html))) == expected


def test_2024_q2_current_parser_accepts_products_and_services_total_alias() -> None:
    spec = _spec(2024, 2)
    text = "\n".join(
        [
            "21. 매출액 (연결)",
            "당반기",
            "(단위 : 백만원)",
            "제품과 용역",
            "DRAM",
            "DRAM",
            "NAND Flash",
            "NAND Flash",
            "기타",
            "기타",
            "제품과 용역 합계",
            "제품과 용역 합계",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "3개월",
            "누적",
            "수익(매출액)",
            "8,000",
            "15,000",
            "3,000",
            "5,000",
            "1,000",
            "2,000",
            "12,000",
            "22,000",
            "전반기",
        ]
    )
    metrics = parse_periodic_product_revenue_text(spec, text)
    assert _amounts(metrics) == (8_000.0, 3_000.0, 1_000.0, 12_000.0)
