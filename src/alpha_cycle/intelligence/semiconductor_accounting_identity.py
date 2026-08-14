"""Source-bounded issuer accounting identities for company-level model reconciliation.

Accounting identities are not residual estimates. They are deterministic reconciliations
between totals and complete disclosed component sets from the same official document and
period. They may certify only the explicitly registered company-level bridge and must never
be reused to infer an undisclosed business-unit profit such as Samsung Memory operating
income or Foundry/System LSI profitability.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.official_semiconductor_ir_collector import extract_pdf_pages

_SAMSUNG_DOCUMENT_ID = "samsung_005930_2026q2_earnings"
_REQUIRED_FALSE_FLAGS = (
    "numeric_forecast_enabled",
    "decision_score_enabled",
    "fair_value_estimate_enabled",
    "target_price_enabled",
    "account_api_enabled",
    "holdings_api_enabled",
    "balance_api_enabled",
    "order_api_enabled",
)
_SEGMENTS = ("ds", "dx", "sdc", "harman")
_ROUNDING_TOLERANCE = 0.11


@dataclass(frozen=True)
class SamsungAccountingIdentityEvidence:
    evidence_id: str
    evaluation_date: date
    period_start: date
    period_end: date
    source_document_sha256: str
    consolidated_revenue: float
    segment_revenue_sum: float
    consolidation_revenue_adjustment: float
    consolidated_operating_income: float
    segment_operating_income_sum: float
    consolidation_operating_income_adjustment: float
    profit_before_tax: float
    income_tax: float
    net_income: float
    non_operating_to_pbt_bridge: float
    corporate_consolidation_bridge_certified: bool
    net_income_bridge_certified: bool
    corporate_baseline_bridge_certified: bool
    accounting_identity_derivation_enabled: bool = True
    residual_estimate_enabled: bool = False
    segment_profit_inference_enabled: bool = False
    memory_operating_income_derived: bool = False
    foundry_operating_income_derived: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or len(self.source_document_sha256) != 64:
            raise ValueError("Accounting identity hashes must be SHA-256")
        if self.period_start > self.period_end or self.period_end > self.evaluation_date:
            raise ValueError("Accounting identity period/evaluation dates are invalid")
        if not self.accounting_identity_derivation_enabled:
            raise ValueError("Accounting identity evidence must identify its derivation method")
        if (
            self.residual_estimate_enabled
            or self.segment_profit_inference_enabled
            or self.memory_operating_income_derived
            or self.foundry_operating_income_derived
            or self.numeric_forecast_enabled
            or self.decision_score_enabled
        ):
            raise ValueError("Accounting identity evidence cannot enable estimation or scoring")
        if self.corporate_baseline_bridge_certified != (
            self.corporate_consolidation_bridge_certified and self.net_income_bridge_certified
        ):
            raise ValueError("Corporate baseline bridge certification is internally inconsistent")


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
            raise ValueError(f"Official IR pointer requires {key}=false")


def _normalized(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def _require(text: str, anchor: str, label: str) -> None:
    if anchor.casefold() not in text.casefold():
        raise ValueError(f"Samsung accounting identity anchor is missing: {label}")


def _number(text: str, pattern: str, label: str) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"Samsung accounting identity number is missing: {label}")
    token = match.group(1).strip()
    negative = token.startswith("(") and token.endswith(")")
    value = float(token.strip("()"))
    return -value if negative else value


def _evidence_id(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_samsung_accounting_identity_from_official_ir(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> SamsungAccountingIdentityEvidence:
    pointer = _json_object(Path(pointer_path), "Official IR pointer")
    if pointer.get("status") != "official_semiconductor_ir_document_captured":
        raise ValueError("Official IR pointer status is invalid")
    _require_false(pointer)
    if str(pointer.get("document_id", "")) != _SAMSUNG_DOCUMENT_ID:
        raise ValueError("Accounting identity v1 requires the registered Samsung 2Q26 document")
    if str(pointer.get("ticker", "")).zfill(6) != "005930":
        raise ValueError("Accounting identity v1 received the wrong issuer")
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Accounting identity official-IR evaluation date mismatch")
    if pointer.get("source_bytes_archived") is not True:
        raise ValueError("Accounting identity requires archived official source bytes")

    manifest_path = Path(str(pointer.get("manifest_path", "")))
    manifest = _json_object(manifest_path, "Official IR manifest")
    _require_false(manifest)
    if manifest.get("parser_semantics_certified") is not True:
        raise ValueError("Accounting identity requires certified official parser semantics")
    if str(manifest.get("document_id", "")) != _SAMSUNG_DOCUMENT_ID:
        raise ValueError("Accounting identity pointer/manifest document mismatch")
    period_start = date.fromisoformat(str(manifest.get("period_start", "")))
    period_end = date.fromisoformat(str(manifest.get("period_end", "")))

    source_path = Path(str(pointer.get("source_document_path", "")))
    try:
        source_bytes = source_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"Accounting identity source bytes not found: {source_path}") from exc
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    expected_hash = str(pointer.get("source_document_sha256", ""))
    manifest_hash = str(manifest.get("source_document_sha256", ""))
    if source_hash != expected_hash or source_hash != manifest_hash:
        raise ValueError("Accounting identity source document hash mismatch")

    pages = extract_pdf_pages(source_bytes)
    if len(pages) != 16:
        raise ValueError("Samsung accounting identity source page count changed")
    result_page = _normalized(pages[4])
    segment_page = _normalized(pages[5])
    financial_page = _normalized(pages[11])
    appendix = _normalized(pages[12])
    _require(result_page, "Based on consolidated financial statements", "consolidated basis")
    _require(
        segment_page,
        "sales of business units include intersegment sales",
        "intersegment footnote",
    )
    _require(appendix, "Appendix 2: Results by Business Segment", "segment appendix")
    _require(financial_page, "Appendix 1: 2Q 2026 Results & Financial Data", "financial appendix")

    consolidated_revenue = _number(
        appendix,
        r"\bTotal\s+74\.6\s+133\.9\s+(171\.5)\b",
        "consolidated revenue",
    )
    consolidated_op = _number(
        appendix,
        r"\bTotal\s+4\.7\s+57\.2\s+(89\.5)\b",
        "consolidated operating income",
    )
    segment_revenue = {
        "ds": _number(appendix, r"\bDS\s+27\.9\s+81\.7\s+(127\.5)\b", "DS revenue"),
        "dx": _number(appendix, r"\bDX\s+43\.6\s+52\.7\s+(48\.0)\b", "DX revenue"),
        "sdc": _number(appendix, r"\bSDC\s+6\.4\s+6\.7\s+(7\.5)\b", "SDC revenue"),
        "harman": _number(
            appendix,
            r"\bHarman\s+3\.8\s+3\.8\s+(4\.6)\b",
            "Harman revenue",
        ),
    }
    segment_op = {
        "ds": _number(appendix, r"\bDS\s+0\.4\s+53\.7\s+(89\.2)\b", "DS OP"),
        "dx": _number(appendix, r"\bDX\s+3\.3\s+3\.0\s+(\(0\.8\))", "DX OP"),
        "sdc": _number(appendix, r"\bSDC\s+0\.5\s+0\.4\s+(0\.7)\b", "SDC OP"),
        "harman": _number(appendix, r"\bHarman\s+0\.5\s+0\.2\s+(0\.4)\b", "Harman OP"),
    }
    if set(segment_revenue) != set(_SEGMENTS) or set(segment_op) != set(_SEGMENTS):
        raise ValueError("Samsung accounting identity segment set is incomplete")
    segment_revenue_sum = sum(segment_revenue.values())
    segment_op_sum = sum(segment_op.values())
    revenue_adjustment = consolidated_revenue - segment_revenue_sum
    op_adjustment = consolidated_op - segment_op_sum

    pbt = _number(
        financial_page,
        r"Profit before income tax\s+5\.8\s+7\.7%\s+58\.8\s+43\.9%\s+(94\.4)",
        "profit before tax",
    )
    income_tax = _number(
        financial_page,
        r"Income tax\s+0\.6\s+-\s+11\.6\s+-\s+(22\.8)",
        "income tax",
    )
    net_income = _number(
        financial_page,
        r"Net profit\s+5\.1\s+6\.9%\s+47\.2\s+35\.3%\s+(71\.6)",
        "net income",
    )
    non_operating_bridge = pbt - consolidated_op
    op_identity_ok = abs(op_adjustment) <= _ROUNDING_TOLERANCE
    net_identity_ok = abs((pbt - income_tax) - net_income) <= _ROUNDING_TOLERANCE
    consolidation_certified = op_identity_ok and revenue_adjustment < 0
    net_bridge_certified = net_identity_ok

    payload: dict[str, object] = {
        "evaluation_date": evaluation_date.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "source_document_sha256": source_hash,
        "consolidated_revenue": consolidated_revenue,
        "segment_revenue_sum": segment_revenue_sum,
        "consolidation_revenue_adjustment": revenue_adjustment,
        "consolidated_operating_income": consolidated_op,
        "segment_operating_income_sum": segment_op_sum,
        "consolidation_operating_income_adjustment": op_adjustment,
        "profit_before_tax": pbt,
        "income_tax": income_tax,
        "net_income": net_income,
        "non_operating_to_pbt_bridge": non_operating_bridge,
        "corporate_consolidation_bridge_certified": consolidation_certified,
        "net_income_bridge_certified": net_bridge_certified,
        "corporate_baseline_bridge_certified": (
            consolidation_certified and net_bridge_certified
        ),
        "accounting_identity_derivation_enabled": True,
        "residual_estimate_enabled": False,
        "segment_profit_inference_enabled": False,
        "memory_operating_income_derived": False,
        "foundry_operating_income_derived": False,
        "numeric_forecast_enabled": False,
        "decision_score_enabled": False,
    }
    return SamsungAccountingIdentityEvidence(
        evidence_id=_evidence_id(payload),
        evaluation_date=evaluation_date,
        period_start=period_start,
        period_end=period_end,
        source_document_sha256=source_hash,
        consolidated_revenue=consolidated_revenue,
        segment_revenue_sum=segment_revenue_sum,
        consolidation_revenue_adjustment=revenue_adjustment,
        consolidated_operating_income=consolidated_op,
        segment_operating_income_sum=segment_op_sum,
        consolidation_operating_income_adjustment=op_adjustment,
        profit_before_tax=pbt,
        income_tax=income_tax,
        net_income=net_income,
        non_operating_to_pbt_bridge=non_operating_bridge,
        corporate_consolidation_bridge_certified=consolidation_certified,
        net_income_bridge_certified=net_bridge_certified,
        corporate_baseline_bridge_certified=(consolidation_certified and net_bridge_certified),
    )


__all__ = [
    "SamsungAccountingIdentityEvidence",
    "build_samsung_accounting_identity_from_official_ir",
]
