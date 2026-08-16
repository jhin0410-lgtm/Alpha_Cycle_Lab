from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sec_product_profitability_support import (
    SecProductProfitabilitySupportSpec,
    build_sec_product_profitability_support_evidence,
)
from alpha_cycle.intelligence.sec_product_profitability_support_verifier import (
    load_sec_product_profitability_support_evidence,
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
    The following table sets forth our revenue by principal product category and the related percentage data for the periods indicated.
    first quarter of 2026
    <p>DRAM W 40,659 77.3% W 14,037 79.6% W 74,904 77.1% W 44,732 67.6% W 20,769 63.4%</p>
    <p>NAND Flash 11,574 22.0% 3,229 18.3% 20,690 21.3% 19,274 29.1% 9,653 29.5%</p>
    <p>Other Products 343 0.7% 373 2.1% 1,552 1.6% 2,187 3.3% 2,344 7.2%</p>
    <p>Total W 52,576 100.0% W 17,639 100.0% W 97,147 100.0% W 66,193 100.0% W 32,766 100.0%</p>
    DRAMs are a type
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


def _registry(path: Path) -> None:
    path.write_text(
        """schema_version: 1
issuers:
  "000660":
    issuer_name: SK hynix
    filings:
      skhynix_000660_2026_sec_424b4_product_profitability_support:
        source_id: sec_edgar
        cik: "0002120882"
        form: 424B4
        filing_date: 2026-07-10
        expected_accession_number: "0001193125-26-299963"
        expected_primary_document: d32785d424b4.htm
        parser_id: skhynix_sec_424b4_product_profitability_support_v1
        calibration_support_only: true
        product_profitability_source_fact: false
        current_baseline_eligible: false
        numeric_forecast_enabled: false
        decision_score_enabled: false
        required_identity_anchors:
          - "The following table sets forth our revenue by principal product category and the related percentage data for the periods indicated"
          - "first quarter of 2026"
          - "gross profit margin increased to 79.3% in the first quarter of 2026 from 57.3% in the first quarter of 2025"
          - "gross profit margin increased to 60.4% in 2025 from 48.1% in 2024"
          - "gross profit margin of 48.1% in 2024 compared to gross loss margin of 1.6% in 2023"
""",
        encoding="utf-8",
    )


def _pointer(tmp_path: Path) -> tuple[Path, Path]:
    observed = date(2026, 8, 16)
    evidence = build_sec_product_profitability_support_evidence(
        _spec(),
        observed_date=observed,
        submissions_bytes=_submissions(),
        filing_bytes=_filing(),
    )
    submissions = tmp_path / "submissions.json"
    filing = tmp_path / "filing.html"
    support = tmp_path / "support.json"
    manifest = tmp_path / "manifest.json"
    registry = tmp_path / "registry.yaml"
    pointer = tmp_path / "pointer.json"
    submissions.write_bytes(_submissions())
    filing.write_bytes(_filing())
    base = {
        "evidence_id": evidence.evidence_id,
        "filing_sha256": evidence.filing_sha256,
    }
    support.write_text(json.dumps(base), encoding="utf-8")
    manifest.write_text(json.dumps(base), encoding="utf-8")
    _registry(registry)
    payload = {
        "status": "sec_product_profitability_support_captured",
        "observed_date": observed.isoformat(),
        "document_id": evidence.document_id,
        "evidence_id": evidence.evidence_id,
        "submissions_sha256": evidence.submissions_sha256,
        "filing_sha256": evidence.filing_sha256,
        "observation_count": evidence.observation_count,
        "independent_non_overlapping_period_count": (
            evidence.independent_non_overlapping_period_count
        ),
        "calibration_support_only": True,
        "product_profitability_source_fact": False,
        "current_baseline_eligible": False,
        "direct_product_profitability_observations": 0,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "submissions_path": str(submissions),
        "filing_path": str(filing),
        "support_path": str(support),
        "manifest_path": str(manifest),
    }
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    return pointer, registry


def test_verifier_replays_archived_source_bytes_and_evidence_id(tmp_path: Path) -> None:
    pointer, registry = _pointer(tmp_path)
    evidence = load_sec_product_profitability_support_evidence(
        pointer,
        evaluation_date=date(2026, 8, 16),
        registry_path=registry,
    )
    assert evidence.observation_count == 5
    assert evidence.independent_non_overlapping_period_count == 4
    assert evidence.product_profitability_source_fact is False


def test_verifier_rejects_filing_byte_tamper(tmp_path: Path) -> None:
    pointer, registry = _pointer(tmp_path)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    filing = Path(payload["filing_path"])
    filing.write_bytes(filing.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="evidence_id does not reproduce|filing hash"):
        load_sec_product_profitability_support_evidence(
            pointer,
            evaluation_date=date(2026, 8, 16),
            registry_path=registry,
        )


def test_verifier_rejects_source_fact_promotion_in_pointer(tmp_path: Path) -> None:
    pointer, registry = _pointer(tmp_path)
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    payload["product_profitability_source_fact"] = True
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="source-fact boundary"):
        load_sec_product_profitability_support_evidence(
            pointer,
            evaluation_date=date(2026, 8, 16),
            registry_path=registry,
        )
