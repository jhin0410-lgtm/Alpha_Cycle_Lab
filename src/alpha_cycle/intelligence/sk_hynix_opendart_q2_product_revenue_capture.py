"""Live SK hynix product-revenue capture using the filing's certified source structure."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from alpha_cycle.intelligence.sk_hynix_opendart_product_revenue_source_consensus import (
    parse_periodic_product_revenue_source_consensus,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT,
    DiscoveredPeriodicProductRevenue,
    OpenDartPeriodicProductRevenueCertification,
    PeriodicProductRevenueSpec,
    _payload,
    discover_periodic_product_revenue,
)
from alpha_cycle.providers.opendart import OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentArchive,
    OpenDartDisclosureDocumentClient,
)


def _certification_dict(
    item: OpenDartPeriodicProductRevenueCertification,
) -> dict[str, object]:
    payload = asdict(item)
    for key in ("evaluation_date", "receipt_date", "period_start", "period_end"):
        payload[key] = getattr(item, key).isoformat()
    return payload


def _write_normalized_text(path: Path, archive: DisclosureDocumentArchive) -> None:
    """Persist the exact UTF-8 bytes covered by the document text SHA-256."""

    text_bytes = archive.evidence.text.encode("utf-8")
    text_sha256 = hashlib.sha256(text_bytes).hexdigest()
    if text_sha256 != archive.evidence.text_sha256:
        raise ValueError("OpenDART normalized text in-memory hash mismatch")
    path.write_bytes(text_bytes)


def build_periodic_product_revenue_certification(
    discovery: DiscoveredPeriodicProductRevenue,
    archive: DisclosureDocumentArchive,
    *,
    evaluation_date: date,
) -> OpenDartPeriodicProductRevenueCertification:
    """Certify direct product revenue under the applicable text/archive source contract."""

    document = archive.evidence
    if document.rcept_no != discovery.rcept_no:
        raise ValueError("OpenDART product revenue receipt/document mismatch")
    if hashlib.sha256(archive.archive_bytes).hexdigest() != document.archive_sha256:
        raise ValueError("OpenDART product revenue raw archive hash mismatch")
    if document.text_truncated:
        raise ValueError("OpenDART product revenue refuses truncated normalized text")
    if discovery.receipt_date > evaluation_date:
        raise ValueError("OpenDART product revenue filing is not yet observable")
    if document.retrieved_at.date() > evaluation_date:
        raise ValueError("OpenDART product revenue retrieval is after evaluation date")

    metrics = parse_periodic_product_revenue_source_consensus(
        discovery.spec,
        document.text,
        archive.archive_bytes,
    )
    payload = _payload(
        discovery,
        document,
        metrics,
        evaluation_date=evaluation_date,
    )
    evidence_id = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return OpenDartPeriodicProductRevenueCertification(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        document_id=discovery.spec.document_id,
        ticker=discovery.spec.ticker,
        issuer_name=discovery.spec.issuer_name,
        rcept_no=discovery.rcept_no,
        report_name=discovery.report_name,
        receipt_date=discovery.receipt_date,
        period_start=discovery.spec.period_start,
        period_end=discovery.spec.period_end,
        metrics=metrics,
        archive_sha256=document.archive_sha256,
        archive_bytes=document.archive_bytes,
        text_sha256=document.text_sha256,
        text_chars=document.text_chars,
        source_url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={discovery.rcept_no}",
    )


def collect_periodic_product_revenue(
    client: OpenDartReadOnlyClient,
    spec: PeriodicProductRevenueSpec,
    *,
    evaluation_date: date,
) -> tuple[
    OpenDartPeriodicProductRevenueCertification,
    DisclosureDocumentArchive,
    DiscoveredPeriodicProductRevenue,
]:
    discovery = discover_periodic_product_revenue(client, spec)
    archive = OpenDartDisclosureDocumentClient(client).document_with_archive(discovery.rcept_no)
    certification = build_periodic_product_revenue_certification(
        discovery,
        archive,
        evaluation_date=evaluation_date,
    )
    return certification, archive, discovery


def _write_failure_bundle(
    root: Path,
    *,
    discovery: DiscoveredPeriodicProductRevenue,
    archive: DisclosureDocumentArchive,
    error: Exception,
    captured_at: datetime,
) -> Path:
    failures = root / "failed"
    failures.mkdir(parents=True, exist_ok=True)
    directory = failures / (
        captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + discovery.rcept_no
    )
    directory.mkdir()
    archive_path = directory / "opendart_document.zip"
    text_path = directory / "normalized_document.txt"
    diagnostic_path = directory / "diagnostic.json"
    archive_path.write_bytes(archive.archive_bytes)
    _write_normalized_text(text_path, archive)
    diagnostic = {
        "status": "skhynix_opendart_q2_product_revenue_parse_failed",
        "captured_at": captured_at.isoformat(),
        "rcept_no": discovery.rcept_no,
        "report_name": discovery.report_name,
        "receipt_date": discovery.receipt_date.isoformat(),
        "retrieved_at": archive.evidence.retrieved_at.isoformat(),
        "archive_path": str(archive_path),
        "archive_sha256": archive.evidence.archive_sha256,
        "archive_bytes": archive.evidence.archive_bytes,
        "normalized_text_path": str(text_path),
        "text_sha256": archive.evidence.text_sha256,
        "text_chars": archive.evidence.text_chars,
        "text_truncated": archive.evidence.text_truncated,
        "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={discovery.rcept_no}",
        "error_type": type(error).__name__,
        "error": str(error),
    }
    diagnostic_path.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return diagnostic_path


def capture_periodic_product_revenue_certification(
    client: OpenDartReadOnlyClient,
    spec: PeriodicProductRevenueSpec,
    *,
    evaluation_date: date,
    output: str | Path = DEFAULT_PERIODIC_PRODUCT_REVENUE_OUTPUT,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Capture a bound source artifact and preserve raw diagnostics on parse failure."""

    captured = captured_at or datetime.now(UTC)
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)

    discovery = discover_periodic_product_revenue(client, spec)
    archive = OpenDartDisclosureDocumentClient(client).document_with_archive(discovery.rcept_no)
    try:
        certification = build_periodic_product_revenue_certification(
            discovery,
            archive,
            evaluation_date=evaluation_date,
        )
    except Exception as exc:
        diagnostic_path = _write_failure_bundle(
            root,
            discovery=discovery,
            archive=archive,
            error=exc,
            captured_at=captured,
        )
        raise ValueError(
            f"{exc}; raw diagnostic evidence preserved at {diagnostic_path}"
        ) from exc

    directory = root / (
        captured.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + "__"
        + certification.evidence_id[:12]
    )
    temporary = root / f".{directory.name}.tmp"
    if directory.exists() or temporary.exists():
        raise ValueError("Periodic product revenue artifact path already exists")
    temporary.mkdir()
    try:
        archive_path = temporary / "opendart_document.zip"
        text_path = temporary / "normalized_document.txt"
        certification_path = temporary / "certification.json"
        archive_path.write_bytes(archive.archive_bytes)
        _write_normalized_text(text_path, archive)
        certification_path.write_text(
            json.dumps(
                _certification_dict(certification),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    pointer = {
        "status": "skhynix_opendart_q2_product_revenue_certified",
        "evidence_id": certification.evidence_id,
        "evaluation_date": evaluation_date.isoformat(),
        "certification_path": str(directory / "certification.json"),
        "archive_path": str(directory / "opendart_document.zip"),
        "archive_sha256": certification.archive_sha256,
        "normalized_text_path": str(directory / "normalized_document.txt"),
        "text_sha256": certification.text_sha256,
        "rcept_no": certification.rcept_no,
        "report_name": certification.report_name,
        "source_url": certification.source_url,
        "product_revenue_baseline_eligible": True,
        "allocation_resolver_registered": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    pointer_path = root / "latest_certification.json"
    temporary_pointer = root / ".latest_certification.json.tmp"
    temporary_pointer.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary_pointer.replace(pointer_path)
    return pointer


__all__ = [
    "build_periodic_product_revenue_certification",
    "capture_periodic_product_revenue_certification",
    "collect_periodic_product_revenue",
]
