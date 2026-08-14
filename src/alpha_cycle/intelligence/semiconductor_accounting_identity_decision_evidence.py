"""Decision-facing verified company accounting-identity evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.semiconductor_accounting_identity import (
    SamsungAccountingIdentityEvidence,
    build_samsung_accounting_identity_from_official_ir,
)

DEFAULT_ACCOUNTING_IDENTITY_POINTER = Path(
    "data/private/live-research/semiconductor-accounting-identity/"
    "latest_semiconductor_accounting_identity.json"
)
_REQUIRED_FALSE_FLAGS = (
    "residual_estimate_enabled",
    "segment_profit_inference_enabled",
    "memory_operating_income_derived",
    "foundry_operating_income_derived",
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
class AccountingIdentityDecisionEvidence:
    evidence: SamsungAccountingIdentityEvidence
    decision_score_enabled: bool = False
    numeric_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        if self.decision_score_enabled or self.numeric_forecast_enabled:
            raise ValueError("Accounting identity decision evidence must remain non-scoring")


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
            raise ValueError(f"Accounting identity evidence requires {key}=false")


def load_semiconductor_accounting_identity_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> AccountingIdentityDecisionEvidence:
    pointer = _json_object(Path(pointer_path), "Accounting identity pointer")
    if pointer.get("status") != "semiconductor_accounting_identity_captured":
        raise ValueError("Accounting identity pointer status is invalid")
    _require_false(pointer)
    if pointer.get("accounting_identity_derivation_enabled") is not True:
        raise ValueError("Accounting identity derivation flag must be true")
    if pointer.get("corporate_baseline_bridge_certified") is not True:
        raise ValueError("Accounting identity corporate bridge is not certified")
    if date.fromisoformat(str(pointer.get("evaluation_date", ""))) != evaluation_date:
        raise ValueError("Accounting identity evaluation date mismatch")
    if str(pointer.get("ticker", "")).zfill(6) != "005930":
        raise ValueError("Accounting identity v1 supports Samsung Electronics only")

    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "Accounting identity manifest",
    )
    _require_false(manifest)
    if manifest.get("accounting_identity_derivation_enabled") is not True:
        raise ValueError("Accounting identity manifest derivation flag must be true")
    evidence_id = str(pointer.get("evidence_id", ""))
    if evidence_id != str(manifest.get("evidence_id", "")) or len(evidence_id) != 64:
        raise ValueError("Accounting identity pointer/manifest evidence mismatch")

    official_pointer_path = Path(str(manifest.get("official_ir_pointer_path", "")))
    reconstructed = build_samsung_accounting_identity_from_official_ir(
        official_pointer_path,
        evaluation_date=evaluation_date,
    )
    if reconstructed.evidence_id != evidence_id:
        raise ValueError("Accounting identity evidence does not reproduce from official source")
    payload = _json_object(
        Path(str(pointer.get("accounting_identity_path", ""))),
        "Accounting identity payload",
    )
    if str(payload.get("evidence_id", "")) != reconstructed.evidence_id:
        raise ValueError("Accounting identity payload evidence mismatch")
    if payload.get("corporate_baseline_bridge_certified") is not True:
        raise ValueError("Accounting identity payload corporate bridge is not certified")
    _require_false(payload)
    return AccountingIdentityDecisionEvidence(evidence=reconstructed)


def append_semiconductor_accounting_identity_report(
    report: str,
    evidence: AccountingIdentityDecisionEvidence,
) -> str:
    item = evidence.evidence
    lines = [
        report.rstrip(),
        "",
        "## Semiconductor Accounting Identity (회사 연결·비점수)",
        "",
        f"- evidence: `{item.evidence_id[:12]}` / evaluation `{item.evaluation_date.isoformat()}`",
        (
            "- 같은 Samsung 공식 문서·같은 회계기간의 consolidated total과 완전한 "
            "reportable-segment set을 사용한 accounting identity입니다."
        ),
        (
            "- segment revenue 합계에는 intersegment sales가 포함되므로 consolidated "
            "revenue와의 차이는 회사-level consolidation adjustment로만 보존합니다."
        ),
        (
            "- 이 identity는 Memory OP, Foundry/System LSI profit 등 미공시 segment "
            "수치를 역산하는 데 사용할 수 없습니다."
        ),
        "",
        "| 항목 | 값 (KRW tn) |",
        "|---|---:|",
        f"| consolidated revenue | {item.consolidated_revenue:.1f} |",
        f"| disclosed segment revenue sum | {item.segment_revenue_sum:.1f} |",
        f"| consolidation revenue adjustment | {item.consolidation_revenue_adjustment:.1f} |",
        f"| consolidated operating income | {item.consolidated_operating_income:.1f} |",
        f"| disclosed segment OP sum | {item.segment_operating_income_sum:.1f} |",
        (
            "| consolidation OP adjustment | "
            f"{item.consolidation_operating_income_adjustment:.1f} |"
        ),
        f"| profit before tax | {item.profit_before_tax:.1f} |",
        f"| income tax | {item.income_tax:.1f} |",
        f"| net income | {item.net_income:.1f} |",
        "",
        (
            "- corporate consolidation bridge certified: "
            f"`{item.corporate_consolidation_bridge_certified}`"
        ),
        f"- net-income bridge certified: `{item.net_income_bridge_certified}`",
        "- residual estimate: `false`; segment-profit inference: `false`; decision score: `false`",
    ]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "AccountingIdentityDecisionEvidence",
    "DEFAULT_ACCOUNTING_IDENTITY_POINTER",
    "append_semiconductor_accounting_identity_report",
    "load_semiconductor_accounting_identity_decision_evidence",
]
