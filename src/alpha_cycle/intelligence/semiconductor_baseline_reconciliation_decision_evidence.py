"""Verify archived semiconductor baseline reconciliation evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.semiconductor_baseline_reconciliation import (
    SemiconductorBaselineReconciliationEvidence,
    build_semiconductor_baseline_reconciliation,
)
from alpha_cycle.intelligence.semiconductor_structural_evidence import (
    load_structural_source_registry,
)

DEFAULT_BASELINE_RECONCILIATION_POINTER = Path(
    "data/private/live-research/semiconductor-baseline-reconciliation/"
    "latest_semiconductor_baseline_reconciliation.json"
)
_REQUIRED_FALSE_FLAGS = (
    "residual_derivation_enabled",
    "internal_estimate_enabled",
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
class SemiconductorBaselineReconciliationDecisionEvidence:
    evidence: SemiconductorBaselineReconciliationEvidence
    residual_derivation_enabled: bool = False
    internal_estimate_enabled: bool = False
    numeric_forecast_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if self.residual_derivation_enabled or self.internal_estimate_enabled:
            raise ValueError("Baseline reconciliation decision evidence prohibits derivation")
        if self.numeric_forecast_enabled or self.decision_score_enabled:
            raise ValueError("Baseline reconciliation decision evidence is non-forecast/non-scoring")


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise ValueError(f"Archived baseline source not found: {path}") from exc
    return digest.hexdigest()


def _require_false(payload: Mapping[str, object]) -> None:
    for key in _REQUIRED_FALSE_FLAGS:
        if payload.get(key) is not False:
            raise ValueError(f"Baseline reconciliation requires {key}=false")


def _frame(path: Path, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, dtype={"ticker": "string"})
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    if frame.empty or "ticker" not in frame.columns:
        raise ValueError(f"{label} is empty or malformed")
    frame["ticker"] = frame["ticker"].astype("string").str.zfill(6)
    return frame


def _assert_frame(actual: pd.DataFrame, expected: pd.DataFrame, label: str) -> None:
    try:
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
        )
    except AssertionError as exc:
        raise ValueError(f"Baseline reconciliation {label} does not reproduce") from exc


def load_semiconductor_baseline_reconciliation_decision_evidence(
    pointer_path: str | Path,
    *,
    evaluation_date: date,
) -> SemiconductorBaselineReconciliationDecisionEvidence:
    pointer = _json_object(Path(pointer_path), "Baseline reconciliation pointer")
    if str(pointer.get("status", "")) != "semiconductor_baseline_reconciliation_captured":
        raise ValueError("Baseline reconciliation pointer status is invalid")
    _require_false(pointer)
    pointer_date = date.fromisoformat(str(pointer.get("evaluation_date", "")))
    if pointer_date != evaluation_date:
        raise ValueError(
            "Baseline reconciliation evaluation date mismatch: "
            f"evidence={pointer_date.isoformat()} decision={evaluation_date.isoformat()}"
        )
    evidence_id = str(pointer.get("evidence_id", "")).strip()
    if len(evidence_id) != 64:
        raise ValueError("Baseline reconciliation evidence_id is invalid")
    manifest = _json_object(
        Path(str(pointer.get("manifest_path", "")).strip()),
        "Baseline reconciliation manifest",
    )
    if str(manifest.get("evidence_id", "")) != evidence_id:
        raise ValueError("Baseline reconciliation pointer/manifest evidence mismatch")
    _require_false(manifest)

    registry_path = Path(str(pointer.get("source_registry_path", "")).strip())
    registry_hash = str(pointer.get("source_registry_sha256", "")).strip()
    if len(registry_hash) != 64 or str(manifest.get("source_registry_sha256", "")) != registry_hash:
        raise ValueError("Baseline reconciliation source registry metadata is invalid")
    if _sha256_file(registry_path) != registry_hash:
        raise ValueError("Baseline reconciliation source registry hash mismatch")
    registry = load_structural_source_registry(registry_path)

    facts = _json_rows(
        Path(str(pointer.get("facts_path", "")).strip()),
        "Baseline reconciliation facts",
    )
    raw_facts: list[dict[str, object]] = []
    document_hashes: set[str] = set()
    for fact in facts:
        archived_path = Path(str(fact.get("archived_document_path", "")).strip())
        expected_hash = str(fact.get("source_document_sha256", "")).strip()
        if _sha256_file(archived_path) != expected_hash:
            raise ValueError("Baseline reconciliation archived document hash mismatch")
        document_hashes.add(expected_hash)
        raw_facts.append(
            {
                key: value
                for key, value in fact.items()
                if key not in {"fact_id", "archived_document_path"}
            }
        )
    manifest_hashes = manifest.get("document_sha256s", [])
    if not isinstance(manifest_hashes, list) or set(map(str, manifest_hashes)) != document_hashes:
        raise ValueError("Baseline reconciliation document hash inventory mismatch")

    rebuilt = build_semiconductor_baseline_reconciliation(
        raw_facts,
        registry,
        evaluation_date=evaluation_date,
    )
    if rebuilt.evidence_id != evidence_id:
        raise ValueError("Baseline reconciliation facts do not reproduce evidence_id")
    persisted_bridges = _frame(
        Path(str(pointer.get("bridge_coverage_path", "")).strip()),
        "Baseline bridge coverage",
    )
    persisted_summary = _frame(
        Path(str(pointer.get("issuer_summary_path", "")).strip()),
        "Baseline issuer summary",
    )
    _assert_frame(rebuilt.bridge_coverage, persisted_bridges, "bridge coverage")
    _assert_frame(rebuilt.issuer_summary, persisted_summary, "issuer summary")
    return SemiconductorBaselineReconciliationDecisionEvidence(evidence=rebuilt)


def append_semiconductor_baseline_reconciliation_report(
    report: str,
    evidence: SemiconductorBaselineReconciliationDecisionEvidence,
) -> str:
    lines = [
        report.rstrip(),
        "",
        "## Semiconductor Baseline Reconciliation (직접 회계근거·비점수)",
        "",
        f"- evidence: `{evidence.evidence.evidence_id[:12]}`",
        (
            "- 같은 issuer·block scope·회계기간의 archived official facts가 required outputs를 "
            "모두 직접 충족할 때만 baseline bridge를 certified로 표시합니다."
        ),
        (
            "- residual subtraction, peer substitution, internal estimate는 v1에서 금지됩니다. "
            "미공개 수익성 항목은 추정하지 않고 research gap으로 유지합니다."
        ),
        "",
        "| 종목 | required bridges | certified | all certified | residual | forecast |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in evidence.evidence.issuer_summary.to_dict(orient="records"):
        lines.append(
            f"| {row['ticker']} | {row['baseline_reconciliation_required_count']} | "
            f"{row['baseline_reconciliation_certified_count']} | "
            f"{row['baseline_reconciliation_certified']} | false | false |"
        )
    lines.extend(["", "### Bridge status", ""])
    for row in evidence.evidence.bridge_coverage.to_dict(orient="records"):
        lines.append(
            f"- `{row['ticker']}` `{row['block_id']}`: {row['baseline_bridge_status']} / "
            f"{row['certified_output_count']}/{row['required_output_count']} outputs"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_BASELINE_RECONCILIATION_POINTER",
    "SemiconductorBaselineReconciliationDecisionEvidence",
    "append_semiconductor_baseline_reconciliation_report",
    "load_semiconductor_baseline_reconciliation_decision_evidence",
]
