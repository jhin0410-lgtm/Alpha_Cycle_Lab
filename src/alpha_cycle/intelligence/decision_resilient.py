"""Resilient decision integration for partially available valuation evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.catalyst_evidence_policy import (
    apply_catalyst_evidence_policy,
    apply_catalyst_report_policy,
    gate_catalyst_playbook,
)
from alpha_cycle.intelligence.decision import (
    InvestmentDecisionSnapshot,
    _load_valuation_snapshot,
)
from alpha_cycle.intelligence.decision import (
    build_investment_decision_snapshot as _build_investment_decision_snapshot,
)
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
from alpha_cycle.intelligence.decision_scoring import (
    CompanyExposure,
    DecisionPolicy,
    build_report,
)
from alpha_cycle.intelligence.disclosure_provenance import (
    normalize_disclosure_tables,
)
from alpha_cycle.intelligence.technical_evidence_policy import (
    apply_market_evidence_policy,
    apply_market_report_policy,
    gate_execution_playbook,
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
_VALUATION_CONTEXT_COLUMNS = (
    "valuation_peer_count",
    "valuation_peer_minimum",
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


def _normalize_disclosure_provenance(
    snapshot: InvestmentDecisionSnapshot,
) -> InvestmentDecisionSnapshot:
    events, catalysts, summary, provenance_warnings = normalize_disclosure_tables(
        snapshot.disclosure_events,
        snapshot.catalysts,
        snapshot.disclosure_summary,
    )
    warnings = tuple(dict.fromkeys([*snapshot.warnings, *provenance_warnings]))
    return replace(
        snapshot,
        disclosure_events=events,
        catalysts=catalysts,
        disclosure_summary=summary,
        warnings=warnings,
    )


def _load_disclosure_document_evidence(
    research_snapshot: str | Path,
) -> Mapping[str, object]:
    root = Path(research_snapshot)
    raw_path = root / "raw_opendart.json" if root.is_dir() else root.parent / "raw_opendart.json"
    if not raw_path.is_file():
        return {}
    payload: object = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("raw_opendart.json must contain an object")
    bundle = payload.get("_disclosure_document_evidence")
    if bundle is None:
        return {}
    if not isinstance(bundle, dict):
        raise ValueError("OpenDART disclosure document evidence must be an object")
    if bundle.get("provider") != "opendart" or bundle.get("endpoint") != "/api/document.xml":
        raise ValueError("Unexpected OpenDART disclosure document evidence contract")
    documents = bundle.get("documents")
    if not isinstance(documents, dict):
        raise ValueError("OpenDART disclosure document evidence has no documents object")
    normalized: dict[str, object] = {}
    for key, value in documents.items():
        receipt = str(key).strip()
        if len(receipt) != 14 or not receipt.isdigit():
            raise ValueError("OpenDART document evidence has an invalid receipt number")
        if not isinstance(value, dict):
            raise ValueError("OpenDART document evidence record must be an object")
        if str(value.get("rcept_no", "")).strip() != receipt:
            raise ValueError("OpenDART document evidence receipt binding mismatch")
        normalized[receipt] = cast(Mapping[str, object], value)
    return normalized


def _attach_valuation_context(
    scorecards: pd.DataFrame,
    valuation_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Carry peer-universe diagnostics into decision and playbook outputs."""

    available = [
        column
        for column in _VALUATION_CONTEXT_COLUMNS
        if column in valuation_metrics.columns
    ]
    if not available:
        return scorecards.copy()
    context = valuation_metrics.loc[:, ["ticker", *available]].copy()
    context["ticker"] = context["ticker"].astype("string").str.zfill(6)
    if context["ticker"].duplicated().any():
        raise ValueError("Valuation context contains duplicate tickers")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    return result.merge(
        context,
        on="ticker",
        how="left",
        validate="one_to_one",
    )


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
    calibrated = calibrate_decision_scorecards(
        enriched,
        snapshot.catalysts,
        evaluation_date=snapshot.evaluation_date,
    )
    market_gated = gate_execution_playbook(calibrated, snapshot.market_context)
    return gate_catalyst_playbook(market_gated)


def _decision_records_with_audit(
    scorecards: pd.DataFrame,
    *,
    evaluation_date: date,
    price_lookup: Mapping[str, object],
) -> pd.DataFrame:
    records = build_decision_records(
        scorecards,
        evaluation_date=evaluation_date,
        price_lookup=price_lookup,
    )
    return attach_priority_audit_to_records(records, scorecards)


def _attach_execution_playbook(
    snapshot: InvestmentDecisionSnapshot,
) -> InvestmentDecisionSnapshot:
    source_scorecards = snapshot.scorecards
    if snapshot.valuation_snapshot_id is not None:
        source_scorecards = _attach_valuation_context(
            source_scorecards,
            snapshot.valuation_metrics,
        )
    scorecards = _calibrated_playbook_scorecards(snapshot, source_scorecards)
    decision_records = _decision_records_with_audit(
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
        report = clarify_valuation_report(report, snapshot.valuation_metrics)
    report = apply_market_report_policy(report, snapshot.market_context)
    report = append_execution_playbook_report(report, scorecards)
    report = apply_catalyst_report_policy(report)
    report = append_review_priority_audit(report, scorecards)
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
    decision_policy = policy or base.policy
    base = apply_market_evidence_policy(
        base,
        market_snapshot=market_snapshot,
        exposures=dict(exposures or {}),
        policy=decision_policy,
    )
    base = _normalize_disclosure_provenance(base)
    base = apply_catalyst_evidence_policy(
        base,
        policy=decision_policy,
        document_evidence=_load_disclosure_document_evidence(research_snapshot),
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
    scorecards = apply_valuation_to_scorecards(
        base.scorecards,
        valuation_metrics,
        decision_policy,
    )
    scorecards = _attach_valuation_context(scorecards, valuation_metrics)
    scorecards = _calibrated_playbook_scorecards(base, scorecards)

    decision_records = _decision_records_with_audit(
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
    warnings = list(dict.fromkeys(warnings))

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
    report = clarify_valuation_report(report, valuation_metrics)
    report = apply_market_report_policy(report, base.market_context)
    report = append_execution_playbook_report(report, scorecards)
    report = apply_catalyst_report_policy(report)
    report = append_review_priority_audit(report, scorecards)

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
