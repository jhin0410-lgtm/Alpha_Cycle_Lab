from __future__ import annotations

import json
from datetime import date

import pytest

from alpha_cycle.intelligence.sec_product_profitability_support import (
    SecProductProfitabilitySupportSpec,
    build_sec_product_profitability_support_evidence,
    parse_sec_product_profitability_support_html,
)


def _spec() -> SecProductProfitabilitySupportSpec:
    return SecProductProfitabilitySupportSpec(
        document_id="skhynix_000660_2026_sec_424b4_product_profitability_support",
        ticker="000660",
        issuer_name="SK hynix",
        source_id="sec_edgar",
        cik="0002120882",
        form="424B4",
        filing_date=date(2026, 7, 10),
        expected_accession_number="0001193125-26-299963",
        expected_primary_document="d32785d424b4.htm",
        parser_id="skhynix_sec_424b4_product_profitability_support_v1",
        calibration_support_only=True,
        product_profitability_source_fact=False,
        current_baseline_eligible=False,
        numeric_forecast_enabled=False,
        decision_score_enabled=False,
        required_identity_anchors=(
            "The following table sets forth our revenue by principal product category and the related percentage data for the periods indicated",
            "first quarter of 2026",
            "gross profit margin increased to 79.3% in the first quarter of 2026 from 57.3% in the first quarter of 2025",
            "gross profit margin increased to 60.4% in 2025 from 48.1% in 2024",
            "gross profit margin of 48.1% in 2024 compared to gross loss margin of 1.6% in 2023",
        ),
    )


def _filing() -> bytes:
    return b"""
    <html><body>
    <p>The following table sets forth our revenue by principal product category and the related percentage data for the periods indicated.</p>
    <p>Three Months Ended March 31, 2026 2025 Year Ended December 31, 2025 2024 2023</p>
    <p>DRAM W 40,659 77.3% W 14,037 79.6% W 74,904 77.1% W 44,732 67.6% W 20,769 63.4%</p>
    <p>NAND Flash 11,574 22.0 3,229 18.3 20,690 21.3 19,274 29.1 9,653 29.5</p>
    <p>Other Products 343 0.7 373 2.1 1,552 1.6 2,187 3.3 2,344 7.2</p>
    <p>Total W 52,576 100.0% W 17,639 100.0% W 97,147 100.0% W 66,193 100.0% W 32,766 100.0%</p>
    <p>DRAMs are a type of random access memory semiconductor.</p>
    <p>Our gross profit increased by 312.6%, or W 31,577 billion, to W 41,679 billion in the first quarter of 2026 from W 10,102 billion in the first quarter of 2025.</p>
    <p>Our gross profit margin increased to 79.3% in the first quarter of 2026 from 57.3% in the first quarter of 2025.</p>
    <p>Our gross profit increased by 84.4%, or W 26,863 billion, to W 58,691 billion in 2025 from W 31,828 billion in 2024.</p>
    <p>Our gross profit margin increased to 60.4% in 2025 from 48.1% in 2024.</p>
    <p>We recorded gross profit of W 31,828 billion in 2024 compared to gross loss of W 533 billion in 2023.</p>
    <p>We recorded gross profit margin of 48.1% in 2024 compared to gross loss margin of 1.6% in 2023.</p>
    </body></html>
    """


def _submissions() -> bytes:
    return json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001193125-26-299963"],
                    "filingDate": ["2026-07-10"],
                    "form": ["424B4"],
                    "primaryDocument": ["d32785d424b4.htm"],
                }
            }
        }
    ).encode()


