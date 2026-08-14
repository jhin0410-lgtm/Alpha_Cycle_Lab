from __future__ import annotations

import json
from datetime import date

import pytest

from alpha_cycle.intelligence.sec_company_actual import (
    DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY,
    build_sec_company_actual_evidence,
    discover_sec_company_actual,
    load_sec_company_actual_registry,
    parse_sec_company_actual_html,
    validate_sec_user_agent,
)

EVALUATION_DATE = date(2026, 8, 14)


def _spec():
    return load_sec_company_actual_registry(DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY)[
        "skhynix_000660_2026q2_sec_6k_actual"
    ]


def _submissions(*, duplicate: bool = False) -> bytes:
    rows = [
        (
            "0001193125-26-321989",
            "2026-07-29",
            "6-K",
            "d115239d6k.htm",
        ),
        (
            "0001193125-26-316497",
            "2026-07-22",
            "6-K",
            "d67858d6k.htm",
        ),
    ]
    if duplicate:
        rows.insert(1, rows[0])
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": [row[0] for row in rows],
                "filingDate": [row[1] for row in rows],
                "form": [row[2] for row in rows],
                "primaryDocument": [row[3] for row in rows],
            }
        }
    }
    return json.dumps(payload).encode("utf-8")


def _filing_html() -> bytes:
    return b"""
<html><body>
<h1>Preliminary Results of Operations</h1>
<div>Basis: Consolidated</div>
<div>Current Period</div>
<div>Second quarter</div>
<div>(unit : in millions of Won or %)</div>
<table>
<tr><td>Revenue</td><td>Quarterly Results</td><td>Year-to-date (YTD) Results</td><td>79,318,746</td><td>131,895,033</td></tr>
<tr><td>Operating Profit (Loss)</td><td>60,542,608</td><td>87,739,123</td></tr>
<tr><td>Profit (Loss) from Continuing Operations Before Income Tax</td><td>128,506,947</td><td>174,427,855</td></tr>
<tr><td>Profit (Loss) for the Period</td><td>93,922,593</td><td>127,498,827</td></tr>
<tr><td>Attributable To: Controlling Interests</td><td>93,935,663</td><td>127,522,594</td></tr>
</table>
<div>Investor Relations, SK hynix</div>
</body></html>
"""


def test_registry_pins_exact_current_official_sec_filing_identity() -> None:
    spec = _spec()

    assert spec.ticker == "000660"
    assert spec.cik == "0002120882"
    assert spec.form == "6-K"
    assert spec.filing_date == date(2026, 7, 29)
    assert spec.expected_accession_number == "0001193125-26-321989"
    assert spec.expected_primary_document == "d115239d6k.htm"
    assert spec.submissions_url == "https://data.sec.gov/submissions/CIK0002120882.json"
    assert spec.filing_url.endswith(
        "/Archives/edgar/data/2120882/000119312526321989/d115239d6k.htm"
    )
    assert spec.company_level_actual is True
    assert spec.product_baseline_eligible is False


def test_pinned_sec_filing_must_resolve_exactly_once_from_submissions() -> None:
    discovered = discover_sec_company_actual(_spec(), _submissions())

    assert discovered.accession_number == "0001193125-26-321989"
    assert discovered.primary_document == "d115239d6k.htm"

    with pytest.raises(ValueError, match="must resolve exactly once"):
        discover_sec_company_actual(_spec(), _submissions(duplicate=True))


def test_sec_filing_parser_reads_current_quarter_company_totals_only() -> None:
    metrics = parse_sec_company_actual_html(_spec(), _filing_html())

    assert metrics.unit == "KRW_million"
    assert metrics.revenue == 79_318_746
    assert metrics.operating_income == 60_542_608
    assert metrics.net_income == 93_922_593


def test_sec_filing_parser_fails_closed_on_identity_or_unit_drift() -> None:
    with pytest.raises(ValueError, match="identity anchor is missing"):
        parse_sec_company_actual_html(
            _spec(),
            _filing_html().replace(b"Investor Relations, SK hynix", b"wrong issuer"),
        )
    with pytest.raises(ValueError, match="unit anchor is missing"):
        parse_sec_company_actual_html(
            _spec(),
            _filing_html().replace(b"in millions of Won or %", b"in unknown units"),
        )


def test_sec_user_agent_requires_declared_contact() -> None:
    assert validate_sec_user_agent("Alpha-Cycle-Lab research contact@example.com") == (
        "Alpha-Cycle-Lab research contact@example.com"
    )
    with pytest.raises(ValueError, match="contact email"):
        validate_sec_user_agent("python-urllib")


def test_sec_evidence_archives_sources_but_stays_non_product_non_scoring() -> None:
    evidence = build_sec_company_actual_evidence(
        _spec(),
        evaluation_date=EVALUATION_DATE,
        submissions_bytes=_submissions(),
        filing_bytes=_filing_html(),
    )

    assert evidence.metrics.revenue == 79_318_746
    assert evidence.source_bytes_archived is True
    assert evidence.company_level_actual is True
    assert evidence.provisional is True
    assert evidence.audited is False
    assert evidence.product_baseline_eligible is False
    assert evidence.historical_vintage_certified is False
    assert evidence.point_in_time_backtest_eligible is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False
