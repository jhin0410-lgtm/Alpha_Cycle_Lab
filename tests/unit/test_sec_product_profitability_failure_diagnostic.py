from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.sec_product_profitability_failure_diagnostic import (
    preserve_sec_product_profitability_failure,
)
from alpha_cycle.intelligence.sec_product_profitability_support import (
    SecProductProfitabilitySupportSpec,
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
        required_identity_anchors=("anchor",),
    )


def test_failure_diagnostic_preserves_re_downloaded_official_bytes(monkeypatch, tmp_path) -> None:
    import alpha_cycle.intelligence.sec_product_profitability_failure_diagnostic as module

    submissions = b'{"filings":{"recent":{}}}'
    filing = b"<html><body>live pinned filing</body></html>"

    def fake_download(url: str, *, user_agent: str, timeout_seconds: float) -> bytes:
        assert user_agent == "AlphaCycleLab test@example.com"
        assert timeout_seconds == 7.0
        return submissions if "submissions" in url else filing

    monkeypatch.setattr(module, "download_sec_bytes", fake_download)
    diagnostic_path = preserve_sec_product_profitability_failure(
        _spec(),
        observed_date=date(2026, 8, 16),
        user_agent="AlphaCycleLab test@example.com",
        original_error=ValueError("nand count=0"),
        output=tmp_path,
        timeout_seconds=7.0,
        captured_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
    )

    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["status"] == "sec_product_profitability_support_capture_failed"
    assert diagnostic["original_error_type"] == "ValueError"
    assert diagnostic["original_error"] == "nand count=0"
    assert diagnostic["raw_bytes_available"] is True
    assert diagnostic["submissions_sha256"] == hashlib.sha256(submissions).hexdigest()
    assert diagnostic["filing_sha256"] == hashlib.sha256(filing).hexdigest()
    assert Path(diagnostic["submissions_path"]).read_bytes() == submissions
    assert Path(diagnostic["filing_path"]).read_bytes() == filing
    assert diagnostic["source_certification_promoted"] is False
    assert diagnostic["product_profitability_source_fact"] is False
    assert diagnostic["numeric_forecast_enabled"] is False
    assert diagnostic["decision_score_enabled"] is False


def test_failure_diagnostic_survives_re_download_failure(monkeypatch, tmp_path) -> None:
    import alpha_cycle.intelligence.sec_product_profitability_failure_diagnostic as module

    def failing_download(url: str, *, user_agent: str, timeout_seconds: float) -> bytes:
        del url, user_agent, timeout_seconds
        raise OSError("network unavailable")

    monkeypatch.setattr(module, "download_sec_bytes", failing_download)
    diagnostic_path = preserve_sec_product_profitability_failure(
        _spec(),
        observed_date=date(2026, 8, 16),
        user_agent="AlphaCycleLab test@example.com",
        original_error=ValueError("parser failed"),
        output=tmp_path,
        captured_at=datetime(2026, 8, 16, 12, 0, tzinfo=UTC),
    )
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["raw_bytes_available"] is False
    assert diagnostic["submissions_path"] is None
    assert diagnostic["filing_path"] is None
    assert "network unavailable" in diagnostic["submissions_download_error"]
    assert "network unavailable" in diagnostic["filing_download_error"]
    assert diagnostic["original_error"] == "parser failed"
