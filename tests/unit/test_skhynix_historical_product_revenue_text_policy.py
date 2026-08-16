from __future__ import annotations

from datetime import date

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_fallback import (
    HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
)
from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_text_policy import (
    parse_historical_product_revenue_text_prioritized,
)
from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_parser_dispatch import (
    parse_periodic_product_revenue_text,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
    ProductRevenueMetrics,
)


def _spec() -> PeriodicProductRevenueSpec:
    return PeriodicProductRevenueSpec(
        document_id="historical-q1-precedence-test",
        ticker="000660",
        issuer_name="SK하이닉스",
        source_id="opendart",
        report_name_exact="분기보고서 (2025.03)",
        discovery_begin_date=date(2025, 5, 1),
        discovery_end_date=date(2025, 5, 31),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 3, 31),
        parser_id=HISTORICAL_PRODUCT_REVENUE_PARSER_ID,
        expected_identity_anchors=("DRAM", "NAND", "3개월", "백만원"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND", "NAND Flash"),
            "other_products_services": ("기타", "기타 제품 및 서비스"),
            "reported_company_revenue": ("합계", "매출액 합계", "부문 합계"),
        },
    )


def _row_and_loose_q1_text() -> str:
    return "\n".join(
        [
            "21. 매출액 (연결)",
            "(단위: 백만원)",
            "당분기",
            "3개월",
            "DRAM",
            "100",
            "NAND Flash",
            "40",
            "기타",
            "10",
            "합계",
            "150",
            "수익",
            "90",
            "35",
            "8",
            "133",
        ]
    )


def _loose_q1_only_text() -> str:
    return "\n".join(
        [
            "21. 매출액 (연결)",
            "(단위: 백만원)",
            "당분기",
            "3개월",
            "DRAM",
            "NAND Flash",
            "기타",
            "합계",
            "수익",
            "100",
            "40",
            "10",
            "150",
        ]
    )


def _amounts(metrics: ProductRevenueMetrics) -> tuple[float, float, float, float]:
    return (
        metrics.dram_total,
        metrics.nand_and_solutions,
        metrics.other_products_services,
        metrics.reported_company_revenue,
    )


def test_explicit_q1_row_layout_wins_over_looser_revenue_candidate() -> None:
    metrics = parse_historical_product_revenue_text_prioritized(
        _spec(),
        _row_and_loose_q1_text(),
    )
    assert _amounts(metrics) == (100.0, 40.0, 10.0, 150.0)


def test_production_dispatch_uses_q1_row_precedence() -> None:
    metrics = parse_periodic_product_revenue_text(
        _spec(),
        _row_and_loose_q1_text(),
    )
    assert _amounts(metrics) == (100.0, 40.0, 10.0, 150.0)


def test_q1_single_period_fallback_still_runs_when_explicit_rows_are_unavailable() -> None:
    metrics = parse_historical_product_revenue_text_prioritized(
        _spec(),
        _loose_q1_only_text(),
    )
    assert _amounts(metrics) == (100.0, 40.0, 10.0, 150.0)
