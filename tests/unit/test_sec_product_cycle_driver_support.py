from __future__ import annotations

import hashlib
from datetime import date

import pytest

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    build_sec_product_cycle_driver_support_evidence,
    parse_sec_product_cycle_driver_html,
)

_PERIODS = (
    "1Q 2023",
    "2Q 2023",
    "3Q 2023",
    "4Q 2023",
    "1Q 2024",
    "2Q 2024",
    "3Q 2024",
    "4Q 2024",
    "1Q 2025",
    "2Q 2025",
    "3Q 2025",
    "4Q 2025",
    "1Q 2026",
)
_DRAM_VOLUME = (
    "Around 20% Decrease",
    "Mid-30% Increase",
    "Around 20% Increase",
    "Low-single% Increase",
    "Mid-teen% Decrease",
    "Low-20% Increase",
    "Slight Decrease",
    "Mid-single% Increase",
    "High-single% Decrease",
    "Mid-20% Increase",
    "High-single% Increase",
    "Low-single% Increase",
    "Flat",
)
_DRAM_ASP = (
    "High-teen% Decrease",
    "High-single% Increase",
    "Around 10% Increase",
    "High-teen% Increase",
    "Over 20% Increase",
    "Mid-teen% Increase",
    "Mid-teen% Increase",
    "Around 10% Increase",
    "Flat",
    "Low-single% Increase",
    "Mid-single% Increase",
    "Mid-20% Increase",
    "Mid-60% Increase",
)
_NAND_VOLUME = (
    "Mid-teen% Decrease",
    "Around 50% Increase",
    "Mid-single% Increase",
    "Low-single% Decrease",
    "Flat",
    "Low-single% Decrease",
    "Mid-teen% Decrease",
    "Mid-single% Decrease",
    "High-teen% Decrease",
    "Over 70% Increase",
    "Mid-single% Decrease",
    "Around 10% Increase",
    "Around 10% Decrease",
)
_NAND_ASP = (
    "Around 10% Decrease",
    "Around 10% Decrease",
    "Slight Decrease",
    "Over 40% Increase",
    "Over 30% Increase",
    "Mid-high-teen% Increase",
    "Mid-teen% Increase",
    "Mid-single% Decrease",
    "Around 20% Decrease",
    "High-single% Decrease",
    "Low-teen% Increase",
    "Low 30% Increase",
    "Mid 70% Increase",
)


def _row(label: str, values: tuple[str, ...]) -> str:
    cells = "".join(f"<td>{value}</td>" for value in values)
    return f"<tr><td>{label}</td>{cells}</tr>"


def _filing_html() -> bytes:
    period_cells = "".join(f"<th>{period}</th>" for period in _PERIODS)
    html = (
        "<html><body>"
        "<table>"
        f"<tr>{period_cells}</tr>"
        f"{_row('DRAM Bit Sales Volume', _DRAM_VOLUME)}"
        f"{_row('DRAM Average Selling Price', _DRAM_ASP)}"
        "</table>"
        "<table>"
        f"<tr>{period_cells}</tr>"
        f"{_row('NAND\u00a0Flash Bit Sales Volume', _NAND_VOLUME)}"
        f"{_row('NAND Flash Average Selling Price', _NAND_ASP)}"
        "</table>"
        "</body></html>"
    )
    return html.encode()


def test_parser_preserves_all_thirteen_official_text_bands_without_numeric_mapping() -> None:
    observations = parse_sec_product_cycle_driver_html(_filing_html())
    assert len(observations) == 13
    assert observations[0].period_id == "2023Q1"
    assert observations[-1].period_id == "2026Q1"
    assert observations[-1].dram_bit_sales_volume_qoq_text == "Flat"
    assert observations[-1].dram_asp_usd_qoq_text == "Mid-60% Increase"
    assert observations[-1].nand_bit_sales_volume_qoq_text == "Around 10% Decrease"
    assert observations[-1].nand_asp_usd_qoq_text == "Mid 70% Increase"
    assert observations[5].nand_asp_usd_qoq_text == "Mid-high-teen% Increase"


def test_evidence_binds_archived_filing_hash_and_never_enables_numeric_driver() -> None:
    filing = _filing_html()
    evidence = build_sec_product_cycle_driver_support_evidence(
        observed_date=date(2026, 8, 16),
        ticker="000660",
        accession_number="0001193125-26-299963",
        source_profitability_support_evidence_id="a" * 64,
        expected_filing_sha256=hashlib.sha256(filing).hexdigest(),
        filing_bytes=filing,
    )
    assert evidence.observation_count == 13
    assert evidence.textual_band_source_facts is True
    assert evidence.numeric_driver_values_available is False
    assert evidence.product_profitability_source_fact is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.fair_value_estimate_enabled is False
    assert evidence.target_price_enabled is False
    assert evidence.decision_score_enabled is False


def test_evidence_rejects_filing_bytes_that_do_not_match_verified_source_hash() -> None:
    with pytest.raises(ValueError, match="archived filing hash"):
        build_sec_product_cycle_driver_support_evidence(
            observed_date=date(2026, 8, 16),
            ticker="000660",
            accession_number="0001193125-26-299963",
            source_profitability_support_evidence_id="a" * 64,
            expected_filing_sha256="b" * 64,
            filing_bytes=_filing_html(),
        )


def test_parser_fails_closed_when_one_driver_row_has_only_twelve_quarters() -> None:
    bad_html = _filing_html().decode().replace(
        f"<td>{_DRAM_ASP[-1]}</td></tr>",
        "</tr>",
        1,
    )
    with pytest.raises(ValueError, match="13 values"):
        parse_sec_product_cycle_driver_html(bad_html.encode())
