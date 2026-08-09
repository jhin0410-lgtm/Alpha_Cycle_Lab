"""Attach optional KOSIS semiconductor industry evidence to calibrated decisions.

The underlying calibrated decision builder remains authoritative for all scores. This
wrapper only adds provenance-bound, non-scoring semiconductor industry evidence when a
local KOSIS history pointer exists or is supplied explicitly.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_evidence_calibrated import (
    build_investment_decision_snapshot as _build_calibrated_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.semiconductor_cycle_proxy import build_semiconductor_cycle_proxy
from alpha_cycle.intelligence.semiconductor_industry_evidence import (
    append_semiconductor_industry_evidence_report,
    attach_semiconductor_industry_to_records,
    attach_semiconductor_industry_to_scorecards,
    build_semiconductor_cycle_bridge,
    load_semiconductor_industry_evidence,
)

KOREA_TZ = ZoneInfo("Asia/Seoul")
DEFAULT_SEMICONDUCTOR_HISTORY_POINTER = Path(
    "data/private/live-research/kosis-semiconductor-history/"
    "latest_kosis_semiconductor_history.json"
)


def _json_object(path: Path, *, label: str) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], raw)


def _kosis_capture_date_in_korea(pointer_path: Path) -> date:
    pointer = _json_object(pointer_path, label="KOSIS semiconductor history pointer")
    manifest_value = str(pointer.get("manifest_path", "")).strip()
    if not manifest_value:
        raise ValueError("KOSIS semiconductor history pointer is missing manifest_path")
    manifest = _json_object(Path(manifest_value), label="KOSIS semiconductor manifest")
    captured_at_text = str(manifest.get("captured_at", "")).strip()
    try:
        captured_at = datetime.fromisoformat(captured_at_text)
    except ValueError as exc:
        raise ValueError("KOSIS semiconductor manifest captured_at is invalid") from exc
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("KOSIS semiconductor manifest captured_at must be timezone-aware")
    return captured_at.astimezone(KOREA_TZ).date()


def _unavailable_report(report: str, reason: str) -> str:
    lines = [
        report.rstrip(),
        "",
        "## KOSIS 반도체 산업 사이클 증거 (사용 불가)",
        "",
        f"- 상태: `{reason}`",
        "- 산업 증거를 사용할 수 없어 기존 발행사 프록시만 유지합니다.",
        "- 의사결정 점수는 변경하지 않습니다.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def build_investment_decision_snapshot(
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    *,
    valuation_snapshot: str | Path | None = None,
    investor_flow_pointer: str | Path | None = None,
    semiconductor_history_pointer: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build calibrated decisions, then attach optional non-scoring KOSIS evidence."""

    snapshot = _build_calibrated_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=valuation_snapshot,
        investor_flow_pointer=investor_flow_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    explicit_pointer = semiconductor_history_pointer is not None
    if semiconductor_history_pointer is not None:
        pointer = Path(semiconductor_history_pointer)
    else:
        pointer = DEFAULT_SEMICONDUCTOR_HISTORY_POINTER
    if not pointer.is_file():
        if explicit_pointer:
            reason = "semiconductor_industry_evidence_pointer_missing"
            warnings = tuple(dict.fromkeys((*snapshot.warnings, reason)))
            return replace(
                snapshot,
                warnings=warnings,
                report_markdown=_unavailable_report(snapshot.report_markdown, reason),
            )
        return snapshot

    try:
        capture_date = _kosis_capture_date_in_korea(pointer)
        if snapshot.evaluation_date < capture_date:
            raise ValueError(
                "KOSIS current snapshot cannot be applied before its Korea capture date"
            )
        industry = load_semiconductor_industry_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"semiconductor_industry_evidence_unavailable:{type(exc).__name__}"
        warnings = tuple(dict.fromkeys((*snapshot.warnings, reason)))
        return replace(
            snapshot,
            warnings=warnings,
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    proxy = build_semiconductor_cycle_proxy(
        snapshot.financial_history,
        snapshot.market_context,
    )
    bridge = build_semiconductor_cycle_bridge(proxy, industry)
    scorecards = attach_semiconductor_industry_to_scorecards(
        snapshot.scorecards,
        proxy,
        bridge,
    )
    decision_records = attach_semiconductor_industry_to_records(
        snapshot.decision_records,
        scorecards,
    )
    report = append_semiconductor_industry_evidence_report(snapshot.report_markdown, bridge)
    warnings = tuple(
        dict.fromkeys(
            (
                *snapshot.warnings,
                f"semiconductor_industry_evidence:{industry.artifact_id[:12]}",
                f"semiconductor_industry_phase:{industry.heuristic_phase}",
                f"semiconductor_industry_issuer_alignment:{bridge.alignment_state}",
                "semiconductor_industry_evidence_non_scoring",
                "semiconductor_industry_history_not_point_in_time_certified",
            )
        )
    )
    return replace(
        snapshot,
        warnings=warnings,
        scorecards=scorecards,
        decision_records=decision_records,
        report_markdown=report,
    )


__all__ = [
    "DEFAULT_SEMICONDUCTOR_HISTORY_POINTER",
    "build_investment_decision_snapshot",
]
