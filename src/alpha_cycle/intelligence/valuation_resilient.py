"""Fail-closed valuation guard for unresolved OpenDART issued-share rows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.valuation import (
    CompanySecurityMapping,
    ValuationDataClient,
    ValuationEvidenceSnapshot,
)
from alpha_cycle.intelligence.valuation import (
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
_METRIC_COLUMNS = (
    "ticker",
    "share_period_end",
    "share_available_date",
    "priced_security_classes",
    "required_security_classes",
    "market_cap_complete",
    "share_count_complete",
    "missing_security_names",
    "market_cap_proxy",
    "market_cap",
    "annual_reference_year",
    "annual_revenue",
    "annual_net_income",
    "annual_equity",
    "annual_free_cash_flow",
    "pe",
    "pb",
    "ps",
    "fcf_yield",
    "earnings_yield",
    "valuation_score",
    "valuation_status",
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
    except (TypeError, ValueError):
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
    for raw_value in unresolved.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
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


def _latest_annual_reference(
    financial_history: pd.DataFrame,
    ticker: str,
) -> Mapping[str, object] | None:
    if financial_history.empty or "ticker" not in financial_history.columns:
        return None
    annual = financial_history.loc[
        financial_history["ticker"].astype(str).eq(ticker)
        & financial_history["period_label"].astype(str).eq("FY")
    ].sort_values("period_end", kind="stable")
    if annual.empty:
        return None
    return cast(Mapping[str, object], annual.iloc[-1].to_dict())


def _number(value: object) -> float | None:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(converted) else float(converted)


def _partial_market_cap_proxy(
    security_values: pd.DataFrame,
    ticker: str,
) -> tuple[float | None, int, int]:
    if security_values.empty or "ticker" not in security_values.columns:
        return None, 0, 0
    company = security_values.loc[security_values["ticker"].astype(str).eq(ticker)]
    if company.empty:
        return None, 0, 0
    priced = company.loc[company["priced"].fillna(False).astype(bool)]
    values = pd.to_numeric(priced["security_market_value"], errors="coerce").dropna()
    proxy = float(values.sum()) if not values.empty else None
    return proxy, len(priced), len(company)


def _placeholder_metric_row(
    ticker: str,
    group: pd.DataFrame,
    security_values: pd.DataFrame,
    financial_history: pd.DataFrame,
    names: list[str],
    columns: list[str],
) -> dict[str, object]:
    row: dict[str, object] = {column: None for column in columns}
    annual = _latest_annual_reference(financial_history, ticker)
    proxy, priced_count, required_count = _partial_market_cap_proxy(
        security_values,
        ticker,
    )
    row.update(
        {
            "ticker": ticker,
            "share_period_end": group["period_end"].max(),
            "share_available_date": group["available_date"].max(),
            "priced_security_classes": priced_count,
            "required_security_classes": required_count,
            "market_cap_complete": False,
            "share_count_complete": False,
            "missing_security_names": json.dumps(names, ensure_ascii=False),
            "market_cap_proxy": proxy,
            "market_cap": None,
            "annual_reference_year": (
                int(str(annual["business_year"])) if annual is not None else None
            ),
            "annual_revenue": _number(annual.get("revenue")) if annual else None,
            "annual_net_income": _number(annual.get("net_income")) if annual else None,
            "annual_equity": _number(annual.get("equity")) if annual else None,
            "annual_free_cash_flow": (
                _number(annual.get("free_cash_flow_ytd")) if annual else None
            ),
            "pe": None,
            "pb": None,
            "ps": None,
            "fcf_yield": None,
            "earnings_yield": None,
            "valuation_score": None,
            "valuation_status": "incomplete_share_count",
        }
    )
    return row


def _ensure_unresolved_metric_rows(
    metrics: pd.DataFrame,
    unresolved: pd.DataFrame,
    security_values: pd.DataFrame,
    financial_history: pd.DataFrame,
) -> pd.DataFrame:
    result = metrics.copy()
    for column in _METRIC_COLUMNS:
        if column not in result.columns:
            result[column] = None
    existing = set(result["ticker"].astype(str))
    additions: list[dict[str, object]] = []
    for ticker_value, group in unresolved.groupby("ticker", sort=False):
        ticker = str(ticker_value)
        if ticker in existing:
            continue
        names = sorted(set(group["security_name"].astype(str)))
        additions.append(
            _placeholder_metric_row(
                ticker,
                group,
                security_values,
                financial_history,
                names,
                list(result.columns),
            )
        )
    if additions:
        result = pd.concat([result, pd.DataFrame(additions)], ignore_index=True, sort=False)
    return result.sort_values("ticker", kind="stable").reset_index(drop=True)


def apply_unresolved_share_count_guard(
    snapshot: ValuationEvidenceSnapshot,
) -> ValuationEvidenceSnapshot:
    """Clear valuation outputs whenever a potential economic share row is unresolved."""

    unresolved = _unresolved_share_rows(snapshot.shares)
    security_values = _append_unresolved_security_rows(
        snapshot.security_values,
        unresolved,
    )
    metrics = _ensure_unresolved_metric_rows(
        snapshot.valuation_metrics,
        unresolved,
        security_values,
        snapshot.financial_history,
    )
    metrics["share_count_complete"] = metrics["share_count_complete"].fillna(True)
    if unresolved.empty:
        return replace(snapshot, security_values=security_values, valuation_metrics=metrics)

    warnings = list(snapshot.warnings)
    for ticker_value, group in unresolved.groupby("ticker", sort=False):
        ticker = str(ticker_value)
        names = sorted(set(group["security_name"].astype(str)))
        metric_mask = metrics["ticker"].astype(str).eq(ticker)
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
