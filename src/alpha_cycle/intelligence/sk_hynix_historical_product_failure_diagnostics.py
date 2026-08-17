"""Verify and inventory raw diagnostics for failed SK hynix historical product parses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_opendart_historical_product_revenue_panel import (
    DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT,
)

_EXPECTED_STATUS = "skhynix_opendart_q2_product_revenue_parse_failed"


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _optional_date(payload: dict[str, object], key: str) -> date | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Historical failure diagnostic {key} is invalid") from exc


def _optional_datetime(payload: dict[str, object], key: str) -> datetime | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"Historical failure diagnostic {key} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Historical failure diagnostic {key} must be timezone-aware")
    return parsed


def _optional_bool(payload: dict[str, object], key: str) -> bool | None:
    if key not in payload:
        return None
    value = payload[key]
    if not isinstance(value, bool):
        raise ValueError(f"Historical failure diagnostic {key} must be boolean")
    return value


def _optional_int(payload: dict[str, object], key: str) -> int | None:
    if key not in payload:
        return None
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Historical failure diagnostic {key} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class HistoricalProductRevenueFailureDiagnostic:
    period_id: str
    diagnostic_path: str
    rcept_no: str
    report_name: str
    archive_path: str
    archive_sha256: str
    normalized_text_path: str
    text_sha256: str
    error_type: str
    error: str
    receipt_date: date | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None
    text_truncated: bool | None = None
    archive_bytes: int | None = None
    text_chars: int | None = None
    raw_archive_hash_verified: bool = True
    normalized_text_hash_verified: bool = True
    source_certification_promoted: bool = False
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Historical failure diagnostic receipt number must be 14 digits")
        if not _valid_sha(self.archive_sha256) or not _valid_sha(self.text_sha256):
            raise ValueError("Historical failure diagnostic hashes must be SHA-256")
        if not self.error_type or not self.error:
            raise ValueError("Historical failure diagnostic must retain parser failure detail")
        if self.retrieved_at is not None and (
            self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None
        ):
            raise ValueError("Historical failure diagnostic retrieved_at must be timezone-aware")
        if (
            self.receipt_date is not None
            and self.retrieved_at is not None
            and self.receipt_date > self.retrieved_at.date()
        ):
            raise ValueError("Historical failure diagnostic retrieval precedes filing receipt")
        if self.source_url is not None and not self.source_url.startswith(
            "https://dart.fss.or.kr/"
        ):
            raise ValueError("Historical failure diagnostic source_url is not official DART")
        if self.archive_bytes is not None and self.archive_bytes < 0:
            raise ValueError("Historical failure diagnostic archive_bytes cannot be negative")
        if self.text_chars is not None and self.text_chars < 0:
            raise ValueError("Historical failure diagnostic text_chars cannot be negative")
        if not self.raw_archive_hash_verified or not self.normalized_text_hash_verified:
            raise ValueError("Historical failure diagnostic must verify preserved raw evidence")
        if (
            self.source_certification_promoted
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Historical failure diagnostic exceeds its trust boundary")

    @property
    def retrieval_provenance_complete(self) -> bool:
        """Return whether the failure retains all facts needed for later replay provenance."""

        return (
            self.receipt_date is not None
            and bool(self.source_url)
            and self.retrieved_at is not None
            and self.text_truncated is False
            and self.archive_bytes is not None
            and self.text_chars is not None
        )


@dataclass(frozen=True)
class HistoricalProductRevenueFailureDiagnosticIntegrityIssue:
    period_id: str
    diagnostic_path: str
    error_type: str
    error: str
    source_certification_promoted: bool = False
    product_profitability_source_fact: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.period_id or not self.diagnostic_path or not self.error_type or not self.error:
            raise ValueError("Historical failure diagnostic integrity issue is incomplete")
        if (
            self.source_certification_promoted
            or self.product_profitability_source_fact
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Invalid historical failure diagnostic exceeds its trust boundary")


@dataclass(frozen=True)
class HistoricalProductRevenueFailureDiagnosticInventory:
    failed_periods: tuple[str, ...]
    diagnostics: tuple[HistoricalProductRevenueFailureDiagnostic, ...]
    invalid_diagnostics: tuple[HistoricalProductRevenueFailureDiagnosticIntegrityIssue, ...]
    missing_diagnostic_periods: tuple[str, ...]
    diagnostic_bundle_coverage_complete: bool
    diagnostic_bundle_integrity_complete: bool

    def __post_init__(self) -> None:
        diagnostic_periods = tuple(item.period_id for item in self.diagnostics)
        invalid_periods = tuple(item.period_id for item in self.invalid_diagnostics)
        if len(set(diagnostic_periods)) != len(diagnostic_periods):
            raise ValueError("Historical failure diagnostic periods must be unique")
        if len(set(invalid_periods)) != len(invalid_periods):
            raise ValueError("Invalid historical failure diagnostic periods must be unique")
        if set(diagnostic_periods) & set(invalid_periods):
            raise ValueError("Historical failure diagnostic cannot be both valid and invalid")
        covered = set(diagnostic_periods) | set(invalid_periods)
        if not covered.issubset(self.failed_periods):
            raise ValueError("Historical failure diagnostic references a non-failed period")
        expected_missing = tuple(period for period in self.failed_periods if period not in covered)
        if self.missing_diagnostic_periods != expected_missing:
            raise ValueError("Historical failure diagnostic missing-period set is inconsistent")
        if self.diagnostic_bundle_coverage_complete != (not expected_missing):
            raise ValueError("Historical failure diagnostic coverage flag is inconsistent")
        if self.diagnostic_bundle_integrity_complete != (not invalid_periods):
            raise ValueError("Historical failure diagnostic integrity flag is inconsistent")

    @property
    def diagnostic_paths(self) -> dict[str, str]:
        return {item.period_id: item.diagnostic_path for item in self.diagnostics}

    @property
    def diagnostic_errors(self) -> dict[str, str]:
        return {item.period_id: item.error for item in self.diagnostics}

    @property
    def invalid_diagnostic_paths(self) -> dict[str, str]:
        return {item.period_id: item.diagnostic_path for item in self.invalid_diagnostics}

    @property
    def invalid_diagnostic_errors(self) -> dict[str, str]:
        return {item.period_id: item.error for item in self.invalid_diagnostics}


def _latest_diagnostic_path(period_output: Path) -> Path | None:
    failed_root = period_output / "failed"
    if not failed_root.is_dir():
        return None
    candidates = sorted(
        (path / "diagnostic.json" for path in failed_root.iterdir() if path.is_dir()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return next((path for path in candidates if path.is_file()), None)


def load_failure_diagnostic(
    period_id: str,
    path: str | Path,
) -> HistoricalProductRevenueFailureDiagnostic:
    diagnostic_path = Path(path)
    payload = _object(diagnostic_path, f"Historical product revenue failure {period_id}")
    if payload.get("status") != _EXPECTED_STATUS:
        raise ValueError(f"Historical failure diagnostic status is invalid: {period_id}")
    archive_path = Path(str(payload.get("archive_path", "")))
    text_path = Path(str(payload.get("normalized_text_path", "")))
    try:
        archive_content = archive_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"Historical failure archive is missing: {period_id}") from exc
    try:
        text_content = text_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"Historical failure normalized text is missing: {period_id}") from exc
    archive_sha = hashlib.sha256(archive_content).hexdigest()
    text_sha = hashlib.sha256(text_content).hexdigest()
    if archive_sha != str(payload.get("archive_sha256", "")):
        raise ValueError(f"Historical failure archive hash mismatch: {period_id}")
    if text_sha != str(payload.get("text_sha256", "")):
        raise ValueError(f"Historical failure normalized text hash mismatch: {period_id}")

    archive_bytes = _optional_int(payload, "archive_bytes")
    text_chars = _optional_int(payload, "text_chars")
    if archive_bytes is not None and archive_bytes != len(archive_content):
        raise ValueError(f"Historical failure archive byte count mismatch: {period_id}")
    if text_chars is not None:
        try:
            normalized_text = text_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"Historical failure normalized text is not UTF-8: {period_id}"
            ) from exc
        if text_chars != len(normalized_text):
            raise ValueError(f"Historical failure normalized text char count mismatch: {period_id}")

    receipt_date = _optional_date(payload, "receipt_date")
    retrieved_at = _optional_datetime(payload, "retrieved_at")
    source_url_raw = payload.get("source_url")
    source_url = None if source_url_raw is None else str(source_url_raw).strip() or None
    text_truncated = _optional_bool(payload, "text_truncated")

    return HistoricalProductRevenueFailureDiagnostic(
        period_id=period_id,
        diagnostic_path=str(diagnostic_path.resolve()),
        rcept_no=str(payload.get("rcept_no", "")),
        report_name=str(payload.get("report_name", "")),
        archive_path=str(archive_path.resolve()),
        archive_sha256=archive_sha,
        normalized_text_path=str(text_path.resolve()),
        text_sha256=text_sha,
        error_type=str(payload.get("error_type", "")),
        error=str(payload.get("error", "")),
        receipt_date=receipt_date,
        source_url=source_url,
        retrieved_at=retrieved_at,
        text_truncated=text_truncated,
        archive_bytes=archive_bytes,
        text_chars=text_chars,
    )


def inventory_historical_product_revenue_failure_diagnostics(
    failed_periods: tuple[str, ...],
    *,
    output: str | Path = DEFAULT_HISTORICAL_PRODUCT_REVENUE_OUTPUT,
) -> HistoricalProductRevenueFailureDiagnosticInventory:
    """Verify newest raw diagnostics, quarantining integrity failures as operational issues."""

    root = Path(output)
    diagnostics: list[HistoricalProductRevenueFailureDiagnostic] = []
    invalid: list[HistoricalProductRevenueFailureDiagnosticIntegrityIssue] = []
    periods_with_bundle: set[str] = set()
    for period_id in failed_periods:
        path = _latest_diagnostic_path(root / period_id)
        if path is None:
            continue
        periods_with_bundle.add(period_id)
        try:
            diagnostics.append(load_failure_diagnostic(period_id, path))
        except ValueError as exc:
            invalid.append(
                HistoricalProductRevenueFailureDiagnosticIntegrityIssue(
                    period_id=period_id,
                    diagnostic_path=str(path.resolve()),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
    missing = tuple(period for period in failed_periods if period not in periods_with_bundle)
    return HistoricalProductRevenueFailureDiagnosticInventory(
        failed_periods=failed_periods,
        diagnostics=tuple(diagnostics),
        invalid_diagnostics=tuple(invalid),
        missing_diagnostic_periods=missing,
        diagnostic_bundle_coverage_complete=not missing,
        diagnostic_bundle_integrity_complete=not invalid,
    )


__all__ = [
    "HistoricalProductRevenueFailureDiagnostic",
    "HistoricalProductRevenueFailureDiagnosticIntegrityIssue",
    "HistoricalProductRevenueFailureDiagnosticInventory",
    "inventory_historical_product_revenue_failure_diagnostics",
    "load_failure_diagnostic",
]
