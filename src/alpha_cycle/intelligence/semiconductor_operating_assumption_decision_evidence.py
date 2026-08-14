"""Verify semiconductor operating-assumption artifacts at the decision boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.semiconductor_forward_input_decision_evidence import (
    load_semiconductor_forward_input_decision_evidence,
)
from alpha_cycle.intelligence.semiconductor_forward_operating_model_contract import (
    SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS,
)
from alpha_cycle.intelligence.semiconductor_model_input_semantics import (
    baseline_requirement_semantics,
)
from alpha_cycle.intelligence.semiconductor_operating_assumptions import (
    OperatingAssumptionPack,
    build_operating_assumption_pack,
)

DEFAULT_OPERATING_ASSUMPTION_POINTER = Path(
    "data/private/live-research/semiconductor-operating-assumptions/"
    "latest_semiconductor_operating_assumptions.json"
)
_REQUIRED_FALSE_FLAGS = (
    "source_fact",
    "scenario_probabilities_enabled",
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
class SemiconductorOperatingAssumptionDecisionEvidence:
    pack: OperatingAssumptionPack
    issuer_summary: pd.DataFrame
    forward_input_evidence_id: str
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if self.issuer_summary.empty:
            raise ValueError("Operating assumption decision summary cannot be empty")
        if len(self.forward_input_evidence_id) != 64:
            raise ValueError("Operating assumption forward-input evidence ID is invalid")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError(
                "Operating assumption decision evidence must remain non-forecast/non-scoring"
            )


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _json_rows(path: Path, label: str) -> list[dict[str, object]]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"{label} must be a non-empty JSON array")
    rows: list[dict[str, object]] = []
    for value in payload:
        if not isinstance(value, dict):
            raise ValueError(f"{label} rows must be objects")
        rows.append({str(key): item for key, item in cast(dict[object, object], value).items()})
    return rows


def _require_false(payload: Mapping[str, object]) -> None:
    for key in _REQUIRED_FALSE_FLAGS:
        if payload.get(key) is not False:
            raise ValueError(f"Operating assumption artifact requires {key}=false")


def _verified_forward_claim_ids(
    forward_pointer: Path,
    *,
    evaluation_date: date,
) -> tuple[str, set[str]]:
    evidence = load_semiconductor_forward_input_decision_evidence(
        forward_pointer,
        evaluation_date=evaluation_date,
    )
    pointer = _json_object(forward_pointer, "Forward-input pointer")
    claims = _json_rows(
        Path(str(pointer.get("claims_path", "")).strip()),
        "Forward-input claims",
    )
    ids = {str(item.get("claim_id", "")).strip() for item in claims}
    if not ids or any(
        len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
        for value in ids
    ):
        raise ValueError("Forward-input claim IDs are invalid")
    return evidence.evidence_id, ids


def _persisted_coverage(path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, dtype={"ticker": "string", "scenario": "string"})
    except FileNotFoundError as exc:
        raise ValueError(f"Operating assumption coverage not found: {path}") from exc
    if frame.empty or not {"ticker", "scenario"}.issubset(frame.columns):
        raise ValueError("Operating assumption coverage is empty or malformed")
    frame["ticker"] = frame["ticker"].astype("string").str.zfill(6)
    return frame


def _issuer_summary(pack: OperatingAssumptionPack) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ticker_key, group in pack.scenario_coverage.groupby("ticker", sort=True):
        ticker = str(ticker_key)
        by_scenario = {str(row["scenario"]): row for row in group.to_dict(orient="records")}
        baseline_bridge_count = 0
        direct_baseline_count = 0
        contract = SEMICONDUCTOR_FORWARD_MODEL_CONTRACTS[ticker]
        for block in contract.blocks:
            for metric in block.required_baseline_metrics:
                semantics = baseline_requirement_semantics(ticker, block.block_id, metric)
                baseline_bridge_count += int(semantics.reconciliation_required)
                direct_baseline_count += int(semantics.direct_numeric_source_fact_sufficient)
        rows.append(
            {
                "ticker": ticker,
                "horizon_quarters": pack.horizon_quarters,
                "bear_assumption_coverage_complete": bool(
                    by_scenario["bear"]["assumption_coverage_complete"]
                ),
                "base_assumption_coverage_complete": bool(
                    by_scenario["base"]["assumption_coverage_complete"]
                ),
                "bull_assumption_coverage_complete": bool(
                    by_scenario["bull"]["assumption_coverage_complete"]
                ),
                "bear_model_use_assumptions_complete": bool(
                    by_scenario["bear"]["model_use_assumptions_complete"]
                ),
                "base_model_use_assumptions_complete": bool(
                    by_scenario["base"]["model_use_assumptions_complete"]
                ),
                "bull_model_use_assumptions_complete": bool(
                    by_scenario["bull"]["model_use_assumptions_complete"]
                ),
                "all_scenario_assumptions_documented": all(
                    bool(by_scenario[item]["assumption_coverage_complete"])
                    for item in ("bear", "base", "bull")
                ),
                "all_scenario_assumptions_model_use_ready": all(
                    bool(by_scenario[item]["model_use_assumptions_complete"])
                    for item in ("bear", "base", "bull")
                ),
                "baseline_reconciliation_required_count": baseline_bridge_count,
                "direct_numeric_baseline_requirement_count": direct_baseline_count,
                "baseline_reconciliation_certified": False,
                "output_method_certified": False,
                "company_reconciliation_certified": False,
                "model_version_frozen": False,
                "internal_forward_model_certified": False,
                "scenario_probabilities_enabled": False,
                "numeric_forecast_enabled": False,
                "decision_score_enabled": False,
            }
        )
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def load_semiconductor_operating_assumption_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> SemiconductorOperatingAssumptionDecisionEvidence:
    pointer = _json_object(Path(pointer_path), "Operating assumption pointer")
    if str(pointer.get("status", "")) != "semiconductor_operating_assumption_pack_captured":
        raise ValueError("Operating assumption pointer status is invalid")
    _require_false(pointer)
    pointer_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if pointer_date != evaluation_date:
        raise ValueError(
            "Operating assumption evaluation date mismatch: "
            f"evidence={pointer_date.isoformat()} decision={evaluation_date.isoformat()}"
        )
    pack_id = str(pointer.get("pack_id", "")).strip()
    if len(pack_id) != 64:
        raise ValueError("Operating assumption pack_id is invalid")
    horizon_quarters = int(str(pointer.get("horizon_quarters", 0)))
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", "")).strip()),
        "Operating assumption manifest",
    )
    if str(manifest.get("pack_id", "")) != pack_id:
        raise ValueError("Operating assumption pointer/manifest mismatch")
    _require_false(manifest)
    if int(str(manifest.get("horizon_quarters", 0))) != horizon_quarters:
        raise ValueError("Operating assumption horizon metadata mismatch")

    forward_pointer = Path(str(pointer.get("forward_input_pointer", "")).strip())
    forward_evidence_id, verified_ids = _verified_forward_claim_ids(
        forward_pointer,
        evaluation_date=evaluation_date,
    )
    if str(pointer.get("forward_input_evidence_id", "")) != forward_evidence_id:
        raise ValueError("Operating assumption forward-input evidence mismatch")
    if str(manifest.get("forward_input_evidence_id", "")) != forward_evidence_id:
        raise ValueError("Operating assumption manifest forward-input evidence mismatch")

    raw_assumptions = _json_rows(
        Path(str(pointer.get("assumptions_path", "")).strip()),
        "Operating assumptions",
    )
    rebuilt = build_operating_assumption_pack(
        raw_assumptions,
        evaluation_date=evaluation_date,
        horizon_quarters=horizon_quarters,
        verified_evidence_ids=verified_ids,
    )
    if rebuilt.pack_id != pack_id:
        raise ValueError("Operating assumptions do not reproduce pack_id")
    persisted = _persisted_coverage(
        Path(str(pointer.get("scenario_coverage_path", "")).strip())
    )
    try:
        pd.testing.assert_frame_equal(
            rebuilt.scenario_coverage.reset_index(drop=True),
            persisted.reset_index(drop=True),
            check_dtype=False,
        )
    except AssertionError as exc:
        raise ValueError("Operating assumption coverage does not reproduce") from exc
    return SemiconductorOperatingAssumptionDecisionEvidence(
        pack=rebuilt,
        issuer_summary=_issuer_summary(rebuilt),
        forward_input_evidence_id=forward_evidence_id,
    )


def append_semiconductor_operating_assumption_report(
    report: str,
    evidence: SemiconductorOperatingAssumptionDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## Semiconductor Operating Assumptions (내부 가정·비점수)",
        "",
        f"- pack: `{evidence.pack.pack_id[:12]}` / horizon: {evidence.pack.horizon_quarters}Q",
        (
            "- Bull/Base/Bear 숫자는 source fact가 아니라 명시적 내부 모델 가정입니다. "
            "각 가정은 supporting evidence와 방법 버전을 보존합니다."
        ),
        (
            "- 확률은 생성하지 않습니다. driver assumptions가 모두 채워져도 baseline bridge, "
            "output method, company reconciliation, model freeze 전에는 numeric forecast가 아닙니다."
        ),
        "",
        "| 종목 | Bear | Base | Bull | model-use all | baseline bridges | forecast |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in evidence.issuer_summary.to_dict(orient="records"):
        lines.append(
            f"| {row['ticker']} | {row['bear_assumption_coverage_complete']} | "
            f"{row['base_assumption_coverage_complete']} | "
            f"{row['bull_assumption_coverage_complete']} | "
            f"{row['all_scenario_assumptions_model_use_ready']} | "
            f"{row['baseline_reconciliation_required_count']} | false |"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_OPERATING_ASSUMPTION_POINTER",
    "SemiconductorOperatingAssumptionDecisionEvidence",
    "append_semiconductor_operating_assumption_report",
    "load_semiconductor_operating_assumption_decision_evidence",
]
