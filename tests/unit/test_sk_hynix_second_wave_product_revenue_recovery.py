from __future__ import annotations

import pytest

from alpha_cycle.intelligence.sk_hynix_second_wave_product_revenue_recovery import (
    SecondWaveRecoveredProductRevenue,
    certify_rows,
)


def test_second_wave_recovery_uses_direct_three_month_column_and_exact_tieout() -> None:
    rows = (
        ("(단위: 백만원)", "(단위: 백만원)", "(단위: 백만원)"),
        ("구 분", "당반기", "당반기"),
        ("구 분", "3개월", "누적"),
        ("DRAM", "4,000", "7,000"),
        ("NAND Flash", "2,000", "3,500"),
        ("기타", "500", "900"),
        ("합 계", "6,500", "11,400"),
    )

    column, semantics, dram, nand, other, total = certify_rows(
        rows, 6_500_000_000
    )

    assert column == 1
    assert semantics == "direct_quarter_3_month"
    assert (dram, nand, other, total) == (4000, 2000, 500, 6500)


def test_second_wave_recovery_rejects_nonconsolidated_total() -> None:
    rows = (
        ("구 분", "당분기", "전분기"),
        ("DRAM", "4,000", "3,000"),
        ("NAND Flash", "2,000", "1,500"),
        ("기타", "500", "400"),
        ("합 계", "6,500", "4,900"),
    )

    with pytest.raises(ValueError, match="verified consolidated revenue"):
        certify_rows(rows, 6_600_000_000)


def test_recovered_product_supports_preregistered_2017_q1_q3_but_not_q4() -> None:
    item = SecondWaveRecoveredProductRevenue(
        evidence_id="a" * 64,
        period_id="2017Q1",
        rcept_no="20170515000001",
        source_archive_sha256="b" * 64,
        member_name="20170515000001.xml",
        table_index=1,
        direct_quarter_column_index=1,
        direct_quarter_semantics="direct_quarter_current_period",
        dram_revenue_million_krw=60,
        nand_revenue_million_krw=30,
        other_revenue_million_krw=10,
        total_revenue_million_krw=100,
        company_revenue_krw=100_000_000,
    )
    assert item.period_id == "2017Q1"

    with pytest.raises(ValueError, match="unsupported"):
        SecondWaveRecoveredProductRevenue(
            evidence_id="a" * 64,
            period_id="2017Q4",
            rcept_no="20171115000001",
            source_archive_sha256="b" * 64,
            member_name="20171115000001.xml",
            table_index=1,
            direct_quarter_column_index=1,
            direct_quarter_semantics="direct_quarter_current_period",
            dram_revenue_million_krw=60,
            nand_revenue_million_krw=30,
            other_revenue_million_krw=10,
            total_revenue_million_krw=100,
            company_revenue_krw=100_000_000,
        )
