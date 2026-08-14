"""Rebase live P/B to the latest observable book equity before publication.

The base valuation layer intentionally uses annual flow references for PER, PSR,
and FCF yield. Book equity is a stock variable, so current P/B must instead use
the latest non-derived positive equity observation that was already available by
the evaluation date. This wrapper keeps the existing share-count and minimum-peer
guards, then corrects only the P/B equity basis and recomputes any eligible peer
score from the corrected multiples.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.valuation import (
    CompanySecurityMapping,
    ValuationDataClient,
    ValuationEvidenceSnapshot,
)
from alpha_cycle.intelligence.valuation_resilient import (
    build_valuation_evidence_snapshot as _build_resilient_valuation_snapshot,
)

_MINIMUM_PEER_UNIVERSE = 5
_PEER_METRICS = ("pe", "pb", "ps", "fcf_yield")


def _boolean_series(values: pd.Series) -> pd.Series:
    return values.map(
        lambda value: value
        if isinstance(value, bool)
        else str(value).strip().casefold() in {"true", "1", "yes"}
    )


def _latest_observable_equity(
    financial_history: pd.DataFrame,
    ticker: str,
    evaluation_date: date,
) -> Mapping[str, object] | None:
    required = {"ticker", "period_end", "available_date", "equity"}
    if financial_history.empty or not required.issubset(financial_history.columns):
        return None
    company = financial_history.loc[
        financial_history["ticker"].astype("string").str.zfill(6).eq(ticker)
    ].copy()
    if company.empty:
        return None
    if "derived" in company.columns:
        company = company.loc[~_boolean_series(company["derived"])].copy()
    company["period_end"] = pd.to_datetime(company["period_end"], errors="raise")
    company["available_date"] = pd.to_datetime(company["available_date"], errors="raise")
    company["equity"] = pd.to_numeric(company["equity"], errors="coerce")
    cutoff = pd.Timestamp(evaluation_date)
    company = company.loc[
        company["period_end"].le(cutoff)
        & company["available_date"].le(cutoff)
        & company["equity"].gt(0)
    ].copy()
    if company.empty:
        return None
    sort_columns = ["available_date", "period_end"]
    if "period_order" in company.columns:
        sort_columns.append("period_order")
    selected = company.sort_values(sort_columns, kind="stable").iloc[-1]
    return cast(Mapping[str, object], selected.to_dict())


def _recompute_peer_scores(metrics: pd.DataFrame) -> pd.DataFrame:
    result = metrics.copy()
    for column in ("market_cap_complete", "valuation_score", "valuation_status"):
        if column not in result.columns:
            result[column] = None
    for column in _PEER_METRICS:
        if column not in result.columns:
            result[column] = None

    comparable = result["market_cap_complete"].fillna(False).astype(bool) & result[
        list(_PEER_METRICS)
    ].notna().any(axis=1)
    peer_count = int(comparable.sum())
    result["valuation_peer_count"] = peer_count
    result["valuation_peer_minimum"] = _MINIMUM_PEER_UNIVERSE
    result.loc[comparable, "valuation_score"] = None
    if peer_count < _MINIMUM_PEER_UNIVERSE:
        result.loc[comparable, "valuation_status"] = "insufficient_peer_universe"
        return result

    eligible = result.loc[comparable].copy()
    ranks = pd.DataFrame(index=eligible.index)
    for metric in ("pe", "pb", "ps"):
        ranks[metric] = pd.to_numeric(eligible[metric], errors="coerce").rank(
            ascending=False,
            pct=True,
        )
    ranks["fcf_yield"] = pd.to_numeric(
        eligible["fcf_yield"],
        errors="coerce",
    ).rank(ascending=True, pct=True)
    percentile = ranks.mean(axis=1, skipna=True)
    raw_score = 1.0 + 4.0 * percentile
    shrinkage = peer_count / (peer_count + 3.0)
    scores = 3.0 + (raw_score - 3.0) * shrinkage
    result.loc[eligible.index, "valuation_score"] = scores
    result.loc[eligible.index, "valuation_status"] = "complete_peer_relative_scored"
    return result


def apply_latest_observable_equity_pb(
    snapshot: ValuationEvidenceSnapshot,
) -> ValuationEvidenceSnapshot:
    """Use the latest observable non-derived equity for P/B, never annual equity by default."""

    metrics = snapshot.valuation_metrics.copy()
    if metrics.empty or "ticker" not in metrics.columns:
        return snapshot
    metrics["ticker"] = metrics["ticker"].astype("string").str.zfill(6)
    for column in (
        "book_equity",
        "book_equity_reference_year",
        "book_equity_reference_period",
        "book_equity_period_end",
        "book_equity_available_date",
        "pb_equity_basis",
    ):
        if column not in metrics.columns:
            metrics[column] = None

    for index, raw in metrics.iterrows():
        ticker = str(raw["ticker"])
        reference = _latest_observable_equity(
            snapshot.financial_history,
            ticker,
            snapshot.evaluation_date,
        )
        market_cap = pd.to_numeric(
            pd.Series([raw.get("market_cap")]),
            errors="coerce",
        ).iloc[0]
        complete = bool(raw.get("market_cap_complete"))
        if reference is None:
            metrics.at[index, "pb"] = None
            continue
        equity_value = pd.to_numeric(
            pd.Series([reference.get("equity")]),
            errors="coerce",
        ).iloc[0]
        if pd.isna(equity_value) or float(equity_value) <= 0:
            metrics.at[index, "pb"] = None
            continue
        equity = float(equity_value)
        metrics.at[index, "book_equity"] = equity
        metrics.at[index, "book_equity_reference_year"] = str(
            reference.get("business_year", "")
        )
        metrics.at[index, "book_equity_reference_period"] = str(
            reference.get("period_label", "")
        )
        metrics.at[index, "book_equity_period_end"] = str(reference.get("period_end", ""))
        metrics.at[index, "book_equity_available_date"] = str(
            reference.get("available_date", "")
        )
        metrics.at[index, "pb_equity_basis"] = "latest_observable_non_derived_equity"
        if not complete or pd.isna(market_cap) or float(market_cap) <= 0:
            metrics.at[index, "pb"] = None
            continue
        metrics.at[index, "pb"] = float(market_cap) / equity

    metrics = _recompute_peer_scores(metrics)
    warning = (
        "P/B uses the latest observable non-derived OpenDART book equity; "
        "PER, PSR, and FCF yield retain annual flow references."
    )
    warnings = tuple(dict.fromkeys((*snapshot.warnings, warning)))
    return replace(snapshot, valuation_metrics=metrics, warnings=warnings)


def build_valuation_evidence_snapshot(
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    client: ValuationDataClient,
    *,
    history_years: int = 3,
    fs_div: str = "CFS",
    security_mappings: Mapping[str, CompanySecurityMapping] | None = None,
    now: datetime | None = None,
) -> ValuationEvidenceSnapshot:
    """Build guarded valuation evidence and publish P/B on the correct stock basis."""

    snapshot = _build_resilient_valuation_snapshot(
        research_snapshot,
        market_snapshot,
        client,
        history_years=history_years,
        fs_div=fs_div,
        security_mappings=security_mappings,
        now=now,
    )
    return apply_latest_observable_equity_pb(snapshot)


__all__ = [
    "apply_latest_observable_equity_pb",
    "build_valuation_evidence_snapshot",
]
