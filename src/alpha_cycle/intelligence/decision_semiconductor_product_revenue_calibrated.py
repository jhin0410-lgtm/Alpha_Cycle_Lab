"""Attach verified SK hynix direct product-revenue source facts to decision snapshots.

This layer sits after direct/company accounting bridges and before any derived revenue
allocation. It surfaces source facts and independent IR cross-check readiness without
promoting revenue evidence into product profitability, a numeric forecast, or a score.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.decision_semiconductor_accounting_identity_calibrated import (
    build_investment_decision_snapshot as _build_accounting_identity_snapshot,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_assignment_certification import (
    DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_official_ir_q2_product_assignment_certification_verifier import (  # noqa: E501
    load_q2_product_assignment_certification,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification import (
    DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER,
)
from alpha_cycle.intelligence.sk_hynix_opendart_q2_product_revenue_certification_verifier import (
    load_periodic_product_revenue_certification,
)
from alpha_cycle.intelligence.sk_hynix_q2_product_revenue_ir_crosscheck import (
    build_product_revenue_ir_crosscheck,
)

_FIELDS = [
    "semiconductor_direct_product_revenue_available",
    "semiconductor_direct_product_revenue_evidence_id",
    "semiconductor_direct_product_revenue_dram_krw_million",
    "semiconductor_direct_product_revenue_nand_krw_million",
    "semiconductor_direct_product_revenue_other_krw_million",
    "semiconductor_direct_product_revenue_total_krw_million",
    "semiconductor_direct_product_revenue_reconciliation_certified",
    "semiconductor_direct_product_revenue_ir_crosscheck_certified",
    "semiconductor_direct_product_revenue_model_input_ready",
    "semiconductor_direct_product_revenue_source_fact",
    "semiconductor_direct_product_revenue_profitability_certified",
    "semiconductor_direct_product_revenue_full_baseline_certified",
    "semiconductor_direct_product_revenue_allocation_resolver_registered",
    "semiconductor_direct_product_revenue_numeric_forecast_enabled",
    "semiconductor_direct_product_revenue_decision_score_enabled",
]


def _defaults(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    result["semiconductor_direct_product_revenue_available"] = False
    result["semiconductor_direct_product_revenue_evidence_id"] = pd.NA
    result["semiconductor_direct_product_revenue_dram_krw_million"] = pd.NA
    result["semiconductor_direct_product_revenue_nand_krw_million"] = pd.NA
    result["semiconductor_direct_product_revenue_other_krw_million"] = pd.NA
    result["semiconductor_direct_product_revenue_total_krw_million"] = pd.NA
    result["semiconductor_direct_product_revenue_reconciliation_certified"] = False
    result["semiconductor_direct_product_revenue_ir_crosscheck_certified"] = False
    result["semiconductor_direct_product_revenue_model_input_ready"] = False
    result["semiconductor_direct_product_revenue_source_fact"] = False
    result["semiconductor_direct_product_revenue_profitability_certified"] = False
    result["semiconductor_direct_product_revenue_full_baseline_certified"] = False
    result["semiconductor_direct_product_revenue_allocation_resolver_registered"] = False
    result["semiconductor_direct_product_revenue_numeric_forecast_enabled"] = False
    result["semiconductor_direct_product_revenue_decision_score_enabled"] = False
    return result


def _attach(
    scorecards: pd.DataFrame,
    *,
    evidence_id: str,
    dram_revenue: float,
    nand_revenue: float,
    other_revenue: float,
    total_revenue: float,
    reconciliation_certified: bool,
    ir_crosscheck_certified: bool,
) -> pd.DataFrame:
    result = _defaults(scorecards)
    target = result["ticker"].eq("000660")
    result.loc[target, "semiconductor_direct_product_revenue_available"] = True
    result.loc[target, "semiconductor_direct_product_revenue_evidence_id"] = evidence_id
    result.loc[target, "semiconductor_direct_product_revenue_dram_krw_million"] = (
        dram_revenue
    )
    result.loc[target, "semiconductor_direct_product_revenue_nand_krw_million"] = (
        nand_revenue
    )
    result.loc[target, "semiconductor_direct_product_revenue_other_krw_million"] = (
        other_revenue
    )
    result.loc[target, "semiconductor_direct_product_revenue_total_krw_million"] = (
        total_revenue
    )
    result.loc[
        target,
        "semiconductor_direct_product_revenue_reconciliation_certified",
    ] = reconciliation_certified
    result.loc[
        target,
        "semiconductor_direct_product_revenue_ir_crosscheck_certified",
    ] = ir_crosscheck_certified
    result.loc[target, "semiconductor_direct_product_revenue_model_input_ready"] = (
        reconciliation_certified and ir_crosscheck_certified
    )
    result.loc[target, "semiconductor_direct_product_revenue_source_fact"] = True
    return result


def _sync_records(records: pd.DataFrame, scorecards: pd.DataFrame) -> pd.DataFrame:
    fields = ["ticker", *_FIELDS]
    supplement = scorecards.loc[:, [item for item in fields if item in scorecards.columns]].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [item for item in _FIELDS if item in result.columns]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _unavailable_report(report: str, reason: str) -> str:
    return (
        report.rstrip()
        + "\n\n## SK hynix Direct Product Revenue (사용 불가)\n\n"
        + f"- 상태: `{reason}`\n"
        + "- DRAM/NAND/Other 금액을 잔여값이나 차트 높이로 추정하지 않습니다.\n"
        + "- 기존 accounting identity와 다른 source-fact evidence는 그대로 유지합니다.\n"
        + "- product profitability, numeric forecast, fair value, decision score는 열지 않습니다.\n"
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


def _report(
    report: str,
    *,
    evidence_id: str,
    dram_revenue: float,
    nand_revenue: float,
    other_revenue: float,
    total_revenue: float,
    crosscheck_certified: bool,
) -> str:
    return (
        report.rstrip()
        + "\n\n## SK hynix Direct Product Revenue\n\n"
        + f"- evidence: `{evidence_id}`\n"
        + f"- DRAM revenue: `{dram_revenue:,.0f} KRW million`\n"
        + f"- NAND revenue: `{nand_revenue:,.0f} KRW million`\n"
        + f"- Other revenue: `{other_revenue:,.0f} KRW million`\n"
        + f"- Reported product revenue total: `{total_revenue:,.0f} KRW million`\n"
        + "- direct source reconciliation: `certified`\n"
        + f"- independent official-IR rounded-share cross-check: `{crosscheck_certified}`\n"
        + "- source fact: `true`; allocation resolver: `false`\n"
        + "- product profitability/full baseline/numeric forecast/decision score: `false`\n"
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
    """Build through accounting identities, then attach direct product-revenue evidence."""

    snapshot = _build_accounting_identity_snapshot(
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
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    pointer = (
        Path(semiconductor_product_revenue_pointer)
        if semiconductor_product_revenue_pointer is not None
        else DEFAULT_PERIODIC_PRODUCT_REVENUE_POINTER
    )
    if not pointer.is_file():
        return _replace_unavailable(
            snapshot,
            reason="semiconductor_direct_product_revenue_evidence_missing",
        )
    try:
        evidence = load_periodic_product_revenue_certification(
            pointer,
            evaluation_date=snapshot.evaluation_date,
        )
    except (OSError, TypeError, ValueError) as exc:
        return _replace_unavailable(
            snapshot,
            reason=f"semiconductor_direct_product_revenue_unavailable:{type(exc).__name__}",
        )

    ir_pointer = (
        Path(skhynix_ir_assignment_pointer)
        if skhynix_ir_assignment_pointer is not None
        else DEFAULT_Q2_PRODUCT_ASSIGNMENT_POINTER
    )
    crosscheck_certified = False
    crosscheck_reason = "semiconductor_direct_product_revenue_ir_crosscheck_missing"
    if ir_pointer.is_file():
        try:
            assignment = load_q2_product_assignment_certification(
                ir_pointer,
                evaluation_date=snapshot.evaluation_date,
            )
            crosscheck = build_product_revenue_ir_crosscheck(evidence, assignment)
            crosscheck_certified = crosscheck.crosscheck_certified
            crosscheck_reason = (
                "semiconductor_direct_product_revenue_ir_crosscheck_certified"
                if crosscheck_certified
                else "semiconductor_direct_product_revenue_ir_crosscheck_failed"
            )
        except (OSError, TypeError, ValueError):
            crosscheck_reason = "semiconductor_direct_product_revenue_ir_crosscheck_unavailable"

    metrics = evidence.metrics
    scorecards = _attach(
        snapshot.scorecards,
        evidence_id=evidence.evidence_id,
        dram_revenue=metrics.dram_total,
        nand_revenue=metrics.nand_and_solutions,
        other_revenue=metrics.other_products_services,
        total_revenue=metrics.reported_company_revenue,
        reconciliation_certified=evidence.company_revenue_reconciliation_certified,
        ir_crosscheck_certified=crosscheck_certified,
    )
    records = _sync_records(snapshot.decision_records, scorecards)
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_direct_product_revenue:{evidence.evidence_id[:12]}",
            crosscheck_reason,
            "semiconductor_direct_product_revenue_source_fact",
            "semiconductor_direct_product_revenue_allocation_resolver_not_required",
            "semiconductor_direct_product_revenue_profitability_blocked",
            "semiconductor_direct_product_revenue_numeric_forecast_disabled",
            "semiconductor_direct_product_revenue_non_scoring",
        ]
    )
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=_report(
            snapshot.report_markdown,
            evidence_id=evidence.evidence_id,
            dram_revenue=metrics.dram_total,
            nand_revenue=metrics.nand_and_solutions,
            other_revenue=metrics.other_products_services,
            total_revenue=metrics.reported_company_revenue,
            crosscheck_certified=crosscheck_certified,
        ),
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["_attach", "_defaults", "build_investment_decision_snapshot"]
