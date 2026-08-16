"""Attach product-profitability calibration readiness after identifiability."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_product_profitability_calibrated import (
    build_investment_decision_snapshot as _build_profitability_identifiability_snapshot,
)
from alpha_cycle.intelligence.semiconductor_product_profitability_calibration import (
    ProductProfitabilityCalibrationMethod,
    ProductProfitabilityCalibrationReadiness,
    ProfitabilityCalibrationEvidenceInventory,
    assess_product_profitability_calibration_readiness,
)

_FIELDS = [
    "semiconductor_product_profitability_calibration_readiness_status",
    "semiconductor_product_profitability_method_registered",
    "semiconductor_product_profitability_method_documented",
    "semiconductor_product_profitability_identification_strategy",
    "semiconductor_product_profitability_method_version_frozen",
    "semiconductor_product_profitability_method_evidence_bound",
    "semiconductor_product_profitability_historical_validation_complete",
    "semiconductor_product_profitability_holdout_validation_complete",
    "semiconductor_product_profitability_prohibited_shortcut_used",
    "semiconductor_product_profitability_calibrated_model_input_ready",
    "semiconductor_product_profitability_missing_requirements",
]


def _defaults(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    result["semiconductor_product_profitability_calibration_readiness_status"] = pd.NA
    result["semiconductor_product_profitability_method_registered"] = False
    result["semiconductor_product_profitability_method_documented"] = False
    result["semiconductor_product_profitability_identification_strategy"] = pd.NA
    result["semiconductor_product_profitability_method_version_frozen"] = False
    result["semiconductor_product_profitability_method_evidence_bound"] = False
    result["semiconductor_product_profitability_historical_validation_complete"] = False
    result["semiconductor_product_profitability_holdout_validation_complete"] = False
    result["semiconductor_product_profitability_prohibited_shortcut_used"] = False
    result["semiconductor_product_profitability_calibrated_model_input_ready"] = False
    result["semiconductor_product_profitability_missing_requirements"] = pd.NA
    return result


def _attach(
    scorecards: pd.DataFrame,
    readiness: ProductProfitabilityCalibrationReadiness,
) -> pd.DataFrame:
    result = _defaults(scorecards)
    target = result["ticker"].eq("000660")
    if not target.any():
        return result
    if "semiconductor_product_profitability_calibration_required" not in result.columns:
        return result
    required = result.loc[
        target,
        "semiconductor_product_profitability_calibration_required",
    ].fillna(False)
    if not bool(required.all()):
        return result

    result.loc[
        target,
        "semiconductor_product_profitability_calibration_readiness_status",
    ] = readiness.status
    result.loc[target, "semiconductor_product_profitability_method_registered"] = (
        readiness.method_registered
    )
    result.loc[target, "semiconductor_product_profitability_method_documented"] = (
        readiness.method_documented
    )
    result.loc[target, "semiconductor_product_profitability_identification_strategy"] = (
        readiness.identification_strategy
    )
    result.loc[target, "semiconductor_product_profitability_method_version_frozen"] = (
        readiness.method_version_frozen
    )
    result.loc[target, "semiconductor_product_profitability_method_evidence_bound"] = (
        readiness.method_evidence_bound
    )
    result.loc[
        target,
        "semiconductor_product_profitability_historical_validation_complete",
    ] = readiness.historical_validation_complete
    result.loc[
        target,
        "semiconductor_product_profitability_holdout_validation_complete",
    ] = readiness.holdout_validation_complete
    result.loc[target, "semiconductor_product_profitability_prohibited_shortcut_used"] = (
        readiness.prohibited_shortcut_used
    )
    result.loc[target, "semiconductor_product_profitability_calibrated_model_input_ready"] = (
        readiness.model_input_ready
    )
    result.loc[target, "semiconductor_product_profitability_missing_requirements"] = "|".join(
        readiness.missing_requirements
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


def _default_readiness(scorecards: pd.DataFrame) -> ProductProfitabilityCalibrationReadiness:
    normalized = scorecards.copy()
    normalized["ticker"] = normalized["ticker"].astype("string").str.zfill(6)
    sk = normalized.loc[normalized["ticker"].eq("000660")]
    revenue_ready = False
    revenue_source_fact = False
    evidence_id = ""
    if not sk.empty:
        row = sk.iloc[0]
        revenue_ready = bool(
            row.get("semiconductor_direct_product_revenue_model_input_ready", False)
        )
        revenue_source_fact = bool(
            row.get("semiconductor_direct_product_revenue_source_fact", False)
        )
        raw_id = row.get("semiconductor_direct_product_revenue_evidence_id", "")
        evidence_id = "" if pd.isna(raw_id) else str(raw_id)

    inventory = ProfitabilityCalibrationEvidenceInventory(
        direct_product_revenue_evidence_id=evidence_id,
        direct_product_revenue_ready=revenue_ready,
        direct_product_profitability_periods=(),
        historical_product_revenue_periods=(),
        company_profitability_constraint_periods=(),
        cycle_driver_history_periods=(),
        holdout_periods=(),
        verified_evidence_ids=(),
        source_evidence_verified=revenue_source_fact,
    )
    return assess_product_profitability_calibration_readiness(inventory)


def _report(report: str, readiness: ProductProfitabilityCalibrationReadiness) -> str:
    missing = ", ".join(readiness.missing_requirements) or "none"
    return (
        report.rstrip()
        + "\n\n## SK hynix Product Profitability Calibration Readiness\n\n"
        + f"- status: `{readiness.status}`\n"
        + f"- identification strategy: `{readiness.identification_strategy}`\n"
        + f"- method documented: `{readiness.method_documented}`\n"
        + f"- method version frozen: `{readiness.method_version_frozen}`\n"
        + f"- evidence bound: `{readiness.method_evidence_bound}`\n"
        + f"- historical validation complete: `{readiness.historical_validation_complete}`\n"
        + f"- holdout validation complete: `{readiness.holdout_validation_complete}`\n"
        + f"- prohibited shortcut used: `{readiness.prohibited_shortcut_used}`\n"
        + f"- calibrated profitability model input ready: `{readiness.model_input_ready}`\n"
        + f"- missing requirements: `{missing}`\n"
        + "- calibrated profitability remains an assumption, not a direct source fact.\n"
        + "- numeric forecast/fair value/target price/decision score remain closed here.\n"
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
    profitability_calibration_inventory: ProfitabilityCalibrationEvidenceInventory | None = None,
    profitability_calibration_method: ProductProfitabilityCalibrationMethod | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build through identifiability, then assess the calibration route fail-closed."""

    snapshot = _build_profitability_identifiability_snapshot(
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
    readiness = (
        _default_readiness(snapshot.scorecards)
        if profitability_calibration_inventory is None
        else assess_product_profitability_calibration_readiness(
            profitability_calibration_inventory,
            profitability_calibration_method,
        )
    )
    scorecards = _attach(snapshot.scorecards, readiness)
    records = _sync_records(snapshot.decision_records, scorecards)
    warnings = list(snapshot.warnings)
    if readiness.direct_product_revenue_ready:
        warnings.append(f"semiconductor_product_profitability_calibration:{readiness.status}")
        warnings.extend(
            f"semiconductor_product_profitability_missing:{item}"
            for item in readiness.missing_requirements
        )
    if readiness.prohibited_shortcut_used:
        warnings.append("semiconductor_product_profitability_prohibited_shortcut")
    if readiness.model_input_ready:
        warnings.append("semiconductor_product_profitability_calibrated_model_input_ready")

    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=_report(snapshot.report_markdown, readiness),
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["_attach", "_defaults", "build_investment_decision_snapshot"]