def test_parser_aligns_five_product_revenue_and_company_profitability_periods() -> None:
    observations = parse_sec_product_profitability_support_html(_spec(), _filing())
    assert [item.period_id for item in observations] == [
        "q1_2026",
        "q1_2025",
        "fy2025",
        "fy2024",
        "fy2023",
    ]
    q1 = observations[0]
    assert q1.total_revenue == 52_576
    assert q1.dram_revenue == 40_659
    assert q1.nand_revenue == 11_574
    assert q1.other_products_revenue == 343
    assert q1.product_revenue_reconciliation_delta_krw_billion == 0
    assert q1.direct_product_revenue_reconciled is True
    assert q1.gross_profit == 41_679
    assert q1.gross_margin_percent == 79.3
    assert abs(q1.gross_margin_reconciliation_delta_pp) < 0.11

    fy2025 = observations[2]
    assert fy2025.total_revenue == 97_147
    assert fy2025.product_revenue_reconciliation_delta_krw_billion == -1
    assert fy2025.direct_product_revenue_reconciled is True

    fy2023 = observations[-1]
    assert fy2023.total_revenue == 32_766
    assert fy2023.gross_profit == -533
    assert fy2023.gross_margin_percent == -1.6
    assert abs(fy2023.gross_margin_reconciliation_delta_pp) < 0.11


def test_parser_accepts_live_sec_rows_without_repeated_percent_markers() -> None:
    observations = parse_sec_product_profitability_support_html(_spec(), _filing())
    assert [item.nand_share_percent for item in observations] == [22.0, 18.3, 21.3, 29.1, 29.5]
    assert [item.other_share_percent for item in observations] == [0.7, 2.1, 1.6, 3.3, 7.2]


def test_evidence_counts_overlapping_q1_2025_and_fy2025_as_non_independent() -> None:
    evidence = build_sec_product_profitability_support_evidence(
        _spec(),
        observed_date=date(2026, 8, 16),
        submissions_bytes=_submissions(),
        filing_bytes=_filing(),
    )
    assert evidence.observation_count == 5
    assert evidence.independent_non_overlapping_period_count == 4
    assert evidence.overlapping_periods_present is True
    assert evidence.direct_product_profitability_observations == 0
    assert evidence.product_profitability_source_fact is False
    assert evidence.calibration_support_only is True
    assert evidence.current_baseline_eligible is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_evidence_rejects_future_observation_date() -> None:
    with pytest.raises(ValueError, match="not yet observable"):
        build_sec_product_profitability_support_evidence(
            _spec(),
            observed_date=date(2026, 7, 9),
            submissions_bytes=_submissions(),
            filing_bytes=_filing(),
        )


def test_parser_rejects_product_revenue_reconciliation_break() -> None:
    broken = _filing().replace(b"W 52,576 100.0%", b"W 52,500 100.0%")
    with pytest.raises(ValueError, match="product revenue does not reconcile"):
        parse_sec_product_profitability_support_html(_spec(), broken)


def test_parser_rejects_rounding_gap_larger_than_one_billion() -> None:
    broken = _filing().replace(b"W 97,147 100.0%", b"W 97,149 100.0%")
    with pytest.raises(ValueError, match="product revenue does not reconcile"):
        parse_sec_product_profitability_support_html(_spec(), broken)


def test_parser_rejects_out_of_range_share_without_percent_marker() -> None:
    broken = _filing().replace(b"NAND Flash 11,574 22.0", b"NAND Flash 11,574 122.0")
    with pytest.raises(ValueError, match="invalid amount/share: nand"):
        parse_sec_product_profitability_support_html(_spec(), broken)


def test_parser_rejects_company_margin_reconciliation_break() -> None:
    broken = _filing().replace(b"79.3% in the first quarter", b"70.0% in the first quarter")
    with pytest.raises(ValueError):
        parse_sec_product_profitability_support_html(_spec(), broken)


def test_spec_forbids_product_profitability_source_fact_promotion() -> None:
    base = _spec()
    with pytest.raises(ValueError, match="exceeds calibration-support boundary"):
        SecProductProfitabilitySupportSpec(
            document_id=base.document_id,
            ticker=base.ticker,
            issuer_name=base.issuer_name,
            source_id=base.source_id,
            cik=base.cik,
            form=base.form,
            filing_date=base.filing_date,
            expected_accession_number=base.expected_accession_number,
            expected_primary_document=base.expected_primary_document,
            parser_id=base.parser_id,
            calibration_support_only=True,
            product_profitability_source_fact=True,
            current_baseline_eligible=False,
            numeric_forecast_enabled=False,
            decision_score_enabled=False,
            required_identity_anchors=base.required_identity_anchors,
        )
