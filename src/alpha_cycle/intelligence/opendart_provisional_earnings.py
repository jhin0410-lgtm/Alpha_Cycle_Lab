"""Source-bounded company-level provisional earnings from official OpenDART disclosures.

This layer certifies a disclosed company-level quarterly actual only. It never allocates
company revenue or profit into DRAM, NAND, HBM, Foundry, or any other model block. The
normalized original-document text is archived locally, while OpenDART's downloaded ZIP
bytes are currently represented only by the provider archive hash and therefore are not
claimed to be locally archived point-in-time source bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import yaml

from alpha_cycle.providers.opendart import CorpCode, OpenDartReadOnlyClient
from alpha_cycle.providers.opendart_documents import (
    DisclosureDocumentEvidence,
    OpenDartDisclosureDocumentClient,
)

DEFAULT_PROVISIONAL_EARNINGS_REGISTRY = Path(
    "config/semiconductor_provisional_earnings.yaml"
)
_ALLOWED_UNIT_SCALES = {
    "백만원": ("KRW_million", 1.0),
    "억원": ("KRW_million", 100.0),
}
_AMOUNT_TOKEN = re.compile(r"^-?\(?[0-9][0-9,]*(?:\.[0-9]+)?\)?$")
_METRIC_SECTION_LABELS = frozenset(
    {
        "매출액",
        "영업이익",
        "법인세비용차감전계속사업이익",
        "당기순이익",
        "당기순이익(손실)",
    }
)


@dataclass(frozen=True)
class ProvisionalEarningsSpec:
    document_id: str
    ticker: str
    issuer_name: str
    source_id: str
    report_name_exact: str
    receipt_date: date
    period_start: date
    period_end: date
    parser_id: str
    consolidated_only: bool
    audited: bool
    product_baseline_eligible: bool
    expected_identity_anchors: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Provisional earnings ticker must be six digits")
        if self.source_id != "opendart":
            raise ValueError("Provisional earnings v1 requires the official OpenDART source")
        if self.period_start > self.period_end or self.period_end > self.receipt_date:
            raise ValueError("Provisional earnings accounting/receipt dates are invalid")
        if not self.consolidated_only or self.audited or self.product_baseline_eligible:
            raise ValueError(
                "Provisional earnings v1 must remain consolidated, unaudited, and non-product"
            )
        if not self.report_name_exact.strip() or not self.parser_id.strip():
            raise ValueError("Provisional earnings report/parser identity cannot be blank")
        if not self.expected_identity_anchors:
            raise ValueError("Provisional earnings parser requires identity anchors")


@dataclass(frozen=True)
class DiscoveredProvisionalDisclosure:
    spec: ProvisionalEarningsSpec
    corp: CorpCode
    rcept_no: str
    report_name: str
    receipt_date: date

    def __post_init__(self) -> None:
        if len(self.rcept_no) != 14 or not self.rcept_no.isdigit():
            raise ValueError("Provisional earnings receipt number must be 14 digits")
        if self.report_name != self.spec.report_name_exact:
            raise ValueError("Provisional earnings report name is not the registered exact name")
        if self.receipt_date != self.spec.receipt_date:
            raise ValueError("Provisional earnings receipt date does not match registry")
        if self.corp.stock_code != self.spec.ticker:
            raise ValueError("Provisional earnings corporation does not match ticker")


@dataclass(frozen=True)
class ProvisionalEarningsMetrics:
    unit: str
    revenue: float
    operating_income: float
    net_income: float

    def __post_init__(self) -> None:
        if self.unit != "KRW_million":
            raise ValueError("Provisional earnings v1 normalizes amounts to KRW_million")
        if self.revenue <= 0:
            raise ValueError("Provisional earnings revenue must be positive")


@dataclass(frozen=True)
class OpenDartProvisionalEarningsEvidence:
    evidence_id: str
    evaluation_date: date
    document_id: str
    ticker: str
    issuer_name: str
    rcept_no: str
    report_name: str
    receipt_date: date
    period_start: date
    period_end: date
    metrics: ProvisionalEarningsMetrics
    archive_sha256: str
    archive_bytes: int
    text_sha256: str
    text_chars: int
    member_count: int
    text_member_count: int
    source_receipt_certified: bool = True
    parser_semantics_certified: bool = True
    provisional: bool = True
    audited: bool = False
    company_level_actual: bool = True
    product_baseline_eligible: bool = False
    source_archive_bytes_archived: bool = False
    normalized_document_text_archived: bool = True
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.archive_sha256) != 64 or len(self.text_sha256) != 64:
            raise ValueError("Provisional earnings evidence hashes must be SHA-256")
        if self.period_start > self.period_end or self.period_end > self.receipt_date:
            raise ValueError("Provisional earnings evidence dates are invalid")
        if self.receipt_date > self.evaluation_date:
            raise ValueError("Provisional earnings disclosure cannot be future evidence")
        if not (
            self.source_receipt_certified
            and self.parser_semantics_certified
            and self.provisional
            and self.company_level_actual
            and self.normalized_document_text_archived
        ):
            raise ValueError("Provisional earnings required evidence flags are not certified")
        if (
            self.audited
            or self.product_baseline_eligible
            or self.source_archive_bytes_archived
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Provisional earnings v1 exceeds its permitted trust boundary")


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"Provisional earnings {label} must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"Provisional earnings {label} entries must be strings")
        text = item.strip()
        if text:
            result.append(text)
    if not result:
        raise ValueError(f"Provisional earnings {label} cannot be empty")
    return tuple(result)


def _strict_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Provisional earnings {label} must be boolean")
    return value


def load_provisional_earnings_registry(
    path: str | Path = DEFAULT_PROVISIONAL_EARNINGS_REGISTRY,
) -> dict[str, ProvisionalEarningsSpec]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("issuers"), dict):
        raise ValueError("Provisional earnings registry must contain issuers")
    specs: dict[str, ProvisionalEarningsSpec] = {}
    issuers = cast(dict[object, object], payload["issuers"])
    for ticker_raw, issuer_value in issuers.items():
        ticker = str(ticker_raw).strip().zfill(6)
        if not isinstance(issuer_value, dict):
            raise ValueError(f"Provisional earnings issuer entry must be an object: {ticker}")
        issuer = cast(dict[object, object], issuer_value)
        issuer_name = str(issuer.get("issuer_name", "")).strip()
        disclosures = issuer.get("disclosures", {})
        if not isinstance(disclosures, dict):
            raise ValueError(f"Provisional earnings disclosures must be an object: {ticker}")
        for raw_id, raw_value in cast(dict[object, object], disclosures).items():
            document_id = str(raw_id).strip()
            if not isinstance(raw_value, dict):
                raise ValueError(f"Provisional earnings disclosure must be an object: {document_id}")
            raw = cast(dict[object, object], raw_value)
            spec = ProvisionalEarningsSpec(
                document_id=document_id,
                ticker=ticker,
                issuer_name=issuer_name,
                source_id=str(raw.get("source_id", "")).strip(),
                report_name_exact=str(raw.get("report_name_exact", "")).strip(),
                receipt_date=date.fromisoformat(str(raw.get("receipt_date", ""))),
                period_start=date.fromisoformat(str(raw.get("period_start", ""))),
                period_end=date.fromisoformat(str(raw.get("period_end", ""))),
                parser_id=str(raw.get("parser_id", "")).strip(),
                consolidated_only=_strict_bool(raw.get("consolidated_only"), "consolidated_only"),
                audited=_strict_bool(raw.get("audited"), "audited"),
                product_baseline_eligible=_strict_bool(
                    raw.get("product_baseline_eligible"), "product_baseline_eligible"
                ),
                expected_identity_anchors=_string_tuple(
                    raw.get("expected_identity_anchors", []), "expected_identity_anchors"
                ),
            )
            if document_id in specs:
                raise ValueError(f"Provisional earnings document is duplicated: {document_id}")
            specs[document_id] = spec
    if not specs:
        raise ValueError("Provisional earnings registry is empty")
    return specs


def discover_provisional_disclosure(
    client: OpenDartReadOnlyClient,
    spec: ProvisionalEarningsSpec,
) -> DiscoveredProvisionalDisclosure:
    corp = client.resolve_stock_codes([spec.ticker])[spec.ticker]
    batch = client.disclosures(
        corp,
        begin_date=spec.receipt_date,
        end_date=spec.receipt_date,
    )
    frame = batch.frame
    if frame.empty:
        raise ValueError("OpenDART provisional earnings disclosure was not found")
    exact = frame.loc[
        frame["report_name"].astype(str).eq(spec.report_name_exact)
        & frame["receipt_date"].eq(spec.receipt_date)
        & ~frame["is_correction"].astype(bool)
    ].copy()
    if len(exact) != 1:
        matches = ",".join(exact["rcept_no"].astype(str).tolist()) if not exact.empty else "none"
        raise ValueError(
            "OpenDART provisional earnings exact disclosure match must be unique: "
            f"count={len(exact)} receipts={matches}"
        )
    row = exact.iloc[0]
    return DiscoveredProvisionalDisclosure(
        spec=spec,
        corp=corp,
        rcept_no=str(row["rcept_no"]),
        report_name=str(row["report_name"]),
        receipt_date=cast(date, row["receipt_date"]),
    )


def _normalize_lines(text: str) -> tuple[str, ...]:
    return tuple(" ".join(line.replace("\u00a0", " ").split()) for line in text.splitlines() if line.strip())


def _require_anchor(lines: tuple[str, ...], anchor: str) -> None:
    joined = "\n".join(lines).casefold()
    if " ".join(anchor.split()).casefold() not in joined:
        raise ValueError(f"OpenDART provisional earnings identity anchor is missing: {anchor}")


def _parse_amount_token(value: str) -> float | None:
    token = value.strip().replace(" ", "")
    if not _AMOUNT_TOKEN.fullmatch(token):
        return None
    negative = token.startswith("(") and token.endswith(")")
    stripped = token.strip("()").replace(",", "")
    if stripped.startswith("-"):
        negative = True
        stripped = stripped[1:]
    amount = float(stripped)
    return -amount if negative else amount


def _unit_scale(lines: tuple[str, ...]) -> tuple[str, float]:
    candidates = [line for line in lines if "단위" in line]
    for line in candidates:
        for marker, result in _ALLOWED_UNIT_SCALES.items():
            if marker in line:
                return result
    raise ValueError("OpenDART provisional earnings unit is not an allowed KRW unit")


def _current_amount(lines: tuple[str, ...], labels: tuple[str, ...], metric: str) -> float:
    indices = [index for index, line in enumerate(lines) if line in labels]
    if len(indices) != 1:
        raise ValueError(
            f"OpenDART provisional earnings metric label must be unique: {metric} count={len(indices)}"
        )
    start = indices[0]
    section_end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index] in _METRIC_SECTION_LABELS
        ),
        len(lines),
    )
    window = lines[start + 1 : section_end]
    current_positions = [index for index, line in enumerate(window) if line == "당해실적"]
    if len(current_positions) != 1:
        raise ValueError(
            f"OpenDART provisional earnings current-period marker is ambiguous: {metric}"
        )
    after = window[current_positions[0] + 1 : current_positions[0] + 7]
    amounts = [value for item in after if (value := _parse_amount_token(item)) is not None]
    if not amounts:
        raise ValueError(f"OpenDART provisional earnings current amount is missing: {metric}")
    return amounts[0]


def parse_provisional_earnings_text(
    spec: ProvisionalEarningsSpec,
    text: str,
) -> ProvisionalEarningsMetrics:
    if spec.parser_id != "skhynix_opendart_provisional_2026q2_v1":
        raise ValueError("Provisional earnings parser received an unsupported parser_id")
    lines = _normalize_lines(text)
    if not lines:
        raise ValueError("OpenDART provisional earnings document text is empty")
    for anchor in spec.expected_identity_anchors:
        _require_anchor(lines, anchor)
    unit, scale_to_million = _unit_scale(lines)
    del unit
    revenue = _current_amount(lines, ("매출액",), "revenue") * scale_to_million
    operating_income = _current_amount(lines, ("영업이익",), "operating_income") * scale_to_million
    net_income = _current_amount(
        lines,
        ("당기순이익", "당기순이익(손실)"),
        "net_income",
    ) * scale_to_million
    return ProvisionalEarningsMetrics(
        unit="KRW_million",
        revenue=revenue,
        operating_income=operating_income,
        net_income=net_income,
    )


def build_provisional_earnings_evidence(
    discovery: DiscoveredProvisionalDisclosure,
    document: DisclosureDocumentEvidence,
    *,
    evaluation_date: date,
) -> OpenDartProvisionalEarningsEvidence:
    if document.rcept_no != discovery.rcept_no:
        raise ValueError("OpenDART provisional earnings receipt/document mismatch")
    if document.text_truncated:
        raise ValueError("OpenDART provisional earnings parser refuses truncated original text")
    if document.retrieved_at.date() > evaluation_date:
        raise ValueError("OpenDART provisional earnings retrieval is after evaluation date")
    metrics = parse_provisional_earnings_text(discovery.spec, document.text)
    payload: dict[str, object] = {
        "evaluation_date": evaluation_date.isoformat(),
        "document_id": discovery.spec.document_id,
        "ticker": discovery.spec.ticker,
        "rcept_no": discovery.rcept_no,
        "report_name": discovery.report_name,
        "receipt_date": discovery.receipt_date.isoformat(),
        "period_start": discovery.spec.period_start.isoformat(),
        "period_end": discovery.spec.period_end.isoformat(),
        "unit": metrics.unit,
        "revenue": metrics.revenue,
        "operating_income": metrics.operating_income,
        "net_income": metrics.net_income,
        "archive_sha256": document.archive_sha256,
        "archive_bytes": document.archive_bytes,
        "text_sha256": document.text_sha256,
        "text_chars": document.text_chars,
        "member_count": document.member_count,
        "text_member_count": document.text_member_count,
        "source_receipt_certified": True,
        "parser_semantics_certified": True,
        "provisional": True,
        "audited": False,
        "company_level_actual": True,
        "product_baseline_eligible": False,
        "source_archive_bytes_archived": False,
        "normalized_document_text_archived": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    evidence_id = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return OpenDartProvisionalEarningsEvidence(
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
        member_count=document.member_count,
        text_member_count=document.text_member_count,
    )


def collect_provisional_earnings(
    client: OpenDartReadOnlyClient,
    spec: ProvisionalEarningsSpec,
    *,
    evaluation_date: date,
) -> tuple[OpenDartProvisionalEarningsEvidence, DisclosureDocumentEvidence]:
    if spec.receipt_date > evaluation_date:
        raise ValueError("Provisional earnings disclosure is not yet observable")
    discovery = discover_provisional_disclosure(client, spec)
    document = OpenDartDisclosureDocumentClient(client).document(discovery.rcept_no)
    evidence = build_provisional_earnings_evidence(
        discovery,
        document,
        evaluation_date=evaluation_date,
    )
    return evidence, document


__all__ = [
    "DEFAULT_PROVISIONAL_EARNINGS_REGISTRY",
    "DiscoveredProvisionalDisclosure",
    "OpenDartProvisionalEarningsEvidence",
    "ProvisionalEarningsMetrics",
    "ProvisionalEarningsSpec",
    "build_provisional_earnings_evidence",
    "collect_provisional_earnings",
    "discover_provisional_disclosure",
    "load_provisional_earnings_registry",
    "parse_provisional_earnings_text",
]
