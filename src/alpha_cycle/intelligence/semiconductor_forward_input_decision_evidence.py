"""Load semiconductor forward-input artifacts and expose block coverage to decisions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

DEFAULT_FORWARD_INPUT_POINTER = Path(
    "data/private/live-research/semiconductor-forward-input-evidence/"
    "latest_semiconductor_forward_input_evidence.json"
)
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


@dataclass(frozen=True)
class SemiconductorForwardInputDecisionEvidence:
    evidence_id: str
    evaluation_date: date
    block_coverage: pd.DataFrame
    issuer_coverage: pd.DataFrame
    decision_score_enabled: bool = False
    numeric_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64:
            raise ValueError("Forward-input decision evidence_id must be SHA-256")
        if self.block_coverage.empty or self.issuer_coverage.empty:
            raise ValueError("Forward-input decision evidence requires coverage")
        if self.decision_score_enabled or self.numeric_forecast_enabled:
            raise ValueError("Forward-input decision evidence must remain non-scoring/non-forecast")


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


def _require_false(payload: Mapping[str, object]) -> None:
    for key in _REQUIRED_FALSE_FLAGS:
        if payload.get(key) is not False:
            raise ValueError(f"Forward-input evidence requires {key}=false")


def _load_frame(path: Path, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, dtype={"ticker": "string"})
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    if frame.empty or "ticker" not in frame.columns:
        raise ValueError(f"{label} is empty or missing ticker")
    frame["ticker"] = frame["ticker"].astype("string").str.zfill(6)
    return frame


def load_semiconductor_forward_input_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> SemiconductorForwardInputDecisionEvidence:
    pointer = _json_object(Path(pointer_path), "Forward-input pointer")
    if str(pointer.get("status", "")) != "semiconductor_forward_input_evidence_captured":
        raise ValueError("Forward-input pointer status is invalid")
    _require_false(pointer)
    pointer_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if pointer_date != evaluation_date:
        raise ValueError(
            "Forward-input evaluation date mismatch: "
            f"evidence={pointer_date.isoformat()} decision={evaluation_date.isoformat()}"
        )
    evidence_id = str(pointer.get("evidence_id", "")).strip()
    if len(evidence_id) != 64:
        raise ValueError("Forward-input pointer evidence_id is invalid")
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", ""))),
        "Forward-input manifest",
    )
    if str(manifest.get("evidence_id", "")) != evidence_id:
        raise ValueError("Forward-input pointer/manifest evidence mismatch")
    _require_false(manifest)
    block_coverage = _load_frame(
        Path(str(pointer.get("block_coverage_path", ""))),
        "Forward-input block coverage",
    )
    issuer_coverage = _load_frame(
        Path(str(pointer.get("issuer_coverage_path", ""))),
        "Forward-input issuer coverage",
    )
    if issuer_coverage["ticker"].duplicated().any():
        raise ValueError("Forward-input issuer coverage contains duplicate tickers")
    return SemiconductorForwardInputDecisionEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        block_coverage=block_coverage,
        issuer_coverage=issuer_coverage,
    )


def append_semiconductor_forward_input_report(
    report: str,
    evidence: SemiconductorForwardInputDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## Semiconductor Forward Inputs (source-bounded·비점수)",
        "",
        f"- evidence: `{evidence.evidence_id[:12]}` / evaluation `{evidence.evaluation_date.isoformat()}`",
        (
            "- 정성 근거 coverage와 numeric model-input coverage를 분리합니다. "
            "정성 근거만으로 4–8분기 숫자 forecast를 생성하지 않습니다."
        ),
        (
            "- issuer block 전체의 baseline·numeric driver coverage 외에도 output method, "
            "company reconciliation, frozen model version이 별도로 인증되어야 internal "
            "forward model이 활성화됩니다."
        ),
        "",
        "| 종목 | blocks | descriptive-ready | numeric-input-ready | 전체 descriptive | 전체 numeric | forecast |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for raw in evidence.issuer_coverage.to_dict(orient="records"):
        lines.append(
            f"| {raw['ticker']} | {raw['required_block_count']} | "
            f"{raw['descriptive_ready_block_count']} | {raw['numeric_input_ready_block_count']} | "
            f"{raw['all_descriptive_inputs_covered']} | {raw['all_numeric_inputs_covered']} | false |"
        )
    lines.extend(["", "### Block coverage", ""])
    for raw in evidence.block_coverage.to_dict(orient="records"):
        lines.append(
            f"- `{raw['ticker']}` `{raw['block_id']}`: baseline "
            f"{raw['covered_baseline_count']}/{raw['required_baseline_count']}, drivers "
            f"{raw['covered_forward_driver_count']}/{raw['required_forward_driver_count']}, "
            f"numeric drivers {raw['numeric_forward_driver_count']}/"
            f"{raw['required_forward_driver_count']}"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_FORWARD_INPUT_POINTER",
    "SemiconductorForwardInputDecisionEvidence",
    "append_semiconductor_forward_input_report",
    "load_semiconductor_forward_input_decision_evidence",
]
