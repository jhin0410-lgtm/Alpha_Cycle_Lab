from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    OpenDartPeriodicProductRevenueCertification,
    ProductRevenueMetrics,
)
from alpha_cycle.intelligence.sk_hynix_q2_product_revenue_ir_crosscheck import (
    build_product_revenue_ir_crosscheck,
)


def _certification(
    *,
    dram: float,
    nand: float,
    other: float,
) -> OpenDartPeriodicProductRevenueCertification:
    total = dram + nand + other
    return OpenDartPeriodicProductRevenueCertification(
        evidence_id="a" * 64,
        evaluation_date=date(2026, 8, 15),
        document_id="skhynix_000660_2026q2_half_year_product_revenue",
        ticker="000660",
        issuer_name="SK hynix",
        rcept_no="20260814003509",
        report_name="반기보고서 (2026.06)",
        receipt_date=date(2026, 8, 14),
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        metrics=ProductRevenueMetrics(
            unit="KRW_million",
            dram_total=dram,
            nand_and_solutions=nand,
            other_products_services=other,
            reported_company_revenue=total,
            direct_sum=total,
            reconciliation_delta=0.0,
        ),
        archive_sha256="b" * 64,
        archive_bytes=100,
        text_sha256="c" * 64,
        text_chars=1000,
        source_url="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814003509",
    )


def _direct(*, other: float = 160_000) -> OpenDartPeriodicProductRevenueCertification:
    return _certification(dram=29_080_000.0, nand=10_760_000.0, other=other)


def _live_direct() -> OpenDartPeriodicProductRevenueCertification:
    return _certification(
        dram=56_982_743.0,
        nand=21_959_898.0,
        other=376_105.0,
    )


def _ir():
    return SimpleNamespace(
        evidence_id="d" * 64,
        product_assignment_certified=True,
        other_share_percent=None,
        other_zero_certified=False,
        dram_share_percent=73.0,
        nand_share_percent=27.0,
        others_segment_present=True,
        current_period_label="'26 Q2",
    )


def test_direct_amount_shares_crosscheck_rounded_ir_labels_without_inferring_other() -> None:
    item = build_product_revenue_ir_crosscheck(_direct(), _ir())  # type: ignore[arg-type]
    assert item.dram_rounded_match is True
    assert item.nand_rounded_match is True
    assert item.share_identity_match is True
    assert item.others_presence_match is True
    assert item.comparison_status == "matched"
    assert item.crosscheck_certified is True
    assert item.direct_source_fact_remains_valid is True
    assert item.other_direct_share_percent > 0
    assert item.allocation_resolver_registered is False
    assert item.numeric_forecast_enabled is False
    assert item.decision_score_enabled is False


def test_ir_crosscheck_blocks_cross_source_promotion_when_share_identity_does_not_match() -> None:
    direct = _direct(other=2_000_000)
    item = build_product_revenue_ir_crosscheck(direct, _ir())  # type: ignore[arg-type]
    assert item.crosscheck_certified is False
    assert item.product_revenue_promotion_ready is False
    assert item.direct_source_fact_remains_valid is True


def test_live_2026_dart_source_fact_survives_ir_share_definition_mismatch() -> None:
    direct = _live_direct()
    item = build_product_revenue_ir_crosscheck(direct, _ir())  # type: ignore[arg-type]

    assert direct.product_revenue_baseline_eligible is True
    assert direct.company_revenue_reconciliation_certified is True
    assert item.dram_direct_share_percent == 100.0 * 56_982_743.0 / 79_318_746.0
    assert item.nand_direct_share_percent == 100.0 * 21_959_898.0 / 79_318_746.0
    assert item.other_direct_share_percent == 100.0 * 376_105.0 / 79_318_746.0
    assert item.dram_rounded_match is False
    assert item.nand_rounded_match is False
    assert item.share_identity_match is False
    assert item.others_presence_match is True
    assert item.period_match is True
    assert item.comparison_status == "official_source_share_identity_mismatch"
    assert item.crosscheck_certified is False
    assert item.product_revenue_promotion_ready is False
    assert item.direct_source_fact_remains_valid is True
