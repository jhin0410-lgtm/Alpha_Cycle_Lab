"""Resilient historical P/B wrapper matching live OpenDART share selection.

The period-history artifact intentionally preserves every visible OpenDART
stock-total report, including aggregate/note-only or otherwise unusable periods.
For valuation reconstruction, however, the newest *usable* visible report must
be selected rather than allowing an unusable newer report to suppress all later
observations. This module filters only the calculation input; source artifacts
remain immutable and excluded periods are surfaced as warnings.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd

from alpha_cycle.intelligence.historical_pb import (
    HistoricalPbEvidence,
    build_historical_pb_evidence as _build_historical_pb_evidence,
)
from alpha_cycle.intelligence.valuation import CompanySecurityMapping

_ECONOMIC_SECURITY_CLASSES = frozenset({"common", "preferred", "other"})
_UNRESOLVED_SHARE_MARKER = "unresolved_missing_economic_share_count"
_GROUP_KEYS = ("ticker", "business_year", "report_code")


def _report_group_usable(group: pd.DataFrame) -> bool:
    economic = group.loc[
        group["security_class"].astype("string").isin(_ECONOMIC_SECURITY_CLASSES)
    ]
    if economic.empty:
        return False
    issued = pd.to_numeric(economic["issued_shares"], errors="coerce")
    if not issued.gt(0).any():
        return False
    if "normalization_warning" not in economic.columns:
        return True
    warnings = economic["normalization_warning"].astype("string").fillna("")
    unresolved = warnings.str.contains(_UNRESOLVED_SHARE_MARKER, regex=False)
    return not bool(unresolved.any())


def _usable_share_history(
    shares: pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    required = {*_GROUP_KEYS, "security_class", "issued_shares"}
    missing = required - set(shares.columns)
    if missing:
        raise ValueError(
            f"stock-total history missing fallback columns: {sorted(missing)}"
        )

    kept: list[pd.DataFrame] = []
    excluded: list[str] = []
    grouped = shares.groupby(list(_GROUP_KEYS), sort=False, dropna=False)
    for raw_key, group in grouped:
        key = tuple(raw_key) if isinstance(raw_key, tuple) else (raw_key,)
        if _report_group_usable(group):
            kept.append(group.copy())
            continue
        ticker = str(key[0]).strip().zfill(6)
        business_year = str(key[1]) if len(key) > 1 else "?"
        report_code = str(key[2]) if len(key) > 2 else "?"
        excluded.append(
            f"{ticker}: historical P/B ignored visible unusable stock-total report "
            f"{business_year}/{report_code}; older usable report may be selected"
        )

    if not kept:
        raise ValueError("stock-total history contains no usable economic-class reports")
    frame = pd.concat(kept, ignore_index=True, sort=False)
    return frame, tuple(excluded)


def build_historical_pb_evidence(
    prices: pd.DataFrame,
    shares: pd.DataFrame,
    financial_history: pd.DataFrame,
    *,
    evaluation_date: date,
    security_mappings: Mapping[str, CompanySecurityMapping] | None = None,
) -> HistoricalPbEvidence:
    """Build P/B using only usable stock-total report groups, without inference."""

    usable_shares, fallback_warnings = _usable_share_history(shares)
    evidence = _build_historical_pb_evidence(
        prices,
        usable_shares,
        financial_history,
        evaluation_date=evaluation_date,
        security_mappings=security_mappings,
    )
    return HistoricalPbEvidence(
        evaluation_date=evidence.evaluation_date,
        series=evidence.series,
        summary=evidence.summary,
        warnings=(*fallback_warnings, *evidence.warnings),
        decision_score_enabled=evidence.decision_score_enabled,
        historical_vintage_certified=evidence.historical_vintage_certified,
        point_in_time_backtest_eligible=evidence.point_in_time_backtest_eligible,
    )


__all__ = ["build_historical_pb_evidence"]
