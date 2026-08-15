"""Attach verified derived-revenue allocation after direct product-revenue source facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_product_revenue_calibrated import (
    build_investment_decision_snapshot as _build_product_revenue_snapshot,
)
from alpha_cycle.intelligence.semiconductor_baseline_allocation_decision_evidence import (
    DEFAULT_BASELINE_ALLOCATION_POINTER,
    append_semiconductor_baseline_allocation_report,
    load_semiconductor_baseline_allocation_decision_evidence,
)

_FIELDS = [
    "semiconductor_baseline_allocation_available",
    "semiconductor_baseline_allocation_evidence_id",
    "semiconductor_baseline_allocation_required_revenue_block_count",
    "semiconductor_baseline_allocation_allocated_revenue_block_count",
    "semiconductor_baseline_allocation_missing_revenue_block_count",
    "semiconductor_baseline_allocation_reconciliation_delta",
    "semiconductor_baseline_allocation_revenue_reconciliation_certified",
    "semiconductor_baseline_allocation_revenue_model_input_ready",
    "semiconductor_baseline_allocation_profitability_baseline_certified",
    "semiconductor_baseline_allocation_full_baseline_certified",
    "semiconductor_baseline_allocation_source_fact",
    "semiconductor_baseline_allocation_numeric_forecast_enabled",
    "semiconductor_baseline_allocation_decision_score_enabled",
]


def _defaults(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    result["semiconductor_baseline_allocation_available"] = False
    result["semiconductor_baseline_allocation_evidence_id"] = pd.NA
    result["semiconductor_baseline_allocation_required_revenue_block_count"] = 0
    result["semiconductor_baseline_allocation_allocated_revenue_block_count"] = 0
    result["semiconductor_baseline_allocation_missing_revenue_block_count"] = 0
    result["semiconductor_baseline_allocation_reconciliation_delta"] = pd.NA
    result["semiconductor_baseline_allocation_revenue_reconciliation_certified"] = False
    result["semiconductor_baseline_allocation_revenue_model_input_ready"] = False
    result["semiconductor_baseline_allocation_profitability_baseline_certified"] = False
    result["semiconductor_baseline_allocation_full_baseline_certified"] = False
    result["semiconductor_baseline_allocation_source_fact"] = False
    result["semiconductor_baseline_allocation_numeric_forecast_enabled"] = False
    result["semiconductor_baseline_allocation_decision_score_enabled"] = False
    return result


def _attach(
    scorecards: pd.DataFrame,
    *,
    evidence_id: str,
    required_block_count: int,
    allocated_block_count: int,
    missing_block_count: int,
    reconciliation_delta: float,
    revenue_reconciliation_certified: bool,
    revenue_model_input_ready: bool,
) -> pd.DataFrame:
    """Attach a non-authoritative revenue summary without touching direct baseline flags."""

    result = _defaults(scorecards)
    target = result["ticker"].eq("000660")
    result.loc[target, "semiconductor_baseline_allocation_available"] = True
    result.loc[target, "semiconductor_baseline_allocation_evidence_id"] = evidence_id
    result.loc[
        target,
        "semiconductor_baseline_allocation_required_revenue_block_count",
    ] = required_block_count
    result.loc[
        target,
        "semiconductor_baseline_allocation_allocated_revenue_block_count",
    ] = allocated_block_count
    result.loc[
        target,
        "semiconductor_baseline_allocation_missing_revenue_block_count",
    ] = missing_block_count
    result.loc[
        target,
        "semiconductor_baseline_allocation_reconciliation_delta",
    ] = reconciliation_delta
    result.loc[
        target,
        "semiconductor_baseline_allocation_revenue_reconciliation_certified",
    ] = revenue_reconciliation_certified
    result.loc[
        target,
        "semiconductor_baseline_allocation_revenue_model_input_ready",
    ] = revenue_model_input_ready
    return result


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = ["ticker", *_FIELDS]
    supplement = scorecards.loc[:, [item for item in fields if item in scorecards.columns]].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [item for item in _FIELDS if item in result.columns]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## Semiconductor Derived Revenue Allocation (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- direct-fact baseline reconciliation과 company accounting identity는 그대로 유지합니다.\n"
        + "- direct SK hynix product-revenue source facts도 그대로 유지합니다.\n"
        + "- source-specific resolver가 없거나 재현 검증에 실패한 persisted allocation은 신뢰하지 않습니다.\n"
        + "- profitability/full baseline, numeric forecast, Expectation Gap, decision score는 열지 않습니다.\n"
    )


def _replace_unavailable(
    snapshot: InvestmentDecisionSnapshot,
    *,
    reason: str,
) -> InvestmentDecisionSnapshot:
    scorecards = _defaults(snapshot.scorecards)
    records = _sync_records(snapshot.decision_records, scorecards)
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
        report_markdown=_unavailable_report(snapshot.report_markdown, reason),
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through direct product revenue, then attach derived allocation evidence only."""

    snapshot = _build_product_revenue_snapshot(
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
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    pointer = (
        Path(semiconductor_baseline_allocation_pointer)
        if semiconductor_baseline_allocation_pointer is not None
        else DEFAULT_BASELINE_ALLOCATION_POINTER
    )
    if not pointer.is_file():
        return _replace_unavailable(
            snapshot,
            reason="semiconductor_baseline_allocation_evidence_missing",
        )
    try:
        evidence = load_semiconductor_baseline_allocation_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        return _replace_unavailable(
            snapshot,
            reason=f"semiconductor_baseline_allocation_unavailable:{type(exc).__name__}",
        )

    reconciliation = evidence.evidence.reconciliation
    scorecards = _attach(
        snapshot.scorecards,
        evidence_id=evidence.evidence.evidence_id,
        required_block_count=len(reconciliation.required_revenue_blocks),
        allocated_block_count=len(reconciliation.allocated_revenue_blocks),
        missing_block_count=len(reconciliation.missing_revenue_blocks),
        reconciliation_delta=reconciliation.reconciliation_delta,
        revenue_reconciliation_certified=(
            reconciliation.revenue_reconciliation_certified
        ),
        revenue_model_input_ready=reconciliation.revenue_model_input_ready,
    )
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_semiconductor_baseline_allocation_report(
        snapshot.report_markdown,
        evidence,
    )
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_baseline_allocation:{evidence.evidence.evidence_id[:12]}",
            "semiconductor_baseline_allocation_derived_not_source_fact",
            "semiconductor_baseline_allocation_profitability_baseline_blocked",
            "semiconductor_baseline_allocation_full_baseline_blocked",
            "semiconductor_baseline_allocation_numeric_forecast_disabled",
            "semiconductor_baseline_allocation_non_scoring",
        ]
    )
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=report,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["_attach", "_defaults", "build_investment_decision_snapshot"]
