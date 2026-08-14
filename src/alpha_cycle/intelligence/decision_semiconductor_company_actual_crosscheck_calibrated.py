"""Attach independent SEC company actual and OpenDART/SEC crosscheck before Expectation Gap."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.company_actual_crosscheck_decision_evidence import (
    CompanyActualCrosscheckEvidence,
    append_company_actual_crosscheck_report,
    build_company_actual_crosscheck,
)
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_company_actual_calibrated import (
    build_investment_decision_snapshot as _build_company_actual_snapshot,
)
from alpha_cycle.intelligence.opendart_provisional_earnings_decision_evidence import (
    DEFAULT_PROVISIONAL_EARNINGS_POINTER,
    load_opendart_provisional_earnings_decision_evidence,
)
from alpha_cycle.intelligence.sec_company_actual import SecCompanyActualEvidence
from alpha_cycle.intelligence.sec_company_actual_decision_evidence import (
    DEFAULT_SEC_COMPANY_ACTUAL_POINTER,
    append_sec_company_actual_report,
    load_sec_company_actual_decision_evidence,
)

_FIELDS = [
    "sec_company_actual_available",
    "sec_company_actual_evidence_id",
    "sec_company_actual_accession_number",
    "sec_company_actual_revenue_krw_million",
    "sec_company_actual_operating_income_krw_million",
    "sec_company_actual_net_income_krw_million",
    "sec_company_actual_product_baseline_eligible",
    "sec_company_actual_numeric_forecast_enabled",
    "sec_company_actual_decision_score_enabled",
    "company_actual_crosscheck_available",
    "company_actual_crosscheck_evidence_id",
    "company_actual_crosscheck_certified",
    "company_actual_crosscheck_revenue_delta_krw_million",
    "company_actual_crosscheck_operating_income_delta_krw_million",
    "company_actual_crosscheck_net_income_delta_krw_million",
    "company_actual_crosscheck_product_baseline_eligible",
    "company_actual_crosscheck_numeric_forecast_enabled",
    "company_actual_crosscheck_decision_score_enabled",
]


def _defaults(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    result["sec_company_actual_available"] = False
    result["sec_company_actual_evidence_id"] = pd.NA
    result["sec_company_actual_accession_number"] = pd.NA
    result["sec_company_actual_revenue_krw_million"] = pd.NA
    result["sec_company_actual_operating_income_krw_million"] = pd.NA
    result["sec_company_actual_net_income_krw_million"] = pd.NA
    result["sec_company_actual_product_baseline_eligible"] = False
    result["sec_company_actual_numeric_forecast_enabled"] = False
    result["sec_company_actual_decision_score_enabled"] = False
    result["company_actual_crosscheck_available"] = False
    result["company_actual_crosscheck_evidence_id"] = pd.NA
    result["company_actual_crosscheck_certified"] = False
    result["company_actual_crosscheck_revenue_delta_krw_million"] = pd.NA
    result["company_actual_crosscheck_operating_income_delta_krw_million"] = pd.NA
    result["company_actual_crosscheck_net_income_delta_krw_million"] = pd.NA
    result["company_actual_crosscheck_product_baseline_eligible"] = False
    result["company_actual_crosscheck_numeric_forecast_enabled"] = False
    result["company_actual_crosscheck_decision_score_enabled"] = False
    return result


def _attach_sec(
    scorecards: pd.DataFrame,
    evidence: SecCompanyActualEvidence,
) -> pd.DataFrame:
    result = _defaults(scorecards)
    target = result["ticker"].eq(evidence.ticker)
    result.loc[target, "sec_company_actual_available"] = True
    result.loc[target, "sec_company_actual_evidence_id"] = evidence.evidence_id
    result.loc[target, "sec_company_actual_accession_number"] = evidence.accession_number
    result.loc[target, "sec_company_actual_revenue_krw_million"] = evidence.metrics.revenue
    result.loc[
        target,
        "sec_company_actual_operating_income_krw_million",
    ] = evidence.metrics.operating_income
    result.loc[target, "sec_company_actual_net_income_krw_million"] = evidence.metrics.net_income
    return result


def _attach_crosscheck(
    scorecards: pd.DataFrame,
    evidence: CompanyActualCrosscheckEvidence,
) -> pd.DataFrame:
    result = scorecards.copy()
    target = result["ticker"].astype("string").str.zfill(6).eq(evidence.ticker)
    result.loc[target, "company_actual_crosscheck_available"] = True
    result.loc[target, "company_actual_crosscheck_evidence_id"] = evidence.evidence_id
    result.loc[target, "company_actual_crosscheck_certified"] = evidence.crosscheck_certified
    result.loc[
        target,
        "company_actual_crosscheck_revenue_delta_krw_million",
    ] = evidence.revenue_delta_krw_million
    result.loc[
        target,
        "company_actual_crosscheck_operating_income_delta_krw_million",
    ] = evidence.operating_income_delta_krw_million
    result.loc[
        target,
        "company_actual_crosscheck_net_income_delta_krw_million",
    ] = evidence.net_income_delta_krw_million
    return result


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = ["ticker", *_FIELDS]
    supplement = scorecards.loc[:, [field for field in fields if field in scorecards.columns]].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [field for field in _FIELDS if field in result.columns]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## SEC / OpenDART Company Actual Cross-check (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- 기존 OpenDART company actual은 유지하며, cross-check 부재를 제품 baseline으로 대체하지 않습니다.\n"
        + "- product baseline, numeric forecast, Expectation Gap, decision score는 이 계층으로 열리지 않습니다.\n"
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
    opendart_provisional_earnings_pointer: str | Path | None = None,
    sec_company_actual_pointer: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through OpenDART actual, then attach SEC actual and independent crosscheck."""

    snapshot = _build_company_actual_snapshot(
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
        opendart_provisional_earnings_pointer=opendart_provisional_earnings_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    sec_pointer = (
        Path(sec_company_actual_pointer)
        if sec_company_actual_pointer is not None
        else DEFAULT_SEC_COMPANY_ACTUAL_POINTER
    )
    if not sec_pointer.is_file():
        return _replace_unavailable(snapshot, reason="sec_company_actual_evidence_missing")
    try:
        sec = load_sec_company_actual_decision_evidence(
            sec_pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        return _replace_unavailable(
            snapshot,
            reason=f"sec_company_actual_unavailable:{type(exc).__name__}",
        )

    scorecards = _attach_sec(snapshot.scorecards, sec)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_sec_company_actual_report(snapshot.report_markdown, sec)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"sec_company_actual:{sec.evidence_id[:12]}",
            "sec_company_actual_company_only",
            "sec_company_actual_product_baseline_disabled",
            "sec_company_actual_non_scoring",
        ]
    )

    opendart_pointer = (
        Path(opendart_provisional_earnings_pointer)
        if opendart_provisional_earnings_pointer is not None
        else DEFAULT_PROVISIONAL_EARNINGS_POINTER
    )
    if not opendart_pointer.is_file():
        reason = "company_actual_crosscheck_opendart_evidence_missing"
        return replace(
            snapshot,
            scorecards=scorecards,
            decision_records=records,
            report_markdown=_unavailable_report(report, reason),
            warnings=tuple(dict.fromkeys((*warnings, reason))),
        )
    try:
        opendart = load_opendart_provisional_earnings_decision_evidence(
            opendart_pointer,
            evaluation_date=snapshot.evaluation_date,
        )
        crosscheck = build_company_actual_crosscheck(opendart, sec)
    except (OSError, TypeError, ValueError) as exc:
        reason = f"company_actual_crosscheck_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            scorecards=scorecards,
            decision_records=records,
            report_markdown=_unavailable_report(report, reason),
            warnings=tuple(dict.fromkeys((*warnings, reason))),
        )

    scorecards = _attach_crosscheck(scorecards, crosscheck)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_company_actual_crosscheck_report(report, crosscheck)
    warnings.extend(
        [
            f"company_actual_crosscheck:{crosscheck.evidence_id[:12]}",
            (
                "company_actual_crosscheck_certified"
                if crosscheck.crosscheck_certified
                else "company_actual_crosscheck_mismatch"
            ),
            "company_actual_crosscheck_product_baseline_disabled",
            "company_actual_crosscheck_non_scoring",
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
    "_attach_crosscheck",
    "_attach_sec",
    "_defaults",
    "build_investment_decision_snapshot",
]
