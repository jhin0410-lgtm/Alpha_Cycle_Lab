"""Attach source-bounded Macro/Liquidity Vertical v1 to final decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_structural_calibrated import (
    build_investment_decision_snapshot as _build_structural_snapshot,
)
from alpha_cycle.intelligence.macro_liquidity_decision_evidence import (
    DEFAULT_MACRO_LIQUIDITY_POINTER,
    append_macro_liquidity_report,
    build_macro_liquidity_decision_evidence,
)


def _attach_shared_macro_fields(
    scorecards: pd.DataFrame,
    *,
    evidence_id: str,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    result = scorecards.copy()
    if "ticker" not in result.columns:
        raise ValueError("Macro liquidity scorecards must contain ticker")
    status_lookup = {
        str(raw["dimension"]): str(raw["status"])
        for raw in coverage.to_dict(orient="records")
    }
    result["macro_liquidity_evidence_id"] = evidence_id
    result["macro_liquidity_discount_rate_status"] = status_lookup.get(
        "us_real_discount_rate", "missing"
    )
    result["macro_liquidity_dollar_status"] = status_lookup.get(
        "broad_us_dollar", "missing"
    )
    result["macro_liquidity_financial_conditions_status"] = status_lookup.get(
        "us_financial_conditions", "missing"
    )
    result["macro_liquidity_fed_balance_sheet_status"] = status_lookup.get(
        "fed_balance_sheet", "missing"
    )
    result["macro_liquidity_reserve_balances_status"] = status_lookup.get(
        "fed_reserve_balances", "missing"
    )
    result["macro_liquidity_korea_rate_status"] = status_lookup.get(
        "korea_policy_rate", "missing"
    )
    result["macro_liquidity_usd_krw_status"] = status_lookup.get("usd_krw", "missing")
    result["macro_liquidity_investor_flow_status"] = status_lookup.get(
        "korea_investor_flow", "missing"
    )
    result["macro_liquidity_semiconductor_risk_appetite_status"] = status_lookup.get(
        "semiconductor_risk_appetite", "missing"
    )
    result["macro_liquidity_decision_score_enabled"] = False
    result["macro_liquidity_composite_score_enabled"] = False
    result["macro_liquidity_forecast_enabled"] = False
    return result


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = [
        "ticker",
        "macro_liquidity_evidence_id",
        "macro_liquidity_discount_rate_status",
        "macro_liquidity_dollar_status",
        "macro_liquidity_financial_conditions_status",
        "macro_liquidity_fed_balance_sheet_status",
        "macro_liquidity_reserve_balances_status",
        "macro_liquidity_korea_rate_status",
        "macro_liquidity_usd_krw_status",
        "macro_liquidity_investor_flow_status",
        "macro_liquidity_semiconductor_risk_appetite_status",
        "macro_liquidity_decision_score_enabled",
        "macro_liquidity_composite_score_enabled",
        "macro_liquidity_forecast_enabled",
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
    """Build existing chain, then attach current Macro/Liquidity Vertical v1."""

    snapshot = _build_structural_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=valuation_snapshot,
        investor_flow_pointer=investor_flow_pointer,
        semiconductor_history_pointer=semiconductor_history_pointer,
        kis_forward_pointer=kis_forward_pointer,
        kis_change_pointer=kis_change_pointer,
        historical_pb_pointer=historical_pb_pointer,
        semiconductor_structural_pointer=semiconductor_structural_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    explicit_pointer = macro_liquidity_pointer is not None
    pointer = (
        Path(macro_liquidity_pointer)
        if macro_liquidity_pointer is not None
        else DEFAULT_MACRO_LIQUIDITY_POINTER
    )
    if not pointer.is_file():
        if explicit_pointer:
            warning = "macro_liquidity_evidence_pointer_missing"
            return replace(
                snapshot,
                warnings=tuple(dict.fromkeys((*snapshot.warnings, warning))),
            )
        return snapshot

    try:
        evidence = build_macro_liquidity_decision_evidence(
            pointer,
            snapshot.macro_regime,
            snapshot.scorecards,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        warning = f"macro_liquidity_evidence_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, warning))),
        )

    scorecards = _attach_shared_macro_fields(
        snapshot.scorecards,
        evidence_id=evidence.evidence_id,
        coverage=evidence.coverage,
    )
    records = _sync_records(snapshot.decision_records, scorecards)
    report = append_macro_liquidity_report(snapshot.report_markdown, evidence)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"macro_liquidity_evidence:{evidence.evidence_id[:12]}",
            "macro_liquidity_non_scoring",
            "macro_liquidity_no_composite_net_liquidity_score",
            "macro_liquidity_current_endpoint_history_not_point_in_time_certified",
            "macro_liquidity_no_causal_or_forecast_claim",
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
