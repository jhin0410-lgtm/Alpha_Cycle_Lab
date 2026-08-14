"""Attach verified company-level provisional actuals after derived revenue allocation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_baseline_allocation_calibrated import (
    build_investment_decision_snapshot as _build_baseline_allocation_snapshot,
)
from alpha_cycle.intelligence.opendart_provisional_earnings_decision_evidence import (
    DEFAULT_PROVISIONAL_EARNINGS_POINTER,
    ProvisionalEarningsDecisionEvidence,
    append_opendart_provisional_earnings_report,
    load_opendart_provisional_earnings_decision_evidence,
)


def _attach(
    scorecards: pd.DataFrame,
    evidence: ProvisionalEarningsDecisionEvidence,
) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    target = result["ticker"].eq(evidence.ticker)
    result["opendart_provisional_company_actual_available"] = False
    result["opendart_provisional_evidence_id"] = pd.NA
    result["opendart_provisional_period_end"] = pd.NA
    result["opendart_provisional_revenue_krw_million"] = pd.NA
    result["opendart_provisional_operating_income_krw_million"] = pd.NA
    result["opendart_provisional_net_income_krw_million"] = pd.NA
    result["opendart_provisional_product_baseline_eligible"] = False
    result["opendart_provisional_decision_score_enabled"] = False
    result.loc[target, "opendart_provisional_company_actual_available"] = True
    result.loc[target, "opendart_provisional_evidence_id"] = evidence.evidence_id
    result.loc[target, "opendart_provisional_period_end"] = evidence.period_end.isoformat()
    result.loc[target, "opendart_provisional_revenue_krw_million"] = evidence.metrics.revenue
    result.loc[
        target,
        "opendart_provisional_operating_income_krw_million",
    ] = evidence.metrics.operating_income
    result.loc[target, "opendart_provisional_net_income_krw_million"] = evidence.metrics.net_income
    return result


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "opendart_provisional_company_actual_available",
        "opendart_provisional_evidence_id",
        "opendart_provisional_period_end",
        "opendart_provisional_revenue_krw_million",
        "opendart_provisional_operating_income_krw_million",
        "opendart_provisional_net_income_krw_million",
        "opendart_provisional_product_baseline_eligible",
        "opendart_provisional_decision_score_enabled",
    ]
    available = [field for field in fields if field in scorecards.columns]
    supplement = scorecards.loc[:, available].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [field for field in available if field != "ticker" and field in result.columns]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## OpenDART 잠정실적 Actual (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- 회사 전체 actual이 없어도 기존 product/forward evidence를 임의 생성하지 않습니다.\n"
        + "- 기존 decision score와 valuation은 변경하지 않습니다.\n"
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
    opendart_provisional_earnings_pointer: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through derived revenue allocation, then attach company actual evidence."""

    snapshot = _build_baseline_allocation_snapshot(
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
    pointer = (
        Path(opendart_provisional_earnings_pointer)
        if opendart_provisional_earnings_pointer is not None
        else DEFAULT_PROVISIONAL_EARNINGS_POINTER
    )
    if not pointer.is_file():
        reason = "opendart_provisional_earnings_evidence_missing"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )
    try:
        evidence = load_opendart_provisional_earnings_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"opendart_provisional_earnings_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = _attach(snapshot.scorecards, evidence)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_opendart_provisional_earnings_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"opendart_provisional_earnings:{evidence.evidence_id[:12]}",
            "opendart_provisional_company_actual_only",
            "opendart_provisional_product_baseline_disabled",
            "opendart_provisional_historical_vintage_not_certified",
            "opendart_provisional_non_scoring",
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
