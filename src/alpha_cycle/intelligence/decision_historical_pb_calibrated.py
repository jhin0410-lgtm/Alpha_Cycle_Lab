"""Attach current own-history P/B evidence after the existing calibrated decision chain."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_forward_estimate_calibrated import (
    build_investment_decision_snapshot as _build_forward_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.historical_pb_decision_evidence import (
    append_historical_pb_report,
    attach_historical_pb_to_scorecards,
    load_historical_pb_decision_evidence,
    sync_record_historical_pb_fields,
)

DEFAULT_HISTORICAL_PB_POINTER = Path(
    "data/private/live-research/historical-pb-evidence/"
    "latest_historical_pb_evidence.json"
)


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## 자사 역사 P/B 증거 (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- peer 상대가치·기존 valuation 점수와 의사결정 점수는 변경하지 않습니다.\n"
    )


def build_investment_decision_snapshot(
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    *,
    valuation_snapshot: str | Path | None = None,
    investor_flow_pointer: str | Path | None = None,
    semiconductor_history_pointer: str | Path | None = None,
    kis_forward_pointer: str | Path | None = None,
    kis_change_pointer: str | Path | None = None,
    historical_pb_pointer: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build existing decisions, then attach qualified historical P/B non-scoring."""

    snapshot = _build_forward_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=valuation_snapshot,
        investor_flow_pointer=investor_flow_pointer,
        semiconductor_history_pointer=semiconductor_history_pointer,
        kis_forward_pointer=kis_forward_pointer,
        kis_change_pointer=kis_change_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )

    explicit_pointer = historical_pb_pointer is not None
    pointer = (
        Path(historical_pb_pointer)
        if historical_pb_pointer is not None
        else DEFAULT_HISTORICAL_PB_POINTER
    )
    if not pointer.is_file():
        if explicit_pointer:
            reason = "historical_pb_evidence_pointer_missing"
            return replace(
                snapshot,
                warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
                report_markdown=_unavailable_report(snapshot.report_markdown, reason),
            )
        return snapshot

    try:
        evidence = load_historical_pb_decision_evidence(pointer)
        if evidence.evaluation_date != snapshot.evaluation_date:
            raise ValueError(
                "historical P/B evidence evaluation date does not match decision date"
            )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"historical_pb_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = attach_historical_pb_to_scorecards(snapshot.scorecards, evidence)
    records = sync_record_historical_pb_fields(snapshot.decision_records, scorecards)
    report = append_historical_pb_report(snapshot.report_markdown, evidence)
    usable = int(evidence.symbols["current_observational_band_usable"].astype(bool).sum())
    warnings = [
        *snapshot.warnings,
        f"historical_pb_evidence:{evidence.artifact_id[:12]}",
        f"historical_pb_current_usable:{usable}/{len(evidence.symbols)}",
        "historical_pb_own_history_observational_non_scoring",
        "historical_pb_historical_vintage_not_certified",
    ]
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=report,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = [
    "DEFAULT_HISTORICAL_PB_POINTER",
    "build_investment_decision_snapshot",
]
