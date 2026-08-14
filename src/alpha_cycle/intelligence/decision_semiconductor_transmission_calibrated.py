"""Attach observational semiconductor industry-to-earnings transmission evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_sector_vertical_calibrated import (
    build_investment_decision_snapshot as _build_sector_vertical_snapshot,
)
from alpha_cycle.intelligence.semiconductor_earnings_transmission import (
    append_semiconductor_transmission_report,
    build_semiconductor_transmission_evidence,
    summarize_semiconductor_transmission,
)

DEFAULT_SEMICONDUCTOR_HISTORY_POINTER = Path(
    "data/private/live-research/kosis-semiconductor-history/"
    "latest_kosis_semiconductor_history.json"
)


def _attach_transmission_fields(
    scorecards: pd.DataFrame,
    summary: pd.DataFrame,
    evidence_id: str,
) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    rows: list[dict[str, object]] = []
    for ticker, group in summary.groupby("ticker", sort=True):
        ready = group["transmission_status"].astype(str).eq("descriptive_history_ready")
        rows.append(
            {
                "ticker": str(ticker).zfill(6),
                "semiconductor_transmission_evidence_id": evidence_id,
                "semiconductor_transmission_hypothesis_count": int(len(group)),
                "semiconductor_transmission_ready_hypothesis_count": int(ready.sum()),
                "semiconductor_transmission_history_ready": bool(ready.all()),
                "semiconductor_transmission_decision_score_enabled": False,
                "semiconductor_transmission_forecast_enabled": False,
                "semiconductor_transmission_causal_claim_enabled": False,
                "semiconductor_transmission_summary_json": json.dumps(
                    group.to_dict(orient="records"),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            }
        )
    if not rows:
        return result
    supplement = pd.DataFrame(rows)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _sync_record_fields(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    fields = [
        "ticker",
        "semiconductor_transmission_evidence_id",
        "semiconductor_transmission_hypothesis_count",
        "semiconductor_transmission_ready_hypothesis_count",
        "semiconductor_transmission_history_ready",
        "semiconductor_transmission_decision_score_enabled",
        "semiconductor_transmission_forecast_enabled",
        "semiconductor_transmission_causal_claim_enabled",
    ]
    available = [column for column in fields if column in scorecards.columns]
    if available == ["ticker"] or not available:
        return records.copy()
    supplement = scorecards.loc[:, available].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [
        column for column in available if column != "ticker" and column in result.columns
    ]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## 반도체 산업 → 기업 실적 transmission (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- 기존 산업·기업·밸류에이션·의사결정 점수는 변경하지 않습니다.\n"
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
    """Build the existing final chain, then attach non-scoring transmission evidence."""

    snapshot = _build_sector_vertical_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=valuation_snapshot,
        investor_flow_pointer=investor_flow_pointer,
        semiconductor_history_pointer=semiconductor_history_pointer,
        kis_forward_pointer=kis_forward_pointer,
        kis_change_pointer=kis_change_pointer,
        historical_pb_pointer=historical_pb_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    explicit_pointer = semiconductor_history_pointer is not None
    pointer = (
        Path(semiconductor_history_pointer)
        if semiconductor_history_pointer is not None
        else DEFAULT_SEMICONDUCTOR_HISTORY_POINTER
    )
    if not pointer.is_file():
        if not explicit_pointer:
            return snapshot
        reason = "semiconductor_transmission_pointer_missing"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    try:
        evidence = build_semiconductor_transmission_evidence(
            pointer,
            snapshot.financial_history,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"semiconductor_transmission_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    summary = summarize_semiconductor_transmission(evidence)
    scorecards = _attach_transmission_fields(
        snapshot.scorecards,
        summary,
        evidence.evidence_id,
    )
    records = _sync_record_fields(snapshot.decision_records, scorecards)
    report = append_semiconductor_transmission_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_transmission_evidence:{evidence.evidence_id[:12]}",
            f"semiconductor_transmission_kosis:{evidence.kosis_artifact_id[:12]}",
            "semiconductor_transmission_observational_non_scoring",
            "semiconductor_transmission_no_causal_or_forecast_claim",
            "semiconductor_transmission_kosis_history_not_point_in_time_certified",
        ]
    )
    for ticker, group in summary.groupby("ticker", sort=True):
        ready = int(
            group["transmission_status"].astype(str).eq("descriptive_history_ready").sum()
        )
        warnings.append(
            f"semiconductor_transmission_ready:{str(ticker).zfill(6)}:{ready}/{len(group)}"
        )
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=report,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = [
    "DEFAULT_SEMICONDUCTOR_HISTORY_POINTER",
    "build_investment_decision_snapshot",
]
