"""Attach current structural semiconductor evidence after transmission evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_transmission_calibrated import (
    build_investment_decision_snapshot as _build_transmission_snapshot,
)
from alpha_cycle.intelligence.semiconductor_structural_decision_evidence import (
    DEFAULT_STRUCTURAL_POINTER,
    append_structural_evidence_report,
    load_structural_decision_evidence,
    structural_coverage_frame,
)


def _attach(scorecards: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = coverage.copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "structural_bundle_id",
        "structural_hbm_demand_mix_status",
        "structural_hbm_capacity_yield_status",
        "structural_competitive_position_status",
        "structural_end_demand_status",
        "structural_memory_pricing_status",
        "structural_export_control_status",
        "structural_issuer_claim_count",
        "structural_customer_claim_count",
        "structural_peer_claim_count",
        "structural_government_claim_count",
        "structural_numeric_memory_price_signal_enabled",
        "structural_decision_score_enabled",
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build existing decisions, then attach validated structural evidence if present."""

    snapshot = _build_transmission_snapshot(
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
    explicit_pointer = semiconductor_structural_pointer is not None
    pointer = (
        Path(semiconductor_structural_pointer)
        if semiconductor_structural_pointer is not None
        else DEFAULT_STRUCTURAL_POINTER
    )
    if not pointer.is_file():
        if explicit_pointer:
            reason = "semiconductor_structural_evidence_pointer_missing"
            return replace(
                snapshot,
                warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
            )
        return snapshot

    try:
        evidence = load_structural_decision_evidence(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        reason = f"semiconductor_structural_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, reason))),
        )

    coverage = structural_coverage_frame(evidence)
    scorecards = _attach(snapshot.scorecards, coverage)
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_structural_evidence_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_structural_evidence:{evidence.bundle.bundle_id[:12]}",
            "semiconductor_structural_primary_source_bounded",
            "semiconductor_structural_source_bytes_not_archived",
            "semiconductor_structural_numeric_memory_price_signal_disabled",
            "semiconductor_structural_non_scoring",
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
