"""Attach provider-agnostic Expectation Gap v1 readiness after macro/liquidity."""

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
from alpha_cycle.intelligence.expectation_gap_decision_evidence import (
    append_expectation_gap_report,
    build_expectation_gap_decision_evidence,
)


def _attach(scorecards: pd.DataFrame, evidence_rows: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = evidence_rows.rename(
        columns={column: f"expectation_gap_{column}" for column in evidence_rows.columns if column != "ticker"}
    ).copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "expectation_gap_expectation_provider_id",
        "expectation_gap_expectation_level_status",
        "expectation_gap_expectation_revision_status",
        "expectation_gap_internal_forward_view_status",
        "expectation_gap_expectation_gap_status",
        "expectation_gap_numeric_expectation_level_enabled",
        "expectation_gap_numeric_expectation_revision_enabled",
        "expectation_gap_expectation_gap_enabled",
        "expectation_gap_decision_score_enabled",
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build existing chain, then attach expectation certification/readiness only."""

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
    evidence = build_expectation_gap_decision_evidence(snapshot.scorecards)
    scorecards = _attach(snapshot.scorecards, evidence.rows)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_expectation_gap_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            "expectation_gap_v1_readiness_only",
            "expectation_gap_kis_forward_level_blocked",
            "expectation_gap_kis_revision_blocked",
            "expectation_gap_internal_forward_model_not_certified",
            "expectation_gap_numeric_gap_disabled",
            "expectation_gap_non_scoring",
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
