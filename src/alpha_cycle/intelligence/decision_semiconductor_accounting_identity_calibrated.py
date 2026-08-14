"""Attach verified Samsung company accounting identities after direct baseline bridges."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_baseline_reconciliation_calibrated import (
    build_investment_decision_snapshot as _build_baseline_snapshot,
)
from alpha_cycle.intelligence.semiconductor_accounting_identity_decision_evidence import (
    DEFAULT_ACCOUNTING_IDENTITY_POINTER,
    append_semiconductor_accounting_identity_report,
    load_semiconductor_accounting_identity_decision_evidence,
)


def _attach(scorecards: pd.DataFrame, *, evidence_id: str, certified: bool) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    samsung = result["ticker"].eq("005930")
    result["semiconductor_accounting_identity_available"] = False
    result["semiconductor_accounting_identity_evidence_id"] = pd.NA
    result["semiconductor_accounting_identity_corporate_bridge_certified"] = False
    result["semiconductor_accounting_identity_residual_estimate_enabled"] = False
    result["semiconductor_accounting_identity_segment_profit_inference_enabled"] = False
    result.loc[samsung, "semiconductor_accounting_identity_available"] = True
    result.loc[samsung, "semiconductor_accounting_identity_evidence_id"] = evidence_id
    result.loc[
        samsung,
        "semiconductor_accounting_identity_corporate_bridge_certified",
    ] = certified
    return result


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "semiconductor_accounting_identity_available",
        "semiconductor_accounting_identity_evidence_id",
        "semiconductor_accounting_identity_corporate_bridge_certified",
        "semiconductor_accounting_identity_residual_estimate_enabled",
        "semiconductor_accounting_identity_segment_profit_inference_enabled",
    ]
    supplement = scorecards.loc[:, [item for item in fields if item in scorecards.columns]].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [item for item in fields if item != "ticker" and item in result.columns]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## Semiconductor Accounting Identity (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- direct-fact baseline reconciliation은 그대로 유지합니다.\n"
        + "- 미공시 segment profit을 residual subtraction으로 생성하지 않습니다.\n"
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through direct baselines, then attach company accounting identities."""

    snapshot = _build_baseline_snapshot(
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
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    pointer = (
        Path(semiconductor_accounting_identity_pointer)
        if semiconductor_accounting_identity_pointer is not None
        else DEFAULT_ACCOUNTING_IDENTITY_POINTER
    )
    if not pointer.is_file():
        reason = "semiconductor_accounting_identity_evidence_missing"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )
    try:
        evidence = load_semiconductor_accounting_identity_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"semiconductor_accounting_identity_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = _attach(
        snapshot.scorecards,
        evidence_id=evidence.evidence.evidence_id,
        certified=evidence.evidence.corporate_baseline_bridge_certified,
    )
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_semiconductor_accounting_identity_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_accounting_identity:{evidence.evidence.evidence_id[:12]}",
            "semiconductor_accounting_identity_company_level_only",
            "semiconductor_accounting_identity_residual_estimates_disabled",
            "semiconductor_accounting_identity_segment_profit_inference_disabled",
            "semiconductor_accounting_identity_non_scoring",
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
