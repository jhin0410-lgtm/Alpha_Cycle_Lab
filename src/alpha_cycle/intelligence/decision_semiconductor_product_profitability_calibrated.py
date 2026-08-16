"""Attach SK hynix product-profitability identifiability after direct revenue evidence.

The prior layer may certify DRAM/NAND/Other revenue as direct source facts. That does
not identify DRAM or NAND gross profit/margin. This layer makes the remaining gap
explicit without estimating it and without changing forecast, valuation, or score gates.
"""

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
from alpha_cycle.intelligence.semiconductor_product_profitability_identifiability import (
    assess_product_profitability_identifiability,
)

_FIELDS = [
    "semiconductor_product_profitability_identifiable_from_source_facts",
    "semiconductor_product_profitability_calibration_required",
    "semiconductor_product_profitability_calibration_status",
    "semiconductor_product_profitability_direct_metrics_required",
    "semiconductor_product_profitability_direct_metrics_available",
    "semiconductor_product_profitability_revenue_share_source_fact_allowed",
    "semiconductor_product_profitability_residual_source_fact_allowed",
    "semiconductor_product_profitability_peer_margin_source_fact_allowed",
    "semiconductor_product_profitability_certified",
    "semiconductor_product_profitability_numeric_forecast_enabled",
    "semiconductor_product_profitability_decision_score_enabled",
]
_REQUIRED_SKHYNIX_PROFITABILITY_BLOCKS = ("dram_total", "nand_and_solutions")
_REVENUE_READY_FIELD = "semiconductor_direct_product_revenue_model_input_ready"


def _defaults(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    result["semiconductor_product_profitability_identifiable_from_source_facts"] = False
    result["semiconductor_product_profitability_calibration_required"] = False
    result["semiconductor_product_profitability_calibration_status"] = pd.NA
    result["semiconductor_product_profitability_direct_metrics_required"] = pd.NA
    result["semiconductor_product_profitability_direct_metrics_available"] = pd.NA
    result["semiconductor_product_profitability_revenue_share_source_fact_allowed"] = False
    result["semiconductor_product_profitability_residual_source_fact_allowed"] = False
    result["semiconductor_product_profitability_peer_margin_source_fact_allowed"] = False
    result["semiconductor_product_profitability_certified"] = False
    result["semiconductor_product_profitability_numeric_forecast_enabled"] = False
    result["semiconductor_product_profitability_decision_score_enabled"] = False
    return result


def _attach(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = _defaults(scorecards)
    target = result["ticker"].eq("000660")
    if not target.any() or _REVENUE_READY_FIELD not in result.columns:
        return result

    revenue_ready = result.loc[target, _REVENUE_READY_FIELD].fillna(False)
    if not bool(revenue_ready.all()):
        return result

    assessment = assess_product_profitability_identifiability(
        "000660",
        required_product_blocks=_REQUIRED_SKHYNIX_PROFITABILITY_BLOCKS,
        directly_disclosed_product_profitability_blocks=(),
    )
    result.loc[
        target,
        "semiconductor_product_profitability_identifiable_from_source_facts",
    ] = assessment.identifiable_from_source_facts
    result.loc[target, "semiconductor_product_profitability_calibration_required"] = (
        assessment.calibrated_assumption_required
    )
    result.loc[target, "semiconductor_product_profitability_calibration_status"] = (
        assessment.calibration_status
    )
    result.loc[target, "semiconductor_product_profitability_direct_metrics_required"] = (
        assessment.direct_product_profitability_metrics_required
    )
    result.loc[target, "semiconductor_product_profitability_direct_metrics_available"] = (
        assessment.direct_product_profitability_metrics_available
    )
    result.loc[
        target,
        "semiconductor_product_profitability_revenue_share_source_fact_allowed",
    ] = assessment.revenue_share_profit_allocation_source_fact_allowed
    result.loc[target, "semiconductor_product_profitability_residual_source_fact_allowed"] = (
        assessment.residual_profit_allocation_source_fact_allowed
    )
    result.loc[
        target,
        "semiconductor_product_profitability_peer_margin_source_fact_allowed",
    ] = assessment.peer_margin_substitution_source_fact_allowed
    result.loc[target, "semiconductor_product_profitability_certified"] = (
        assessment.product_profitability_certified
    )
    return result


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = ["ticker", *_FIELDS]
    available = [column for column in fields if column in scorecards.columns]
    supplement = scorecards.loc[:, available].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [column for column in _FIELDS if column in result.columns]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _report(report: str, scorecards: pd.DataFrame) -> str:
    sk = scorecards.loc[scorecards["ticker"].eq("000660")]
    if sk.empty:
        return report
    row = sk.iloc[0]
    if pd.isna(row["semiconductor_product_profitability_calibration_status"]):
        status = "direct_product_revenue_not_ready"
        required = "n/a"
        available = "n/a"
        calibration_required = False
    else:
        status = str(row["semiconductor_product_profitability_calibration_status"])
        required = str(int(row["semiconductor_product_profitability_direct_metrics_required"]))
        available = str(int(row["semiconductor_product_profitability_direct_metrics_available"]))
        calibration_required = bool(
            row["semiconductor_product_profitability_calibration_required"]
        )
    return (
        report.rstrip()
        + "\n\n## SK hynix Product Profitability Identifiability\n\n"
        + f"- status: `{status}`\n"
        + f"- direct profitability metrics: `{available}/{required}`\n"
        + f"- calibrated assumption route required: `{calibration_required}`\n"
        + "- revenue-share profit allocation as source fact: `false`\n"
        + "- residual profit allocation as source fact: `false`\n"
        + "- peer margin substitution as source fact: `false`\n"
        + "- product profitability/numeric forecast/decision score: `false`\n"
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
    semiconductor_product_revenue_pointer: str | Path | None = None,
    skhynix_ir_assignment_pointer: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through direct product revenue, then expose profitability identifiability."""

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
        semiconductor_product_revenue_pointer=semiconductor_product_revenue_pointer,
        skhynix_ir_assignment_pointer=skhynix_ir_assignment_pointer,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    scorecards = _attach(snapshot.scorecards)
    records = _sync_records(snapshot.decision_records, scorecards)
    warnings = list(snapshot.warnings)
    sk = scorecards.loc[scorecards["ticker"].eq("000660")]
    if not sk.empty and bool(
        sk.iloc[0]["semiconductor_product_profitability_calibration_required"]
    ):
        warnings.extend(
            [
                "semiconductor_product_profitability_not_identifiable_from_source_facts",
                "semiconductor_product_profitability_calibration_required",
                "semiconductor_product_profitability_revenue_share_allocation_forbidden",
                "semiconductor_product_profitability_residual_allocation_forbidden",
                "semiconductor_product_profitability_peer_margin_substitution_forbidden",
            ]
        )
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=_report(snapshot.report_markdown, scorecards),
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["_attach", "_defaults", "build_investment_decision_snapshot"]
