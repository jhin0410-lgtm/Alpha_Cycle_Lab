"""Attach source-bounded semiconductor forward-input coverage after macro/liquidity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_macro_liquidity_calibrated import (
    build_investment_decision_snapshot as _build_macro_liquidity_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.semiconductor_forward_input_decision_evidence import (
    DEFAULT_FORWARD_INPUT_POINTER,
    append_semiconductor_forward_input_report,
    load_semiconductor_forward_input_decision_evidence,
)


def _attach(scorecards: pd.DataFrame, issuer_coverage: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = issuer_coverage.rename(
        columns={
            column: f"semiconductor_forward_{column}"
            for column in issuer_coverage.columns
            if column != "ticker"
        }
    ).copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "semiconductor_forward_required_block_count",
        "semiconductor_forward_descriptive_ready_block_count",
        "semiconductor_forward_numeric_input_ready_block_count",
        "semiconductor_forward_all_descriptive_inputs_covered",
        "semiconductor_forward_all_numeric_inputs_covered",
        "semiconductor_forward_internal_forward_model_certified",
        "semiconductor_forward_numeric_forecast_enabled",
        "semiconductor_forward_decision_score_enabled",
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
        + "\n\n## Semiconductor Forward Inputs (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- historical transmission이나 qualitative commentary를 numeric forecast로 승격하지 않습니다.\n"
        + "- 기존 의사결정 점수·fair value·target price는 변경하지 않습니다.\n"
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build existing chain and attach explicit issuer/block forward-input coverage."""

    snapshot = _build_macro_liquidity_snapshot(
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
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    explicit_pointer = semiconductor_forward_input_pointer is not None
    pointer = (
        Path(semiconductor_forward_input_pointer)
        if semiconductor_forward_input_pointer is not None
        else DEFAULT_FORWARD_INPUT_POINTER
    )
    if not pointer.is_file():
        reason = "semiconductor_forward_input_evidence_missing"
        warnings = tuple(dict.fromkeys((*snapshot.warnings, reason)))
        if explicit_pointer or pointer == DEFAULT_FORWARD_INPUT_POINTER:
            return replace(
                snapshot,
                warnings=warnings,
                report_markdown=_unavailable_report(snapshot.report_markdown, reason),
            )
        return snapshot
    try:
        evidence = load_semiconductor_forward_input_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"semiconductor_forward_input_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            report_markdown=_unavailable_report(snapshot.report_markdown, reason),
        )

    scorecards = _attach(snapshot.scorecards, evidence.issuer_coverage)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_semiconductor_forward_input_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_forward_input_evidence:{evidence.evidence_id[:12]}",
            "semiconductor_forward_input_source_bounded",
            "semiconductor_forward_input_qualitative_not_numeric",
            "semiconductor_forward_model_still_requires_method_reconciliation_and_freeze",
            "semiconductor_forward_input_non_scoring",
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
