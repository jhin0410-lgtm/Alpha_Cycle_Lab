from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from alpha_cycle.intelligence.sec_product_cycle_driver_support import (
    build_sec_product_cycle_driver_support_evidence,
)
from alpha_cycle.intelligence.sec_product_cycle_driver_support_verifier import (
    load_sec_product_cycle_driver_support_evidence,
)


def _filing() -> bytes:
    periods = tuple(
        f"{quarter}Q {year}"
        for year, quarters in ((2023, 4), (2024, 4), (2025, 4), (2026, 1))
        for quarter in range(1, quarters + 1)
    )
    header = "".join(f"<th>{period}</th>" for period in periods)
    values = "".join("<td>Flat</td>" for _ in periods)
    rows = "".join(
        f"<tr><td>{label}</td>{values}</tr>"
        for label in (
            "DRAM Bit Sales Volume",
            "DRAM Average Selling Price",
            "NAND Flash Bit Sales Volume",
            "NAND Flash Average Selling Price",
        )
    )
    return f"<html><table><tr>{header}</tr>{rows}</table></html>".encode()


def test_verifier_replays_source_bound_filing_bytes(monkeypatch, tmp_path) -> None:
    filing = _filing()
    source = SimpleNamespace(
        ticker="000660",
        evidence_id="s" * 64,
        accession_number="0001193125-26-299963",
        filing_sha256=__import__("hashlib").sha256(filing).hexdigest(),
    )
    evidence = build_sec_product_cycle_driver_support_evidence(
        observed_date=date(2026, 8, 16),
        ticker=source.ticker,
        accession_number=source.accession_number,
        source_profitability_support_evidence_id=source.evidence_id,
        expected_filing_sha256=source.filing_sha256,
        filing_bytes=filing,
    )
    filing_path = tmp_path / "sec_filing.html"
    filing_path.write_bytes(filing)
    source_pointer = tmp_path / "profitability.json"
    source_pointer.write_text("{}", encoding="utf-8")
    support_path = tmp_path / "cycle_driver_support.json"
    manifest_path = tmp_path / "manifest.json"
    boundary = {
        "evidence_id": evidence.evidence_id,
        "source_filing_sha256": evidence.source_filing_sha256,
    }
    support_path.write_text(json.dumps(boundary), encoding="utf-8")
    manifest_path.write_text(json.dumps(boundary), encoding="utf-8")
    pointer = {
        "status": "sec_product_cycle_driver_support_captured",
        "observed_date": "2026-08-16",
        "evidence_id": evidence.evidence_id,
        "source_profitability_support_evidence_id": source.evidence_id,
        "source_filing_sha256": evidence.source_filing_sha256,
        "observation_count": 13,
        "textual_band_source_facts": True,
        "numeric_driver_values_available": False,
        "calibration_support_only": True,
        "current_baseline_eligible": False,
        "product_profitability_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "source_profitability_support_pointer": str(source_pointer),
        "source_filing_path": str(filing_path),
        "support_path": str(support_path),
        "manifest_path": str(manifest_path),
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    import alpha_cycle.intelligence.sec_product_cycle_driver_support_verifier as module

    monkeypatch.setattr(
        module,
        "load_sec_product_profitability_support_evidence",
        lambda *args, **kwargs: source,
    )
    verified = load_sec_product_cycle_driver_support_evidence(
        pointer_path,
        evaluation_date=date(2026, 8, 16),
    )
    assert verified.evidence_id == evidence.evidence_id
    assert verified.observation_count == 13
    assert verified.numeric_driver_values_available is False
