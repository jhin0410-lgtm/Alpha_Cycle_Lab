from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sec_company_actual import (
    DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY,
    build_sec_company_actual_evidence,
    load_sec_company_actual_registry,
)
from alpha_cycle.intelligence.sec_company_actual_decision_evidence import (
    load_sec_company_actual_decision_evidence,
)

EVALUATION_DATE = date(2026, 8, 14)
DOCUMENT_ID = "skhynix_000660_2026q2_sec_6k_actual"


def _submissions() -> bytes:
    return json.dumps(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001193125-26-321989"],
                    "filingDate": ["2026-07-29"],
                    "form": ["6-K"],
                    "primaryDocument": ["d115239d6k.htm"],
                }
            }
        }
    ).encode("utf-8")


def _filing_html() -> bytes:
    return b"""
<html><body>
<h1>Preliminary Results of Operations</h1>
<div>Basis: Consolidated</div><div>Current Period</div><div>Second quarter</div>
<div>(unit : in millions of Won or %)</div>
<table>
<tr><td>Revenue</td><td>79,318,746</td><td>131,895,033</td></tr>
<tr><td>Operating Profit (Loss)</td><td>60,542,608</td><td>87,739,123</td></tr>
<tr><td>Profit (Loss) from Continuing Operations Before Income Tax</td><td>128,506,947</td><td>174,427,855</td></tr>
<tr><td>Profit (Loss) for the Period</td><td>93,922,593</td><td>127,498,827</td></tr>
<tr><td>Attributable To: Controlling Interests</td><td>93,935,663</td><td>127,522,594</td></tr>
</table>
<div>Investor Relations, SK hynix</div>
</body></html>
"""


def _false_flags() -> dict[str, object]:
    return {
        "audited": False,
        "product_baseline_eligible": False,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }


def _pointer(tmp_path: Path) -> Path:
    spec = load_sec_company_actual_registry(DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY)[DOCUMENT_ID]
    submissions = _submissions()
    filing = _filing_html()
    evidence = build_sec_company_actual_evidence(
        spec,
        evaluation_date=EVALUATION_DATE,
        submissions_bytes=submissions,
        filing_bytes=filing,
    )
    root = tmp_path / "sec"
    root.mkdir()
    submissions_path = root / "submissions.json"
    filing_path = root / "filing.html"
    submissions_path.write_bytes(submissions)
    filing_path.write_bytes(filing)
    payload = {
        **_false_flags(),
        "evidence_id": evidence.evidence_id,
        "evaluation_date": EVALUATION_DATE.isoformat(),
        "document_id": DOCUMENT_ID,
        "ticker": evidence.ticker,
        "issuer_name": evidence.issuer_name,
        "accession_number": evidence.accession_number,
        "primary_document": evidence.primary_document,
        "filing_date": evidence.filing_date.isoformat(),
        "period_start": evidence.period_start.isoformat(),
        "period_end": evidence.period_end.isoformat(),
        "submissions_url": evidence.submissions_url,
        "filing_url": evidence.filing_url,
        "submissions_sha256": evidence.submissions_sha256,
        "filing_sha256": evidence.filing_sha256,
        "unit": evidence.metrics.unit,
        "revenue": evidence.metrics.revenue,
        "operating_income": evidence.metrics.operating_income,
        "net_income": evidence.metrics.net_income,
        "company_level_actual": True,
        "provisional": True,
        "source_bytes_archived": True,
    }
    company_actual_path = root / "company_actual.json"
    manifest_path = root / "manifest.json"
    company_actual_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    pointer = {
        **payload,
        "status": "sec_company_actual_captured",
        "manifest_path": str(manifest_path),
        "company_actual_path": str(company_actual_path),
        "submissions_path": str(submissions_path),
        "filing_path": str(filing_path),
    }
    pointer_path = root / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_loader_rehashes_and_reparses_both_official_sec_sources(tmp_path: Path) -> None:
    evidence = load_sec_company_actual_decision_evidence(
        _pointer(tmp_path),
        evaluation_date=EVALUATION_DATE,
    )

    assert evidence.accession_number == "0001193125-26-321989"
    assert evidence.metrics.revenue == 79_318_746
    assert evidence.metrics.operating_income == 60_542_608
    assert evidence.metrics.net_income == 93_922_593
    assert evidence.source_bytes_archived is True
    assert evidence.product_baseline_eligible is False
    assert evidence.numeric_forecast_enabled is False
    assert evidence.decision_score_enabled is False


def test_loader_rejects_filing_byte_tampering(tmp_path: Path) -> None:
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    filing_path = Path(raw["filing_path"])
    filing_path.write_bytes(_filing_html().replace(b"79,318,746", b"1"))

    with pytest.raises(ValueError, match="filing archive hash mismatch"):
        load_sec_company_actual_decision_evidence(
            pointer,
            evaluation_date=EVALUATION_DATE,
        )


def test_loader_rejects_persisted_metric_tampering(tmp_path: Path) -> None:
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    payload_path = Path(raw["company_actual_path"])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["revenue"] = 1
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="metrics do not reproduce"):
        load_sec_company_actual_decision_evidence(
            pointer,
            evaluation_date=EVALUATION_DATE,
        )


def test_loader_rejects_product_baseline_promotion(tmp_path: Path) -> None:
    pointer = _pointer(tmp_path)
    raw = json.loads(pointer.read_text(encoding="utf-8"))
    raw["product_baseline_eligible"] = True
    pointer.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="product_baseline_eligible=false"):
        load_sec_company_actual_decision_evidence(
            pointer,
            evaluation_date=EVALUATION_DATE,
        )
