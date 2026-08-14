"""Attach verified semiconductor baseline bridges after operating assumptions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_operating_assumption_calibrated import (
    build_investment_decision_snapshot as _build_operating_assumption_snapshot,
)
from alpha_cycle.intelligence.semiconductor_baseline_reconciliation_decision_evidence import (
    DEFAULT_BASELINE_RECONCILIATION_POINTER,
    append_semiconductor_baseline_reconciliation_report,
    load_semiconductor_baseline_reconciliation_decision_evidence,
)

_RENAMES = {
    "baseline_reconciliation_required_count": "semiconductor_baseline_reconciliation_required_count",
    "baseline_reconciliation_certified_count": "semiconductor_baseline_reconciliation_certified_count",
    "baseline_reconciliation_certified": "semiconductor_baseline_reconciliation_certified",
    "residual_derivation_enabled": "semiconductor_baseline_residual_derivation_enabled",
    "internal_estimate_enabled": "semiconductor_baseline_internal_estimate_enabled",
    "numeric_forecast_enabled": "semiconductor_baseline_numeric_forecast_enabled",
    "decision_score_enabled": "semiconductor_baseline_decision_score_enabled",
}


def _attach(scorecards: pd.DataFrame, issuer_summary: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = issuer_summary.rename(columns=_RENAMES).copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = ["ticker", *_RENAMES.values()]
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
        + "\n\n## Semiconductor Baseline Reconciliation (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- 미공개 block profitability를 residual subtraction이나 내부 추정으로 채우지 않습니다.\n"
        + "- 기존 forecast·fair value·target price·점수는 변경하지 않습니다.\n"
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through operating assumptions, then attach direct-fact baseline bridges."""

    snapshot = _build_operating_assumption_snapshot(
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
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    pointer = (
        Path(semiconductor_baseline_reconciliation_pointer)
        if semiconductor_baseline_reconciliation_pointer is not None
        else DEFAULT_BASELINE_RECONCILIATION_POINTER
    )
    if not pointer.is_file():
        reason = "semiconductor_baseline_reconciliation_evidence_missing"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )
    try:
        evidence = load_semiconductor_baseline_reconciliation_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"semiconductor_baseline_reconciliation_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = _attach(snapshot.scorecards, evidence.evidence.issuer_summary)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_semiconductor_baseline_reconciliation_report(
        snapshot.report_markdown,
        evidence,
    )
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_baseline_reconciliation:{evidence.evidence.evidence_id[:12]}",
            "semiconductor_baseline_direct_fact_only",
            "semiconductor_baseline_residual_derivation_disabled",
            "semiconductor_baseline_internal_estimates_disabled",
            "semiconductor_baseline_reconciliation_non_scoring",
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
