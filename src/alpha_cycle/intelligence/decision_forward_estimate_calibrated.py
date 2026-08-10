"""Attach optional non-scoring KIS forward estimate evidence to calibrated decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_industry_evidence_calibrated import (
    build_investment_decision_snapshot as _build_industry_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.kis_forward_decision_evidence import (
    append_kis_forward_report,
    attach_kis_forward_to_scorecards,
    load_kis_forward_decision_evidence,
    reconcile_expectation_evidence_gaps,
    sync_record_forward_fields,
)
from alpha_cycle.intelligence.kis_forward_forecast_trust import (
    FORWARD_BLOCK_REASON,
    FORWARD_NUMERIC_EVIDENCE_ELIGIBLE,
)

KOREA_TZ = ZoneInfo("Asia/Seoul")
DEFAULT_KIS_FORWARD_POINTER = Path(
    "data/private/live-research/kis-forward-estimates/latest_kis_forward_estimates.json"
)
DEFAULT_KIS_CHANGE_POINTER = Path(
    "data/private/live-research/kis-forward-estimate-changes/"
    "latest_kis_forward_estimate_changes.json"
)


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## KIS forward 실적 추정 증거 (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- 역사 실적 row/scale 교차검증은 유지되지만 forecast DATA 열의 기간 대응과 "
        + "forecast 열 단위 연속성이 별도로 인증되지 않았습니다.\n"
        + "- 기존 의사결정 점수는 변경하지 않습니다.\n"
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build existing calibrated decisions, then attach KIS forward evidence if qualified."""

    snapshot = _build_industry_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=valuation_snapshot,
        investor_flow_pointer=investor_flow_pointer,
        semiconductor_history_pointer=semiconductor_history_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )

    # The existing private forward artifacts were created after historical row/scale
    # crosschecks, but before forecast-column period and scale continuity were certified.
    # Quarantine them at the final decision boundary regardless of local pointer presence.
    if not FORWARD_NUMERIC_EVIDENCE_ELIGIBLE:
        warning = f"kis_forward_evidence_blocked:{FORWARD_BLOCK_REASON}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, warning))),
            report_markdown=_unavailable_report(snapshot.report_markdown, FORWARD_BLOCK_REASON),
        )

    explicit_forward = kis_forward_pointer is not None
    forward_pointer = (
        Path(kis_forward_pointer)
        if kis_forward_pointer is not None
        else DEFAULT_KIS_FORWARD_POINTER
    )
    if not forward_pointer.is_file():
        if explicit_forward:
            reason = "kis_forward_evidence_pointer_missing"
            return replace(
                snapshot,
                warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
                report_markdown=_unavailable_report(snapshot.report_markdown, reason),
            )
        return snapshot

    change_pointer = (
        Path(kis_change_pointer)
        if kis_change_pointer is not None
        else DEFAULT_KIS_CHANGE_POINTER
    )
    try:
        evidence = load_kis_forward_decision_evidence(
            forward_pointer,
            change_pointer_path=change_pointer if change_pointer.is_file() else None,
        )
        source_date = evidence.source_expectation_captured_at.astimezone(KOREA_TZ).date()
        if source_date > snapshot.evaluation_date:
            raise ValueError(
                "KIS forward source snapshot cannot be applied before its Korea capture date"
            )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"kis_forward_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = attach_kis_forward_to_scorecards(snapshot.scorecards, evidence)
    scorecards = reconcile_expectation_evidence_gaps(scorecards)
    records = sync_record_forward_fields(snapshot.decision_records, scorecards)
    report = append_kis_forward_report(snapshot.report_markdown, evidence)
    warnings = [
        *snapshot.warnings,
        f"kis_forward_evidence:{evidence.artifact_id[:12]}",
        "kis_forward_historical_semantics_crosschecked",
        "kis_forward_provider_semantics_not_certified",
        "kis_forward_evidence_non_scoring",
    ]
    if evidence.estimate_snapshot_change_verified:
        warnings.append("kis_estimate_snapshot_change_available_non_consensus")
    else:
        warnings.append("kis_estimate_snapshot_change_baseline_only")
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=report,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = [
    "DEFAULT_KIS_CHANGE_POINTER",
    "DEFAULT_KIS_FORWARD_POINTER",
    "build_investment_decision_snapshot",
]
