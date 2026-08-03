"""Resilient decision integration for partially available valuation evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.decision import (
    InvestmentDecisionSnapshot,
    _load_valuation_snapshot,
)
from alpha_cycle.intelligence.decision import (
    build_investment_decision_snapshot as _build_investment_decision_snapshot,
)
from alpha_cycle.intelligence.decision_calibration import (
    calibrate_decision_scorecards,
    clarify_report_coverage,
)
from alpha_cycle.intelligence.decision_playbook import (
    append_execution_playbook_report,
    build_decision_records,
    enrich_scorecards_with_playbook,
)
from alpha_cycle.intelligence.decision_scoring import (
    CompanyExposure,
    DecisionPolicy,
    build_report,
)
from alpha_cycle.intelligence.valuation import (
    append_valuation_report,
    apply_valuation_to_scorecards,
)

_REQUIRED_PLACEHOLDER_COLUMNS = (
    "ticker",
    "market_cap_complete",
    "share_count_complete",
    "missing_security_names",
    "market_cap_proxy",
    "market_cap",
    "pe",
    "pb",
    "ps",
    "fcf_yield",
    "earnings_yield",
    "valuation_score",
    "valuation_status",
)


def align_valuation_metrics_to_decisions(
    valuation_metrics: pd.DataFrame,
    decision_tickers: set[str],
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Pad missing decision companies while rejecting unrelated valuation companies."""

    metrics = valuation_metrics.copy()
    if "ticker" not in metrics.columns:
        raise ValueError("Valuation metrics must contain ticker")
    metrics["ticker"] = metrics["ticker"].astype("string").str.zfill(6)
    if metrics["ticker"].duplicated().any():
        raise ValueError("Valuation metrics contain duplicate tickers")

    valuation_tickers = set(metrics["ticker"].astype(str))
    extras = sorted(valuation_tickers - decision_tickers)
    if extras:
        raise ValueError(
            "Valuation snapshot contains companies outside the decision universe: "
            f"{extras}"
        )

    for column in _REQUIRED_PLACEHOLDER_COLUMNS:
        if column not in metrics.columns:
            metrics[column] = None

    missing = tuple(sorted(decision_tickers - valuation_tickers))
    additions: list[dict[str, object]] = []
    for ticker in missing:
        row: dict[str, object] = {column: None for column in metrics.columns}
        row.update(
            {
                "ticker": ticker,
                "market_cap_complete": False,
                "share_count_complete": False,
                "missing_security_names": json.dumps([], ensure_ascii=False),
                "market_cap_proxy": None,
                "market_cap": None,
                "pe": None,
                "pb": None,
                "ps": None,
                "fcf_yield": None,
                "earnings_yield": None,
                "valuation_score": None,
                "valuation_status": "valuation_not_available",
            }
        )
        additions.append(row)
    if additions:
        metrics = pd.concat([metrics, pd.DataFrame(additions)], ignore_index=True, sort=False)

    return (
        metrics.sort_values("ticker", kind="stable").reset_index(drop=True),
        missing,
    )


def _price_lookup(market_context: pd.DataFrame) -> dict[str, object]:
    raw = market_context.set_index("ticker")["last_price"].to_dict()
    return {str(key).zfill(6): value for key, value in raw.items()}


def _calibrated_playbook_scorecards(
    snapshot: InvestmentDecisionSnapshot,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    enriched = enrich_scorecards_with_playbook(
        scorecards,
        snapshot.financial_kpis,
        snapshot.catalysts,
        snapshot.market_context,
        evaluation_date=snapshot.evaluation_date,
    )
    return calibrate_decision_scorecards(
        enriched,
        snapshot.catalysts,
        evaluation_date=snapshot.evaluation_date,
    )


def _attach_execution_playbook(
    snapshot: InvestmentDecisionSnapshot,
) -> InvestmentDecisionSnapshot:
    scorecards = _calibrated_playbook_scorecards(snapshot, snapshot.scorecards)
    decision_records = build_decision_records(
        scorecards,
        evaluation_date=snapshot.evaluation_date,
        price_lookup=_price_lookup(snapshot.market_context),
    )
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
    report = append_execution_playbook_report(report, scorecards)
    return replace(
        snapshot,
        scorecards=scorecards,
        decision_records=decision_records,
        report_markdown=report,
    )


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
    """Build decisions while preserving unavailable valuation as explicit evidence."""

    base = _build_investment_decision_snapshot(
        research_snapshot,
        market_snapshot,
        valuation_snapshot=None,
        benchmark=benchmark,
        exposures=exposures,
        policy=policy,
        now=now,
    )
    if valuation_snapshot is None:
        return _attach_execution_playbook(base)

    valuation_id, valuation_metrics, financial_history, valuation_warnings = (
        _load_valuation_snapshot(
            valuation_snapshot,
            research_snapshot_id=base.research_snapshot_id,
            market_snapshot_id=base.market_snapshot_id,
            evaluation_date=base.evaluation_date,
        )
    )
    decision_tickers = set(base.scorecards["ticker"].astype(str))
    valuation_metrics, missing = align_valuation_metrics_to_decisions(
        valuation_metrics,
        decision_tickers,
    )
    decision_policy = policy or base.policy
    scorecards = apply_valuation_to_scorecards(
        base.scorecards,
        valuation_metrics,
        decision_policy,
    )
    scorecards = _calibrated_playbook_scorecards(base, scorecards)

    decision_records = build_decision_records(
        scorecards,
        evaluation_date=base.evaluation_date,
        price_lookup=_price_lookup(base.market_context),
    )

    warnings = [
        item
        for item in base.warnings
        if item != "valuation_and_consensus_not_available"
    ]
    warnings.extend(valuation_warnings)
    if missing:
        warnings.append(
            "valuation_missing_for_decision_tickers:" + ",".join(missing)
        )
    if "consensus_not_available" not in warnings:
        warnings.append("consensus_not_available")

    report = build_report(
        base.evaluation_date,
        scorecards,
        base.financial_kpis,
        base.catalysts,
        base.macro_regime,
        base.market_context,
        tuple(warnings),
    )
    report = clarify_report_coverage(report)
    report = append_valuation_report(report, valuation_metrics, financial_history)
    report = append_execution_playbook_report(report, scorecards)

    return replace(
        base,
        valuation_snapshot_id=valuation_id,
        valuation_metrics=valuation_metrics,
        financial_history=financial_history,
        scorecards=scorecards,
        decision_records=decision_records,
        report_markdown=report,
        warnings=tuple(warnings),
    )


__all__ = [
    "align_valuation_metrics_to_decisions",
    "build_investment_decision_snapshot",
]
