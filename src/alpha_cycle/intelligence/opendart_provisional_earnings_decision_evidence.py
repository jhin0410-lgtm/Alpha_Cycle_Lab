"""Decision-facing verified company-level OpenDART provisional earnings evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.opendart_provisional_earnings import (
    DEFAULT_PROVISIONAL_EARNINGS_REGISTRY,
    ProvisionalEarningsMetrics,
    load_provisional_earnings_registry,
    parse_provisional_earnings_text,
)

DEFAULT_PROVISIONAL_EARNINGS_POINTER = Path(
    "data/private/live-research/opendart-provisional-earnings/"
    "latest_opendart_provisional_earnings.json"
)
_REQUIRED_FALSE_FLAGS = (
    "product_baseline_eligible",
    "source_archive_bytes_archived",
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


@dataclass(frozen=True)
class ProvisionalEarningsDecisionEvidence:
    evidence_id: str
    evaluation_date: date
    document_id: str
    ticker: str
    issuer_name: str
    rcept_no: str
    receipt_date: date
    period_start: date
    period_end: date
    metrics: ProvisionalEarningsMetrics
    text_sha256: str
    archive_sha256: str
    company_level_actual: bool = True
    product_baseline_eligible: bool = False
    provisional: bool = True
    audited: bool = False
    decision_score_enabled: bool = False
    numeric_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.text_sha256) != 64 or len(self.archive_sha256) != 64:
            raise ValueError("Provisional earnings decision hashes must be SHA-256")
        if not self.company_level_actual or not self.provisional or self.audited:
            raise ValueError("Provisional earnings decision evidence has invalid actual-status flags")
        if self.product_baseline_eligible or self.decision_score_enabled or self.numeric_forecast_enabled:
            raise ValueError("Provisional earnings decision evidence exceeds its trust boundary")


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


def _require_false(payload: dict[str, object]) -> None:
    for key in _REQUIRED_FALSE_FLAGS:
        if payload.get(key) is not False:
            raise ValueError(f"Provisional earnings evidence requires {key}=false")


def _float(payload: dict[str, object], key: str) -> float:
    try:
        return float(str(payload[key]))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Provisional earnings {key} is invalid") from exc


def load_opendart_provisional_earnings_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
    registry_path: str | Path = DEFAULT_PROVISIONAL_EARNINGS_REGISTRY,
) -> ProvisionalEarningsDecisionEvidence:
    pointer = _json_object(Path(pointer_path), "Provisional earnings pointer")
    if pointer.get("status") != "opendart_provisional_earnings_captured":
        raise ValueError("Provisional earnings pointer status is invalid")
    _require_false(pointer)
    if pointer.get("company_level_actual") is not True:
        raise ValueError("Provisional earnings pointer must identify a company-level actual")
    if pointer.get("normalized_document_text_archived") is not True:
        raise ValueError("Provisional earnings normalized source text must be archived")
    pointer_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if pointer_date != evaluation_date:
        raise ValueError("Provisional earnings evaluation date mismatch")

    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "Provisional earnings manifest",
    )
    payload = _json_object(
        Path(str(pointer.get("provisional_earnings_path", ""))),
        "Provisional earnings payload",
    )
    metadata = _json_object(
        Path(str(pointer.get("document_metadata_path", ""))),
        "Provisional earnings document metadata",
    )
    for item in (manifest, payload):
        _require_false(item)
        if item.get("company_level_actual") is not True:
            raise ValueError("Provisional earnings persisted actual-status flag is invalid")
        if item.get("normalized_document_text_archived") is not True:
            raise ValueError("Provisional earnings persisted text-archive flag is invalid")

    evidence_id = str(pointer.get("evidence_id", ""))
    if len(evidence_id) != 64 or any(
        str(item.get("evidence_id", "")) != evidence_id for item in (manifest, payload)
    ):
        raise ValueError("Provisional earnings pointer/manifest/payload evidence mismatch")
    document_id = str(pointer.get("document_id", ""))
    if document_id != str(manifest.get("document_id", "")) or document_id != str(
        payload.get("document_id", "")
    ):
        raise ValueError("Provisional earnings persisted document identity mismatch")
    specs = load_provisional_earnings_registry(registry_path)
    if document_id not in specs:
        raise ValueError("Provisional earnings document is not in the checked-in registry")
    spec = specs[document_id]
    ticker = str(pointer.get("ticker", "")).zfill(6)
    if ticker != spec.ticker or ticker != str(payload.get("ticker", "")).zfill(6):
        raise ValueError("Provisional earnings issuer identity mismatch")
    if date.fromisoformat(str(payload.get("receipt_date", ""))) != spec.receipt_date:
        raise ValueError("Provisional earnings receipt date does not match registry")
    if date.fromisoformat(str(payload.get("period_start", ""))) != spec.period_start:
        raise ValueError("Provisional earnings period start does not match registry")
    if date.fromisoformat(str(payload.get("period_end", ""))) != spec.period_end:
        raise ValueError("Provisional earnings period end does not match registry")

    text_path = Path(str(pointer.get("normalized_document_path", "")))
    try:
        text = text_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Provisional earnings normalized document not found: {text_path}") from exc
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    expected_text_hash = str(payload.get("text_sha256", ""))
    if text_hash != expected_text_hash or text_hash != str(metadata.get("text_sha256", "")):
        raise ValueError("Provisional earnings normalized document hash mismatch")
    if metadata.get("text_truncated") is not False:
        raise ValueError("Provisional earnings decision evidence refuses truncated text")
    if metadata.get("source_archive_bytes_archived") is not False:
        raise ValueError("Provisional earnings archive-byte provenance flag is invalid")
    if metadata.get("normalized_document_text_archived") is not True:
        raise ValueError("Provisional earnings normalized text provenance flag is invalid")

    reparsed = parse_provisional_earnings_text(spec, text)
    persisted = ProvisionalEarningsMetrics(
        unit=str(payload.get("unit", "")),
        revenue=_float(payload, "revenue"),
        operating_income=_float(payload, "operating_income"),
        net_income=_float(payload, "net_income"),
    )
    if reparsed != persisted:
        raise ValueError("Provisional earnings metrics do not reproduce from normalized source text")
    rcept_no = str(pointer.get("rcept_no", ""))
    if len(rcept_no) != 14 or not rcept_no.isdigit() or rcept_no != str(payload.get("rcept_no", "")):
        raise ValueError("Provisional earnings receipt number is invalid or inconsistent")

    return ProvisionalEarningsDecisionEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        document_id=document_id,
        ticker=ticker,
        issuer_name=str(payload.get("issuer_name", "")),
        rcept_no=rcept_no,
        receipt_date=spec.receipt_date,
        period_start=spec.period_start,
        period_end=spec.period_end,
        metrics=persisted,
        text_sha256=text_hash,
        archive_sha256=str(payload.get("archive_sha256", "")),
    )


def append_opendart_provisional_earnings_report(
    report: str,
    evidence: ProvisionalEarningsDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## OpenDART 잠정실적 Actual (회사 전체·비점수)",
        "",
        (
            f"- `{evidence.ticker}` {evidence.issuer_name} / receipt `{evidence.rcept_no}` / "
            f"period `{evidence.period_end.isoformat()}`"
        ),
        (
            "- OpenDART original-document normalized text를 다시 파싱해 persisted actual과 "
            "일치할 때만 사용합니다."
        ),
        (
            "- 이 evidence는 회사 전체 잠정실적 actual이며 DRAM/NAND/HBM 제품 baseline이나 "
            "forward forecast로 사용할 수 없습니다."
        ),
        (
            "- 현재 provider는 original ZIP의 SHA-256은 보존하지만 ZIP bytes 자체를 local "
            "artifact에 보존하지 않으므로 historical-vintage/PIT 인증은 비활성입니다."
        ),
        "",
        "| 항목 | KRW tn |",
        "|---|---:|",
        f"| revenue | {evidence.metrics.revenue / 1_000_000:.3f} |",
        f"| operating income | {evidence.metrics.operating_income / 1_000_000:.3f} |",
        f"| net income | {evidence.metrics.net_income / 1_000_000:.3f} |",
        "",
        "- provisional: `true`; audited: `false`; product baseline eligible: `false`; score: `false`",
    ]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_PROVISIONAL_EARNINGS_POINTER",
    "ProvisionalEarningsDecisionEvidence",
    "append_opendart_provisional_earnings_report",
    "load_opendart_provisional_earnings_decision_evidence",
]
