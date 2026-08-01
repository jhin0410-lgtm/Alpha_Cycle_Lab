"""Fail-closed valuation guard for unresolved OpenDART issued-share rows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.intelligence.valuation import (
    CompanySecurityMapping,
    ValuationDataClient,
    ValuationEvidenceSnapshot,
    build_valuation_evidence_snapshot as _build_valuation_evidence_snapshot,
)

_UNRESOLVED_MARKER = "unresolved_missing_economic_share_count"
_ECONOMIC_CLASSES = frozenset({"common", "preferred", "other"})
_CLEARED_METRICS = (
    "market_cap",
    "pe",
    "pb",
    "ps",
    "fcf_yield",
    "earnings_yield",
    "valuation_score",
)


def _unresolved_share_rows(shares: pd.DataFrame) -> pd.DataFrame:
    if shares.empty or "normalization_warning" not in shares.columns:
        return shares.iloc[0:0].copy()
    warnings = shares["normalization_warning"].astype("string").fillna("")
    security_class = shares["security_class"].astype("string")
    return shares.loc[
        security_class.isin(_ECONOMIC_CLASSES)
        & warnings.str.contains(_UNRESOLVED_MARKER, regex=False)
    ].copy()


def _missing_names(value: object) -> set[str]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item) for item in parsed if str(item).strip()}


def _append_unresolved_security_rows(
    security_values: pd.DataFrame,
    unresolved: pd.DataFrame,
) -> pd.DataFrame:
    result = security_values.copy()
    result["share_count_complete"] = True
    if unresolved.empty:
        return result
    existing = {
        (str(row["ticker"]), str(row["security_name"]))
        for row in result.to_dict(orient="records")
    }
    additions: list[dict[str, object]] = []
    for raw in unresolved.to_dict(orient="records"):
        key = (str(raw["ticker"]), str(raw["security_name"]))
        if key in existing:
            mask = (
                result["ticker"].astype(str).eq(key[0])
                & result["security_name"].astype(str).eq(key[1])
            )
            result.loc[mask, "share_count_complete"] = False
            continue
        additions.append(
            {
                **raw,
                "symbol": None,
                "mapping_source": "unresolved_share_count",
                "price": None,
                "price_timestamp": None,
                "security_market_value": None,
                "priced": False,
                "share_count_complete": False,
            }
        )
    if additions:
        result = pd.concat([result, pd.DataFrame(additions)], ignore_index=True, sort=False)
    return result.sort_values(
        ["ticker", "security_class", "security_name"],
        kind="stable",
    ).reset_index(drop=True)


def apply_unresolved_share_count_guard(
    snapshot: ValuationEvidenceSnapshot,
) -> ValuationEvidenceSnapshot:
    """Clear valuation outputs whenever a potential economic share row is unresolved."""

    unresolved = _unresolved_share_rows(snapshot.shares)
    security_values = _append_unresolved_security_rows(
        snapshot.security_values,
        unresolved,
    )
    metrics = snapshot.valuation_metrics.copy()
    metrics["share_count_complete"] = True
    if unresolved.empty:
        return replace(snapshot, security_values=security_values, valuation_metrics=metrics)

    warnings = list(snapshot.warnings)
    for ticker_value, group in unresolved.groupby("ticker", sort=False):
        ticker = str(ticker_value)
        names = sorted(set(group["security_name"].astype(str)))
        metric_mask = metrics["ticker"].astype(str).eq(ticker)
        if not metric_mask.any():
            continue
        current_missing: set[str] = set()
        for value in metrics.loc[metric_mask, "missing_security_names"]:
            current_missing.update(_missing_names(value))
        current_missing.update(names)
        metrics.loc[metric_mask, "market_cap_complete"] = False
        metrics.loc[metric_mask, "share_count_complete"] = False
        metrics.loc[metric_mask, "missing_security_names"] = json.dumps(
            sorted(current_missing),
            ensure_ascii=False,
        )
        for column in _CLEARED_METRICS:
            metrics.loc[metric_mask, column] = None
        metrics.loc[metric_mask, "valuation_status"] = "incomplete_share_count"
        warnings.append(
            f"{ticker}: unresolved issued-share count for "
            f"{','.join(names)}; market cap and valuation multiples disabled"
        )

    return replace(
        snapshot,
        security_values=security_values,
        valuation_metrics=metrics,
        warnings=tuple(warnings),
    )


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
    """Build valuation evidence and fail closed on ambiguous issued-share rows."""

    snapshot = _build_valuation_evidence_snapshot(
        research_snapshot,
        market_snapshot,
        client,
        history_years=history_years,
        fs_div=fs_div,
        security_mappings=security_mappings,
        now=now,
    )
    return apply_unresolved_share_count_guard(snapshot)


__all__ = [
    "apply_unresolved_share_count_guard",
    "build_valuation_evidence_snapshot",
]
