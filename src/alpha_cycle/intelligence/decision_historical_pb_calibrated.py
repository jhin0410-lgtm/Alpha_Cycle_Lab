"""Attach current own-history P/B evidence after the existing calibrated decision chain."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_forward_estimate_calibrated import (
    build_investment_decision_snapshot as _build_forward_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.historical_pb_decision_evidence import (
    HistoricalPbDecisionEvidence,
    append_historical_pb_report,
    attach_historical_pb_to_scorecards,
    load_historical_pb_decision_evidence,
    sync_record_historical_pb_fields,
)
from alpha_cycle.intelligence.pb_roe_valuation_regime_readiness import (
    append_pb_roe_regime_report,
    attach_pb_roe_regime_to_scorecards,
    build_pb_roe_valuation_regime_evidence,
    sync_record_pb_roe_regime_fields,
)

DEFAULT_HISTORICAL_PB_POINTER = Path(
    "data/private/live-research/historical-pb-evidence/"
    "latest_historical_pb_evidence.json"
)
_GENERIC_HISTORICAL_VALUATION_GAP = "글로벌 비교기업과 과거 밸류에이션 밴드 미연결"
_OWN_HISTORY_CONNECTED_GAP = (
    "글로벌 비교기업 미연결 (자사 역사 P/B 밴드 연결됨, 비점수)"
)


def _unavailable_report(report: str, reason: str) -> str:
    remediation = ""
    if reason.startswith("historical_pb_evaluation_date_mismatch:"):
        remediation = (
            "- 조치: 현재 live run 완료 후 `./scripts/refresh_historical_pb.cmd`로 "
            "P/B 증거를 갱신한 뒤 live pipeline을 다시 실행하세요.\n"
        )
    return (
        report.rstrip()
        + "\n\n## 자사 역사 P/B 증거 (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + remediation
        + "- peer 상대가치·기존 valuation 점수와 의사결정 점수는 변경하지 않습니다.\n"
    )


def _reconcile_scorecard_gaps(scorecards: pd.DataFrame) -> pd.DataFrame:
    required = {"historical_pb_evidence_available", "evidence_gaps"}
    if not required.issubset(scorecards.columns):
        return scorecards.copy()
    result = scorecards.copy()
    reconciled: list[object] = []
    for raw in result.to_dict(orient="records"):
        gaps = raw.get("evidence_gaps")
        if not bool(raw.get("historical_pb_evidence_available")) or not isinstance(gaps, str):
            reconciled.append(gaps)
            continue
        try:
            parsed = json.loads(gaps)
        except (TypeError, ValueError):
            reconciled.append(gaps)
            continue
        if not isinstance(parsed, list):
            reconciled.append(gaps)
            continue
        updated = [
            _OWN_HISTORY_CONNECTED_GAP
            if str(item) == _GENERIC_HISTORICAL_VALUATION_GAP
            else str(item)
            for item in parsed
        ]
        reconciled.append(json.dumps(list(dict.fromkeys(updated)), ensure_ascii=False))
    result["evidence_gaps"] = pd.Series(reconciled, index=result.index, dtype="object")
    return result


def _reconcile_report_gaps(
    report: str,
    evidence: HistoricalPbDecisionEvidence,
) -> str:
    usable = evidence.symbols["current_observational_band_usable"].astype(bool)
    if not bool(usable.all()):
        return report
    return report.replace(
        _GENERIC_HISTORICAL_VALUATION_GAP,
        _OWN_HISTORY_CONNECTED_GAP,
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
    except (OSError, TypeError, ValueError) as exc:
        reason = f"historical_pb_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    if evidence.evaluation_date != snapshot.evaluation_date:
        reason = (
            "historical_pb_evaluation_date_mismatch:"
            f"evidence={evidence.evaluation_date.isoformat()}:"
            f"decision={snapshot.evaluation_date.isoformat()}"
        )
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = attach_historical_pb_to_scorecards(snapshot.scorecards, evidence)
    scorecards = _reconcile_scorecard_gaps(scorecards)
    records = sync_record_historical_pb_fields(snapshot.decision_records, scorecards)
    base_report = _reconcile_report_gaps(snapshot.report_markdown, evidence)
    report = append_historical_pb_report(base_report, evidence)
    warnings = list(snapshot.warnings)

    regime_evidence = None
    if snapshot.valuation_snapshot_id is None:
        warnings.append("pb_roe_regime_unavailable:valuation_snapshot_missing")
    else:
        try:
            regime_evidence = build_pb_roe_valuation_regime_evidence(
                snapshot.financial_history,
                evidence,
                evaluation_date=snapshot.evaluation_date,
                valuation_snapshot_id=snapshot.valuation_snapshot_id,
            )
        except (TypeError, ValueError) as exc:
            warnings.append(f"pb_roe_regime_unavailable:{type(exc).__name__}")

    if regime_evidence is not None:
        scorecards = attach_pb_roe_regime_to_scorecards(scorecards, regime_evidence)
        records = sync_record_pb_roe_regime_fields(records, scorecards)
        report = append_pb_roe_regime_report(report, regime_evidence)
        available = int(
            regime_evidence.rows["regime_evidence_available"].astype(bool).sum()
        )
        percentile_ready = int(
            regime_evidence.rows["ttm_roe_history_ready"].astype(bool).sum()
        )
        warnings.extend(
            [
                f"pb_roe_regime_evidence:{regime_evidence.evidence_id[:12]}",
                f"pb_roe_regime_available:{available}/{len(regime_evidence.rows)}",
                (
                    "pb_roe_regime_percentile_ready:"
                    f"{percentile_ready}/{len(regime_evidence.rows)}"
                ),
                "pb_roe_regime_descriptive_non_scoring",
                "pb_roe_regime_no_forward_roe_or_cost_of_equity",
            ]
        )
        if percentile_ready < len(regime_evidence.rows):
            warnings.append("pb_roe_regime_percentile_withheld_insufficient_history")

    usable = int(evidence.symbols["current_observational_band_usable"].astype(bool).sum())
    warnings.extend(
        [
            f"historical_pb_evidence:{evidence.artifact_id[:12]}",
            f"historical_pb_current_usable:{usable}/{len(evidence.symbols)}",
            "historical_pb_own_history_observational_non_scoring",
            "historical_pb_historical_vintage_not_certified",
        ]
    )
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
