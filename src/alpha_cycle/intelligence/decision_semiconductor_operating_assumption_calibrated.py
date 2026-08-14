"""Attach verified semiconductor Bull/Base/Bear assumptions after forward-input evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_forward_input_calibrated import (
    build_investment_decision_snapshot as _build_forward_input_snapshot,
)
from alpha_cycle.intelligence.semiconductor_operating_assumption_decision_evidence import (
    DEFAULT_OPERATING_ASSUMPTION_POINTER,
    append_semiconductor_operating_assumption_report,
    load_semiconductor_operating_assumption_decision_evidence,
)


def _attach(scorecards: pd.DataFrame, issuer_summary: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = issuer_summary.rename(
        columns={
            column: f"semiconductor_assumption_{column}"
            for column in issuer_summary.columns
            if column != "ticker"
        }
    ).copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "semiconductor_assumption_horizon_quarters",
        "semiconductor_assumption_all_scenario_assumptions_documented",
        "semiconductor_assumption_all_scenario_assumptions_model_use_ready",
        "semiconductor_assumption_baseline_reconciliation_required_count",
        "semiconductor_assumption_direct_numeric_baseline_requirement_count",
        "semiconductor_assumption_baseline_reconciliation_certified",
        "semiconductor_assumption_output_method_certified",
        "semiconductor_assumption_company_reconciliation_certified",
        "semiconductor_assumption_model_version_frozen",
        "semiconductor_assumption_internal_forward_model_certified",
        "semiconductor_assumption_scenario_probabilities_enabled",
        "semiconductor_assumption_numeric_forecast_enabled",
        "semiconductor_assumption_decision_score_enabled",
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
        + "\n\n## Semiconductor Operating Assumptions (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- source evidence를 내부 Bull/Base/Bear 숫자로 자동 변환하지 않습니다.\n"
        + "- baseline bridge·forecast·fair value·target price·점수는 변경하지 않습니다.\n"
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through forward inputs, then attach internal scenario-assumption readiness."""

    snapshot = _build_forward_input_snapshot(
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
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    pointer = (
        Path(semiconductor_operating_assumption_pointer)
        if semiconductor_operating_assumption_pointer is not None
        else DEFAULT_OPERATING_ASSUMPTION_POINTER
    )
    if not pointer.is_file():
        reason = "semiconductor_operating_assumption_evidence_missing"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )
    try:
        evidence = load_semiconductor_operating_assumption_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"semiconductor_operating_assumption_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = _attach(snapshot.scorecards, evidence.issuer_summary)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_semiconductor_operating_assumption_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_operating_assumption_pack:{evidence.pack.pack_id[:12]}",
            "semiconductor_operating_assumptions_are_internal_model_choices",
            "semiconductor_scenario_probabilities_disabled",
            "semiconductor_baseline_reconciliation_still_required",
            "semiconductor_operating_assumption_non_scoring",
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
