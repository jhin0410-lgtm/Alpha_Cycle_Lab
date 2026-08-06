"""Final evidence-coverage calibration for resilient investment decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.catalyst_evidence_policy import (
    apply_catalyst_report_policy,
    gate_catalyst_playbook,
)
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_calibration import (
    append_review_priority_audit,
    attach_priority_audit_to_records,
    calibrate_decision_scorecards,
    clarify_report_coverage,
    clarify_valuation_report,
)
from alpha_cycle.intelligence.decision_playbook import (
    append_execution_playbook_report,
    build_decision_records,
    enrich_scorecards_with_playbook,
)
from alpha_cycle.intelligence.decision_resilient import (
    build_investment_decision_snapshot as _build_resilient_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import (
    CompanyExposure,
    DecisionPolicy,
    build_report,
)
from alpha_cycle.intelligence.evidence_coverage_policy import (
    apply_evidence_coverage_policy,
    apply_evidence_report_policy,
)
from alpha_cycle.intelligence.report_financial_formatting import (
    apply_financial_report_formatting,
)
from alpha_cycle.intelligence.technical_evidence_policy import (
    apply_market_report_policy,
    gate_execution_playbook,
)
from alpha_cycle.intelligence.valuation import append_valuation_report


def _price_lookup(market_context: pd.DataFrame) -> dict[str, object]:
    raw = market_context.set_index("ticker")["last_price"].to_dict()
    return {str(key).zfill(6): value for key, value in raw.items()}


def _rebuild_scorecards(snapshot: InvestmentDecisionSnapshot) -> pd.DataFrame:
    adjusted = apply_evidence_coverage_policy(snapshot.scorecards, snapshot.policy)
    enriched = enrich_scorecards_with_playbook(
        adjusted,
        snapshot.financial_kpis,
        snapshot.catalysts,
        snapshot.market_context,
        evaluation_date=snapshot.evaluation_date,
    )
    calibrated = calibrate_decision_scorecards(
        enriched,
        snapshot.catalysts,
        evaluation_date=snapshot.evaluation_date,
    )
    market_gated = gate_execution_playbook(calibrated, snapshot.market_context)
    return gate_catalyst_playbook(market_gated)


def _rebuild_records(
    snapshot: InvestmentDecisionSnapshot,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    records = build_decision_records(
        scorecards,
        evaluation_date=snapshot.evaluation_date,
        price_lookup=_price_lookup(snapshot.market_context),
    )
    return attach_priority_audit_to_records(records, scorecards)


def _rebuild_report(
    snapshot: InvestmentDecisionSnapshot,
    scorecards: pd.DataFrame,
) -> str:
    report = build_report(
        snapshot.evaluation_date,
        scorecards,
        snapshot.financial_kpis,
        snapshot.catalysts,
        snapshot.macro_regime,
        snapshot.market_context,
        snapshot.warnings,
    )
    report = clarify_report_coverage(report)
    if snapshot.valuation_snapshot_id is not None:
        report = append_valuation_report(
            report,
            snapshot.valuation_metrics,
            snapshot.financial_history,
        )
        report = clarify_valuation_report(report, snapshot.valuation_metrics)
    report = apply_market_report_policy(report, snapshot.market_context)
    report = append_execution_playbook_report(report, scorecards)
    report = apply_catalyst_report_policy(report)
    report = append_review_priority_audit(report, scorecards)
    report = apply_evidence_report_policy(
        report,
        scorecards,
        snapshot.financial_kpis,
        snapshot.financial_history,
    )
    return apply_financial_report_formatting(report, snapshot.financial_kpis)


def build_investment_decision_snapshot(
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    *,
    valuation_snapshot: str | Path | None = None,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build a resilient snapshot, then neutral-impute missing score components."""

    snapshot = _build_resilient_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=valuation_snapshot,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    scorecards = _rebuild_scorecards(snapshot)
    records = _rebuild_records(snapshot, scorecards)
    report = _rebuild_report(snapshot, scorecards)
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=report,
    )


__all__ = ["build_investment_decision_snapshot"]
