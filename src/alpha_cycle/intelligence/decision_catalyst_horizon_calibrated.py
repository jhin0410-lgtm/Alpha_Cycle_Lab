"""Attach certified future Catalyst Horizon v1 after Expectation Gap readiness."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.catalyst_horizon_decision_evidence import (
    DEFAULT_CATALYST_HORIZON_POINTER,
    append_catalyst_horizon_report,
    load_catalyst_horizon_decision_evidence,
)
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_expectation_gap_calibrated import (
    build_investment_decision_snapshot as _build_expectation_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy


def _attach(scorecards: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = summary.copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "catalyst_horizon_evidence_id",
        "catalyst_event_count",
        "future_certified_event_count",
        "catalyst_1m_count",
        "catalyst_3m_count",
        "catalyst_6m_count",
        "catalyst_12m_count",
        "binary_event_count",
        "pending_prerequisite_count",
        "surprise_candidate_count",
        "catalyst_horizon_status",
        "decision_score_enabled",
        "forecast_enabled",
    ]
    available = [column for column in fields if column in scorecards.columns]
    if not available or available == ["ticker"]:
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
        + "\n\n## Catalyst Horizon v1 (미래일정 evidence 미연결)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- 과거 공시를 미래 catalyst로 재분류하지 않습니다.\n"
        + "- 기존 catalyst context 및 의사결정 점수는 변경하지 않습니다.\n"
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
    semiconductor_structural_pointer: str | Path | None = None,
    macro_liquidity_pointer: str | Path | None = None,
    semiconductor_forward_input_pointer: str | Path | None = None,
    semiconductor_operating_assumption_pointer: str | Path | None = None,
    semiconductor_baseline_reconciliation_pointer: str | Path | None = None,
    semiconductor_accounting_identity_pointer: str | Path | None = None,
    semiconductor_baseline_allocation_pointer: str | Path | None = None,
    catalyst_horizon_pointer: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build existing chain, then attach certified future catalyst timing if available."""

    snapshot = _build_expectation_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=valuation_snapshot,
        investor_flow_pointer=investor_flow_pointer,
        semiconductor_history_pointer=semiconductor_history_pointer,
        kis_forward_pointer=kis_forward_pointer,
        kis_change_pointer=kis_change_pointer,
        historical_pb_pointer=historical_pb_pointer,
        semiconductor_structural_pointer=semiconductor_structural_pointer,
        macro_liquidity_pointer=macro_liquidity_pointer,
        semiconductor_forward_input_pointer=semiconductor_forward_input_pointer,
        semiconductor_operating_assumption_pointer=semiconductor_operating_assumption_pointer,
        semiconductor_baseline_reconciliation_pointer=(
            semiconductor_baseline_reconciliation_pointer
        ),
        semiconductor_accounting_identity_pointer=semiconductor_accounting_identity_pointer,
        semiconductor_baseline_allocation_pointer=semiconductor_baseline_allocation_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    explicit_pointer = catalyst_horizon_pointer is not None
    pointer = (
        Path(catalyst_horizon_pointer)
        if catalyst_horizon_pointer is not None
        else DEFAULT_CATALYST_HORIZON_POINTER
    )
    if not pointer.is_file():
        reason = "catalyst_horizon_future_timing_evidence_missing"
        missing_warnings = tuple(dict.fromkeys((*snapshot.warnings, reason)))
        if explicit_pointer or pointer == DEFAULT_CATALYST_HORIZON_POINTER:
            return replace(
                snapshot,
                warnings=missing_warnings,
                report_markdown=_unavailable_report(snapshot.report_markdown, reason),
            )
        return snapshot

    try:
        evidence = load_catalyst_horizon_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"catalyst_horizon_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = _attach(snapshot.scorecards, evidence.summary)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_catalyst_horizon_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"catalyst_horizon_evidence:{evidence.evidence.evidence_id[:12]}",
            "catalyst_horizon_future_timing_source_bounded",
            "catalyst_horizon_past_disclosures_not_relabelled_as_future",
            "catalyst_horizon_non_scoring",
            "catalyst_horizon_no_automatic_event_forecast",
        ]
    )
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=report,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["build_investment_decision_snapshot"]
