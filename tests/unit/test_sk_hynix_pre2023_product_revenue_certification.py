from __future__ import annotations

from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_certification import (
    certify_pre2023_product_revenue_period,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_product_revenue_source_closure import (
    ProductRevenueSourceClosurePeriod,
    ProductRevenueTableWitness,
)
from alpha_cycle.intelligence.sk_hynix_pre2023_source_layer_resolution import (
    VerifiedCompanyProfitabilityConstraint,
)

_SHA = "a" * 64
_RCEPT = "20220816001536"


def _candidate(table_index: int, rows: tuple[tuple[str, ...], ...]) -> ProductRevenueTableWitness:
    return ProductRevenueTableWitness(
        member_name=f"{_RCEPT}.xml",
        table_index=table_index,
        witness_kind="direct_separable_candidate",
        layout_mode="structured_grid",
        prefix_tail=("매출액의 품목별 세부내역", "(단위: 백만원)"),
        rows=rows,
        combined_bucket_cells=(),
        dram_label_rows=((3, 0),),
        nand_label_rows=((4, 0),),
        direct_labeled_amount_row_count=2,
        unit_markers=("백만원",),
    )


def _period(*candidates: ProductRevenueTableWitness) -> ProductRevenueSourceClosurePeriod:
    return ProductRevenueSourceClosurePeriod(
        evidence_id=_SHA,
        period_id="2022Q2",
        rcept_no=_RCEPT,
        archive_sha256=_SHA,
        member_count=1,
        table_count=500,
        layout_fallback_count=0,
        layout_fallback_errors=(),
        aggregate_bucket_witnesses=(),
        direct_separable_candidates=tuple(candidates),
        aggregate_bucket_witness_count=0,
        direct_separable_candidate_count=len(candidates),
    )


def _company(revenue_million_krw: int = 13_811_001) -> VerifiedCompanyProfitabilityConstraint:
    revenue = revenue_million_krw * 1_000_000
    cost = 8_000_000 * 1_000_000
    gross = revenue - cost
    return VerifiedCompanyProfitabilityConstraint(
        period_id="2022Q2",
        rcept_no=_RCEPT,
        revenue_krw=revenue,
        cost_of_sales_krw=cost,
        gross_profit_krw=gross,
        gross_margin_percent=gross / revenue * 100.0,
        raw_payload_sha256=_SHA,
        raw_payload_path="fixture.json",
    )


def _rows(
    dram_3m: str,
    dram_ytd: str,
    nand_3m: str,
    nand_ytd: str,
    other_3m: str,
    other_ytd: str,
    total_3m: str,
    total_ytd: str,
) -> tuple[tuple[str, ...], ...]:
    return (
        ("(단위: 백만원)",) * 5,
        ("구 분", "당반기", "당반기", "전반기", "전반기"),
        ("구 분", "3개월", "누 적", "3개월", "누 적"),
        ("DRAM", dram_3m, dram_ytd, "7,505,783", "13,568,252"),
        ("NAND Flash", nand_3m, nand_ytd, "2,305,681", "4,313,204"),
        ("기타", other_3m, other_ytd, "510,207", "934,403"),
        ("합 계", total_3m, total_ytd, "10,321,671", "18,815,859"),
    )


def test_certification_selects_consolidated_direct_quarter_candidate() -> None:
    consolidated = _candidate(
        143,
        _rows(
            "8,781,735",
            "16,639,311",
            "4,517,859",
            "8,431,254",
            "511,407",
            "896,089",
            "13,811,001",
            "25,966,654",
        ),
    )
    separate = _candidate(
        227,
        _rows(
            "8,750,956",
            "16,621,760",
            "3,149,208",
            "5,739,804",
            "201,550",
            "377,722",
            "12,101,714",
            "22,739,286",
        ),
    )

    result = certify_pre2023_product_revenue_period(
        _period(consolidated, separate),
        _company(),
    )

    assert result.certified is True
    assert result.error is None
    assert result.observation is not None
    assert result.observation.table_index == 143
    assert result.observation.direct_quarter_column_index == 1
    assert result.observation.direct_quarter_semantics == "direct_quarter_3_month"
    assert result.observation.dram_revenue_million_krw == 8_781_735
    assert result.observation.nand_revenue_million_krw == 4_517_859
    assert result.observation.other_revenue_million_krw == 511_407
    assert result.observation.total_revenue_million_krw == 13_811_001
    assert result.candidate_reviews[0].reconciles_to_company_revenue is True
    assert result.candidate_reviews[1].reconciles_to_company_revenue is False
    assert "consolidated revenue" in result.candidate_reviews[1].rejection_reasons[0]
    assert result.training_row_promoted is False
    assert result.fit_enabled is False


def test_certification_rejects_ambiguous_multiple_company_tie_outs() -> None:
    rows = _rows(
        "8,781,735",
        "16,639,311",
        "4,517,859",
        "8,431,254",
        "511,407",
        "896,089",
        "13,811,001",
        "25,966,654",
    )
    result = certify_pre2023_product_revenue_period(
        _period(_candidate(143, rows), _candidate(144, rows)),
        _company(),
    )

    assert result.certified is False
    assert result.observation is None
    assert result.error is not None
    assert "matches=2" in result.error


def test_certification_rejects_fallback_layout_even_when_amounts_tie() -> None:
    base = _candidate(
        143,
        _rows(
            "8,781,735",
            "16,639,311",
            "4,517,859",
            "8,431,254",
            "511,407",
            "896,089",
            "13,811,001",
            "25,966,654",
        ),
    )
    fallback = ProductRevenueTableWitness(
        **{**base.__dict__, "layout_mode": "flat_cell_sequence_fallback"}
    )
    result = certify_pre2023_product_revenue_period(_period(fallback), _company())

    assert result.certified is False
    assert result.observation is None
    assert result.candidate_reviews[0].reconciles_to_company_revenue is False
    assert "diagnostic fallback" in result.candidate_reviews[0].rejection_reasons[0]
