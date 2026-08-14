"""Attach industry-specific vertical research coverage after the calibrated chain.

The existing decision snapshot remains authoritative for all scores and states.
This final wrapper adds only non-scoring research-completeness metadata for the
semiconductor vertical.  Other industries will use the same contract with their
own evidence adapters rather than inheriting semiconductor assumptions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_historical_pb_calibrated import (
    build_investment_decision_snapshot as _build_historical_pb_snapshot,
)
from alpha_cycle.intelligence.decision_scoring import CompanyExposure, DecisionPolicy
from alpha_cycle.intelligence.semiconductor_vertical import (
    append_semiconductor_vertical_report,
    attach_semiconductor_vertical_to_scorecards,
    build_semiconductor_vertical_assessment,
    sync_record_semiconductor_vertical_fields,
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
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy | None = None,
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build existing decisions, then publish semiconductor vertical coverage."""

    snapshot = _build_historical_pb_snapshot(
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
    try:
        assessment = build_semiconductor_vertical_assessment(
            snapshot.scorecards,
            snapshot.financial_history,
            snapshot.catalysts,
            snapshot.macro_regime,
            evaluation_date=snapshot.evaluation_date,
        )
    except (TypeError, ValueError) as exc:
        warning = f"semiconductor_vertical_unavailable:{type(exc).__name__}"
        return replace(
            snapshot,
            warnings=tuple(dict.fromkeys((*snapshot.warnings, warning))),
        )

    scorecards = attach_semiconductor_vertical_to_scorecards(
        snapshot.scorecards,
        assessment,
    )
    records = sync_record_semiconductor_vertical_fields(
        snapshot.decision_records,
        scorecards,
    )
    report = append_semiconductor_vertical_report(
        snapshot.report_markdown,
        assessment,
    )
    warnings = list(snapshot.warnings)
    warnings.extend(
        [
            f"semiconductor_vertical_assessment:{assessment.assessment_id[:12]}",
            "semiconductor_vertical_non_scoring",
            "sector_vertical_missing_evidence_not_zero_scored",
        ]
    )
    for coverage in assessment.coverages:
        warnings.append(
            "semiconductor_vertical_coverage:"
            f"{coverage.ticker}:{coverage.required_available}/{coverage.required_total}:"
            f"{coverage.readiness_status}"
        )
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=records,
        report_markdown=report,
        warnings=tuple(dict.fromkeys(warnings)),
    )


__all__ = ["build_investment_decision_snapshot"]
