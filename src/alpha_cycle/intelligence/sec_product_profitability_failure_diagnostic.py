"""Operational raw-evidence preservation for failed SEC profitability captures.

This module is deliberately outside the certified evidence path.  It exists so a live
parser failure leaves reproducible official bytes and hashes for the next parser repair.
A failure bundle can never promote source facts or open downstream model gates.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.sec_company_actual import download_sec_bytes
from alpha_cycle.intelligence.sec_product_profitability_support import (
    DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT,
    SecProductProfitabilitySupportSpec,
)

_KOREA_TIME_ZONE = ZoneInfo("Asia/Seoul")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preserve_sec_product_profitability_failure(
    spec: SecProductProfitabilitySupportSpec,
    *,
    observed_date: date,
    user_agent: str,
    original_error: Exception,
    output: str | Path = DEFAULT_SEC_PRODUCT_PROFITABILITY_OUTPUT,
    timeout_seconds: float = 20.0,
    captured_at: datetime | None = None,
) -> Path:
    """Preserve official SEC bytes after a failed certification attempt and return diagnostic."""

    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("SEC profitability failure captured_at must be timezone-aware")
    if captured.astimezone(_KOREA_TIME_ZONE).date() < observed_date:
        raise ValueError("SEC profitability failure capture cannot predate observed_date")

    root = Path(output) / "failed"
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + spec.expected_accession_number.replace("-", "")
    )
    if directory.exists():
        raise ValueError(f"SEC profitability failure artifact already exists: {directory}")
    directory.mkdir()

    submissions_path = directory / "sec_submissions.json"
    filing_path = directory / "sec_filing.html"
    submissions_error: str | None = None
    filing_error: str | None = None
    submissions_sha256: str | None = None
    filing_sha256: str | None = None

    try:
        submissions_bytes = download_sec_bytes(
            spec.submissions_url,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
        )
        submissions_path.write_bytes(submissions_bytes)
        submissions_sha256 = _sha(submissions_bytes)
    except Exception as exc:  # diagnostic capture must retain the original parser failure
        submissions_error = f"{type(exc).__name__}: {exc}"

    try:
        filing_bytes = download_sec_bytes(
            spec.filing_url,
            user_agent=user_agent,
            timeout_seconds=timeout_seconds,
        )
        filing_path.write_bytes(filing_bytes)
        filing_sha256 = _sha(filing_bytes)
    except Exception as exc:  # diagnostic capture must retain the original parser failure
        filing_error = f"{type(exc).__name__}: {exc}"

    diagnostic = {
        "schema_version": 1,
        "status": "sec_product_profitability_support_capture_failed",
        "captured_at": captured.isoformat(),
        "observed_date": observed_date.isoformat(),
        "document_id": spec.document_id,
        "ticker": spec.ticker,
        "accession_number": spec.expected_accession_number,
        "primary_document": spec.expected_primary_document,
        "submissions_url": spec.submissions_url,
        "filing_url": spec.filing_url,
        "submissions_path": str(submissions_path.resolve()) if submissions_sha256 else None,
        "submissions_sha256": submissions_sha256,
        "filing_path": str(filing_path.resolve()) if filing_sha256 else None,
        "filing_sha256": filing_sha256,
        "submissions_download_error": submissions_error,
        "filing_download_error": filing_error,
        "original_error_type": type(original_error).__name__,
        "original_error": str(original_error),
        "raw_bytes_available": submissions_sha256 is not None and filing_sha256 is not None,
        "source_certification_promoted": False,
        "product_profitability_source_fact": False,
        "numeric_forecast_enabled": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
    }
    diagnostic_path = directory / "diagnostic.json"
    diagnostic_path.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return diagnostic_path.resolve()


__all__ = ["preserve_sec_product_profitability_failure"]
