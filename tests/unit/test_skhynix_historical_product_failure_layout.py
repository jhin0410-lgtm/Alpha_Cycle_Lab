from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    HistoricalProductRevenueFailureDiagnostic,
)
from alpha_cycle.intelligence.sk_hynix_historical_product_failure_layout import (
    build_failure_layout_signature,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    PeriodicProductRevenueSpec,
)


def _spec() -> PeriodicProductRevenueSpec:
    return PeriodicProductRevenueSpec(
        document_id="historical-layout-test",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="opendart",
        report_name_exact="분기보고서 (2024.03)",
        discovery_begin_date=date(2024, 5, 1),
        discovery_end_date=date(2024, 5, 31),
        period_start=date(2024, 1, 1),
        period_end=date(2024, 3, 31),
        parser_id="skhynix_opendart_periodic_product_revenue_v1",
        expected_identity_anchors=("DRAM", "NAND", "3개월", "백만원"),
        product_labels={
            "dram_total": ("DRAM",),
            "nand_and_solutions": ("NAND", "NAND Flash"),
            "other_products_services": ("기타",),
            "reported_company_revenue": ("합계", "부문 합계"),
        },
    )


def test_failure_layout_signature_exposes_bounded_source_structure(tmp_path: Path) -> None:
    text = "\n".join(
        [
            "20. 매출액",
            "전분기",
            "21. 매출액 (연결)",
            "(단위 : 백만원)",
            "당분기",
            "구분",
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
        ]
    )
    text_path = tmp_path / "normalized_document.txt"
    text_path.write_bytes(text.encode("utf-8"))
    diagnostic = HistoricalProductRevenueFailureDiagnostic(
        period_id="2024Q1",
        diagnostic_path=str(tmp_path / "diagnostic.json"),
        rcept_no="20240516001638",
        report_name="분기보고서 (2024.03)",
        archive_path=str(tmp_path / "opendart_document.zip"),
        archive_sha256="a" * 64,
        normalized_text_path=str(text_path),
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        error_type="ValueError",
        error="historical parser candidates=0",
    )
    signature = build_failure_layout_signature(diagnostic, _spec())
    assert signature.period_id == "2024Q1"
    assert signature.error == "historical parser candidates=0"
    assert signature.revenue_note_headings == ("20. 매출액", "21. 매출액 (연결)")
    assert signature.connected_revenue_note_headings == ("21. 매출액 (연결)",)
    assert signature.current_period_markers == ("당분기",)
    assert signature.prior_period_markers == ("전분기",)
    assert signature.three_month_count == 1
    assert signature.cumulative_count == 0
    assert signature.dram_label_count == 1
    assert signature.nand_label_count == 1
    assert signature.other_label_count == 1
    assert signature.total_label_count == 1
    assert signature.revenue_label_count == 1
    assert "DRAM" in signature.relevant_excerpt
    assert signature.source_fact_promoted is False
