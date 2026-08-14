"""Decision-facing verification of archived SEC company-level actual evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sec_company_actual import (
    DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY,
    SecCompanyActualEvidence,
    SecCompanyActualMetrics,
    build_sec_company_actual_evidence,
    load_sec_company_actual_registry,
)

DEFAULT_SEC_COMPANY_ACTUAL_POINTER = Path(
    "data/private/live-research/sec-company-actual/latest_sec_company_actual.json"
)
_REQUIRED_FALSE_FLAGS = (
    "audited",
    "product_baseline_eligible",
    "historical_vintage_certified",
    "point_in_time_backtest_eligible",
    "numeric_forecast_enabled",
    "decision_score_enabled",
    "fair_value_estimate_enabled",
    "target_price_enabled",
    "account_api_enabled",
    "holdings_api_enabled",
    "balance_api_enabled",
    "order_api_enabled",
)


def _json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def _require_boundary(payload: dict[str, object]) -> None:
    if payload.get("company_level_actual") is not True:
        raise ValueError("SEC company actual must identify a company-level actual")
    if payload.get("provisional") is not True or payload.get("source_bytes_archived") is not True:
        raise ValueError("SEC company actual required provenance flags are invalid")
    for flag in _REQUIRED_FALSE_FLAGS:
        if payload.get(flag) is not False:
            raise ValueError(f"SEC company actual requires {flag}=false")


def _float(payload: dict[str, object], key: str) -> float:
    try:
        return float(str(payload[key]))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"SEC company actual {key} is invalid") from exc


def load_sec_company_actual_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_SEC_COMPANY_ACTUAL_REGISTRY,
) -> SecCompanyActualEvidence:
    pointer = _json_object(Path(pointer_path), "SEC company actual pointer")
    if pointer.get("status") != "sec_company_actual_captured":
        raise ValueError("SEC company actual pointer status is invalid")
    _require_boundary(pointer)
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("SEC company actual evaluation date mismatch")

    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "SEC company actual manifest",
    )
    payload = _json_object(
        Path(str(pointer.get("company_actual_path", ""))),
        "SEC company actual payload",
    )
    for item in (manifest, payload):
        _require_boundary(item)

    evidence_id = str(pointer.get("evidence_id", ""))
    if len(evidence_id) != 64 or any(
        str(item.get("evidence_id", "")) != evidence_id for item in (manifest, payload)
    ):
        raise ValueError("SEC company actual pointer/manifest/payload evidence mismatch")
    document_id = str(pointer.get("document_id", ""))
    if document_id != str(manifest.get("document_id", "")) or document_id != str(
        payload.get("document_id", "")
    ):
        raise ValueError("SEC company actual persisted document identity mismatch")
    specs = load_sec_company_actual_registry(registry_path)
    if document_id not in specs:
        raise ValueError("SEC company actual document is not in the checked-in registry")
    spec = specs[document_id]

    submissions_path = Path(str(pointer.get("submissions_path", "")))
    filing_path = Path(str(pointer.get("filing_path", "")))
    try:
        submissions_bytes = submissions_path.read_bytes()
        filing_bytes = filing_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("SEC company actual archived source bytes are missing") from exc
    submissions_hash = hashlib.sha256(submissions_bytes).hexdigest()
    filing_hash = hashlib.sha256(filing_bytes).hexdigest()
    if submissions_hash != str(payload.get("submissions_sha256", "")) or submissions_hash != str(
        pointer.get("submissions_sha256", "")
    ):
        raise ValueError("SEC submissions archive hash mismatch")
    if filing_hash != str(payload.get("filing_sha256", "")) or filing_hash != str(
        pointer.get("filing_sha256", "")
    ):
        raise ValueError("SEC filing archive hash mismatch")

    reconstructed = build_sec_company_actual_evidence(
        spec,
        evaluation_date=evaluation_date,
        submissions_bytes=submissions_bytes,
        filing_bytes=filing_bytes,
    )
    if reconstructed.evidence_id != evidence_id:
        raise ValueError("SEC company actual does not reproduce from archived official bytes")
    persisted = SecCompanyActualMetrics(
        unit=str(payload.get("unit", "")),
        revenue=_float(payload, "revenue"),
        operating_income=_float(payload, "operating_income"),
        net_income=_float(payload, "net_income"),
    )
    if reconstructed.metrics != persisted:
        raise ValueError("SEC company actual metrics do not reproduce from archived filing")
    if reconstructed.accession_number != str(payload.get("accession_number", "")):
        raise ValueError("SEC company actual accession identity mismatch")
    if reconstructed.primary_document != str(payload.get("primary_document", "")):
        raise ValueError("SEC company actual primary-document identity mismatch")
    return reconstructed


def append_sec_company_actual_report(report: str, evidence: SecCompanyActualEvidence) -> str:
    lines = [
        report.rstrip(),
        "",
        "## SEC 6-K 잠정실적 Actual (회사 전체·독립공식교차검증)",
        "",
        (
            f"- `{evidence.ticker}` {evidence.issuer_name} / accession "
            f"`{evidence.accession_number}` / filing `{evidence.filing_date.isoformat()}`"
        ),
        "- SEC submissions JSON과 filing HTML raw bytes를 모두 archive하고 다시 파싱합니다.",
        (
            "- 회사 전체 잠정실적 actual만 제공하며 DRAM/NAND/HBM 제품 baseline, "
            "forecast, valuation, score에는 직접 사용하지 않습니다."
        ),
        "",
        "| 항목 | KRW tn |",
        "|---|---:|",
        f"| revenue | {evidence.metrics.revenue / 1_000_000:.3f} |",
        f"| operating income | {evidence.metrics.operating_income / 1_000_000:.3f} |",
        f"| net income | {evidence.metrics.net_income / 1_000_000:.3f} |",
        "",
        "- source bytes archived: `true`; product baseline eligible: `false`; score: `false`",
    ]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_SEC_COMPANY_ACTUAL_POINTER",
    "append_sec_company_actual_report",
    "load_sec_company_actual_decision_evidence",
]
