from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from alpha_cycle.intelligence.sk_hynix_historical_product_failure_diagnostics import (
    inventory_historical_product_revenue_failure_diagnostics,
    load_failure_diagnostic,
)


def _write_failure_bundle(root: Path, period: str, *, name: str = "20260816T010203Z") -> Path:
    directory = root / period / "failed" / name
    directory.mkdir(parents=True)
    archive = b"fake-opendart-zip-bytes"
    text = "21. 매출액 (연결)\n당분기\nDRAM\nNAND Flash\n기타\n"
    archive_path = directory / "opendart_document.zip"
    text_path = directory / "normalized_document.txt"
    archive_path.write_bytes(archive)
    text_path.write_bytes(text.encode("utf-8"))
    diagnostic_path = directory / "diagnostic.json"
    diagnostic = {
        "status": "skhynix_opendart_q2_product_revenue_parse_failed",
        "rcept_no": "20240516000001",
        "report_name": "분기보고서 (2024.03)",
        "receipt_date": "2024-05-16",
        "archive_path": str(archive_path),
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "normalized_text_path": str(text_path),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20240516000001",
        "error_type": "ValueError",
        "error": "historical layout differs",
    }
    diagnostic_path.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return diagnostic_path


def test_inventory_verifies_latest_preserved_failure_bundle_and_exposes_path(tmp_path) -> None:
    older = _write_failure_bundle(tmp_path, "2024Q1", name="20260815T010203Z")
    latest = _write_failure_bundle(tmp_path, "2024Q1", name="20260816T010203Z")
    result = inventory_historical_product_revenue_failure_diagnostics(
        ("2024Q1",),
        output=tmp_path,
    )
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert Path(diagnostic.diagnostic_path) == latest.resolve()
    assert Path(diagnostic.diagnostic_path) != older.resolve()
    assert diagnostic.raw_archive_hash_verified is True
    assert diagnostic.normalized_text_hash_verified is True
    assert diagnostic.source_certification_promoted is False
    assert diagnostic.product_profitability_source_fact is False
    assert result.diagnostic_paths == {"2024Q1": str(latest.resolve())}
    assert result.invalid_diagnostics == ()
    assert result.missing_diagnostic_periods == ()
    assert result.diagnostic_bundle_coverage_complete is True
    assert result.diagnostic_bundle_integrity_complete is True


def test_inventory_reports_discovery_failure_without_raw_bundle_as_missing(tmp_path) -> None:
    present = _write_failure_bundle(tmp_path, "2023Q2")
    result = inventory_historical_product_revenue_failure_diagnostics(
        ("2023Q2", "2025Q3"),
        output=tmp_path,
    )
    assert result.diagnostic_paths == {"2023Q2": str(present.resolve())}
    assert result.missing_diagnostic_periods == ("2025Q3",)
    assert result.diagnostic_bundle_coverage_complete is False
    assert result.diagnostic_bundle_integrity_complete is True


def test_inventory_quarantines_tampered_text_without_raising(tmp_path) -> None:
    diagnostic_path = _write_failure_bundle(tmp_path, "2023Q1")
    text_path = diagnostic_path.parent / "normalized_document.txt"
    text_path.write_bytes(b"tampered\r\nnormalized\r\ntext")

    result = inventory_historical_product_revenue_failure_diagnostics(
        ("2023Q1",),
        output=tmp_path,
    )

    assert result.diagnostics == ()
    assert len(result.invalid_diagnostics) == 1
    issue = result.invalid_diagnostics[0]
    assert issue.period_id == "2023Q1"
    assert Path(issue.diagnostic_path) == diagnostic_path.resolve()
    assert "normalized text hash mismatch" in issue.error
    assert result.invalid_diagnostic_paths == {"2023Q1": str(diagnostic_path.resolve())}
    assert result.missing_diagnostic_periods == ()
    assert result.diagnostic_bundle_coverage_complete is True
    assert result.diagnostic_bundle_integrity_complete is False


def test_failure_diagnostic_rejects_tampered_archive(tmp_path) -> None:
    diagnostic_path = _write_failure_bundle(tmp_path, "2024Q2")
    archive_path = diagnostic_path.parent / "opendart_document.zip"
    archive_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="archive hash mismatch"):
        load_failure_diagnostic("2024Q2", diagnostic_path)


def test_failure_diagnostic_rejects_tampered_normalized_text(tmp_path) -> None:
    diagnostic_path = _write_failure_bundle(tmp_path, "2025Q1")
    text_path = diagnostic_path.parent / "normalized_document.txt"
    text_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="normalized text hash mismatch"):
        load_failure_diagnostic("2025Q1", diagnostic_path)
