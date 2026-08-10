"""Build non-scoring historical P/B evidence from source-bounded inputs.

Historical market capitalization is reconstructed from *unadjusted* Kiwoom
closes and the latest OpenDART issued-share report that was available by each
price date.  Book equity is likewise selected only from financial periods whose
availability date is on or before the price date.

The output is observational evidence only.  It does not produce target prices,
fair value, or a decision score, and it is not historical-vintage/backtest
certified because OpenDART's current API is not treated as a complete filing
vintage store.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.valuation import CompanySecurityMapping

MIN_ONE_YEAR_OBSERVATIONS = 252
MIN_TWO_YEAR_OBSERVATIONS = 504


@dataclass(frozen=True)
class HistoricalPbEvidence:
    evaluation_date: date
    series: pd.DataFrame
    summary: pd.DataFrame
    warnings: tuple[str, ...]
    decision_score_enabled: bool = False
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False


def _ticker(value: object) -> str:
    text = str(value).strip().zfill(6)
    if len(text) != 6 or not text.isdigit():
        raise ValueError(f"invalid KRX ticker: {value}")
    return text


def _date_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise ValueError(f"historical P/B input is missing {column}")
    values = pd.to_datetime(frame[column], errors="raise")
    if getattr(values.dt, "tz", None) is not None:
        values = values.dt.tz_localize(None)
    return values.dt.date


def _number(value: object) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _normalize_prices(prices: pd.DataFrame, evaluation_date: date) -> pd.DataFrame:
    required = {"ticker", "date", "close_price", "adjusted"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"valuation-history prices missing columns: {sorted(missing)}")
    result = prices.copy()
    result["ticker"] = result["ticker"].map(_ticker)
    result["date"] = _date_series(result, "date")
    result["close_price"] = pd.to_numeric(result["close_price"], errors="raise")
    normalized_adjusted = result["adjusted"].map(
        lambda value: value
        if isinstance(value, bool)
        else str(value).strip().casefold() in {"true", "1", "yes"}
    )
    if normalized_adjusted.any():
        raise ValueError("historical P/B requires unadjusted price rows only")
    if (result["close_price"] <= 0).any():
        raise ValueError("historical P/B prices must be positive")
    result = result.loc[result["date"] <= evaluation_date].copy()
    if result.empty:
        raise ValueError("valuation-history prices contain no rows by evaluation date")
    if result.duplicated(["ticker", "date"]).any():
        raise ValueError("valuation-history prices contain duplicate ticker/date rows")
    return result.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)


def _normalize_shares(shares: pd.DataFrame, evaluation_date: date) -> pd.DataFrame:
    required = {
        "ticker",
        "business_year",
        "report_code",
        "period_end",
        "available_date",
        "security_name",
        "security_class",
        "issued_shares",
    }
    missing = required - set(shares.columns)
    if missing:
        raise ValueError(f"stock-total history missing columns: {sorted(missing)}")
    result = shares.copy()
    result["ticker"] = result["ticker"].map(_ticker)
    result["period_end"] = _date_series(result, "period_end")
    result["available_date"] = _date_series(result, "available_date")
    result["issued_shares"] = pd.to_numeric(result["issued_shares"], errors="coerce")
    result = result.loc[
        (result["period_end"] <= evaluation_date)
        & (result["available_date"] <= evaluation_date)
    ].copy()
    if result.empty:
        raise ValueError("stock-total history has no rows by evaluation date")
    keys = [
        "ticker",
        "business_year",
        "report_code",
        "security_class",
        "security_name",
    ]
    if result.duplicated(keys).any():
        raise ValueError("stock-total history contains duplicate period/security rows")
    return result.sort_values(
        ["ticker", "available_date", "period_end", "security_class", "security_name"],
        kind="stable",
    ).reset_index(drop=True)


def _normalize_financials(financials: pd.DataFrame, evaluation_date: date) -> pd.DataFrame:
    required = {"ticker", "period_end", "available_date", "equity"}
    missing = required - set(financials.columns)
    if missing:
        raise ValueError(f"financial history missing columns: {sorted(missing)}")
    result = financials.copy()
    result["ticker"] = result["ticker"].map(_ticker)
    result["period_end"] = _date_series(result, "period_end")
    result["available_date"] = _date_series(result, "available_date")
    result["equity"] = pd.to_numeric(result["equity"], errors="coerce")
    if "derived" in result.columns:
        derived = result["derived"].map(
            lambda value: value
            if isinstance(value, bool)
            else str(value).strip().casefold() in {"true", "1", "yes"}
        )
        result = result.loc[~derived].copy()
    result = result.loc[
        (result["period_end"] <= evaluation_date)
        & (result["available_date"] <= evaluation_date)
        & result["equity"].gt(0)
    ].copy()
    if result.empty:
        raise ValueError("financial history has no positive observable equity rows")
    return result.sort_values(
        ["ticker", "available_date", "period_end"],
        kind="stable",
    ).reset_index(drop=True)


def _latest_report_group(shares: pd.DataFrame, ticker: str, as_of: date) -> pd.DataFrame:
    eligible = shares.loc[
        (shares["ticker"] == ticker)
        & (shares["period_end"] <= as_of)
        & (shares["available_date"] <= as_of)
    ]
    if eligible.empty:
        return eligible
    periods = eligible.loc[
        :, ["business_year", "report_code", "available_date", "period_end"]
    ].drop_duplicates()
    selected = periods.sort_values(
        ["available_date", "period_end", "business_year", "report_code"],
        kind="stable",
    ).iloc[-1]
    return eligible.loc[
        (eligible["business_year"].astype(str) == str(selected["business_year"]))
        & (eligible["report_code"].astype(str) == str(selected["report_code"]))
    ].copy()


def _latest_equity(financials: pd.DataFrame, ticker: str, as_of: date) -> Mapping[str, object] | None:
    eligible = financials.loc[
        (financials["ticker"] == ticker)
        & (financials["period_end"] <= as_of)
        & (financials["available_date"] <= as_of)
    ]
    if eligible.empty:
        return None
    selected = eligible.sort_values(
        ["available_date", "period_end"],
        kind="stable",
    ).iloc[-1]
    return cast(Mapping[str, object], selected.to_dict())


def _security_symbol(
    ticker: str,
    security: Mapping[str, object],
    report_rows: pd.DataFrame,
    mappings: Mapping[str, CompanySecurityMapping],
) -> tuple[str | None, str]:
    security_name = str(security.get("security_name", "")).strip()
    security_class = str(security.get("security_class", "")).strip()
    company_mapping = mappings.get(ticker)
    if company_mapping is not None and security_name in company_mapping.securities:
        return _ticker(company_mapping.securities[security_name]), "explicit"
    common_rows = report_rows.loc[
        report_rows["security_class"].astype(str).eq("common")
        & pd.to_numeric(report_rows["issued_shares"], errors="coerce").gt(0)
    ]
    if security_class == "common" and len(common_rows) == 1:
        return ticker, "default_common"
    return None, "unmapped"


def _market_cap_for_date(
    *,
    ticker: str,
    as_of: date,
    report_rows: pd.DataFrame,
    price_lookup: Mapping[tuple[str, date], float],
    mappings: Mapping[str, CompanySecurityMapping],
) -> tuple[float | None, list[dict[str, object]], str | None]:
    issued = pd.to_numeric(report_rows["issued_shares"], errors="coerce")
    classes = report_rows.loc[
        report_rows["security_class"].isin(["common", "preferred", "other"])
        & issued.gt(0)
    ].copy()
    if classes.empty:
        return None, [], "no_issued_equity_classes"
    parts: list[dict[str, object]] = []
    total = 0.0
    for raw in classes.to_dict(orient="records"):
        security = cast(Mapping[str, object], raw)
        symbol, mapping_source = _security_symbol(
            ticker,
            security,
            classes,
            mappings,
        )
        if symbol is None:
            return None, parts, f"unmapped_security:{security.get('security_name')}"
        price = price_lookup.get((symbol, as_of))
        share_count = _number(security.get("issued_shares"))
        if price is None:
            return None, parts, f"missing_exact_date_price:{symbol}"
        if share_count is None or share_count <= 0:
            return None, parts, f"invalid_share_count:{security.get('security_name')}"
        value = float(price) * share_count
        total += value
        parts.append(
            {
                "security_name": str(security.get("security_name", "")),
                "security_class": str(security.get("security_class", "")),
                "symbol": symbol,
                "mapping_source": mapping_source,
                "close_price": float(price),
                "issued_shares": int(share_count),
                "market_value": value,
            }
        )
    return total, parts, None


def _band_status(observations: int) -> str:
    if observations >= MIN_TWO_YEAR_OBSERVATIONS:
        return "observational_2y_ready"
    if observations >= MIN_ONE_YEAR_OBSERVATIONS:
        return "observational_1y_ready"
    return "insufficient_history"


def build_historical_pb_evidence(
    prices: pd.DataFrame,
    shares: pd.DataFrame,
    financial_history: pd.DataFrame,
    *,
    evaluation_date: date,
    security_mappings: Mapping[str, CompanySecurityMapping] | None = None,
) -> HistoricalPbEvidence:
    """Reconstruct daily P/B without using future-visible share/equity rows."""

    normalized_prices = _normalize_prices(prices, evaluation_date)
    normalized_shares = _normalize_shares(shares, evaluation_date)
    normalized_financials = _normalize_financials(financial_history, evaluation_date)
    mappings = dict(security_mappings or {})
    price_lookup = {
        (str(raw["ticker"]), cast(date, raw["date"])): float(raw["close_price"])
        for raw in normalized_prices.to_dict(orient="records")
    }

    observations: list[dict[str, object]] = []
    warnings: list[str] = []
    target_tickers = sorted(set(normalized_shares["ticker"].astype(str)))
    for ticker in target_tickers:
        candidate_dates = sorted(
            normalized_prices.loc[
                normalized_prices["ticker"].astype(str).eq(ticker),
                "date",
            ].tolist()
        )
        skipped: dict[str, int] = {}
        for as_of in candidate_dates:
            report_rows = _latest_report_group(normalized_shares, ticker, as_of)
            if report_rows.empty:
                skipped["share_report_unavailable"] = skipped.get("share_report_unavailable", 0) + 1
                continue
            equity_row = _latest_equity(normalized_financials, ticker, as_of)
            if equity_row is None:
                skipped["equity_unavailable"] = skipped.get("equity_unavailable", 0) + 1
                continue
            market_cap, parts, market_reason = _market_cap_for_date(
                ticker=ticker,
                as_of=as_of,
                report_rows=report_rows,
                price_lookup=price_lookup,
                mappings=mappings,
            )
            if market_cap is None:
                reason = market_reason or "market_cap_unavailable"
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            equity = _number(equity_row.get("equity"))
            if equity is None or equity <= 0:
                skipped["equity_nonpositive"] = skipped.get("equity_nonpositive", 0) + 1
                continue
            share_period_end = cast(date, report_rows["period_end"].iloc[0])
            share_available_date = cast(date, report_rows["available_date"].max())
            equity_period_end = cast(date, equity_row["period_end"])
            equity_available_date = cast(date, equity_row["available_date"])
            if share_available_date > as_of or equity_available_date > as_of:
                raise ValueError("historical P/B attempted to use future-visible evidence")
            observations.append(
                {
                    "ticker": ticker,
                    "date": as_of,
                    "market_cap": market_cap,
                    "equity": equity,
                    "pb": market_cap / equity,
                    "share_period_end": share_period_end,
                    "share_available_date": share_available_date,
                    "equity_period_end": equity_period_end,
                    "equity_available_date": equity_available_date,
                    "security_values_json": json.dumps(parts, ensure_ascii=False, sort_keys=True),
                    "price_basis": "unadjusted",
                    "decision_score_enabled": False,
                }
            )
        if skipped:
            summary = ",".join(f"{key}={value}" for key, value in sorted(skipped.items()))
            warnings.append(f"{ticker}: historical P/B skipped dates: {summary}")

    series = pd.DataFrame(observations)
    if series.empty:
        raise ValueError("No historical P/B observations survived source/date validation")
    series = series.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    summaries: list[dict[str, object]] = []
    for ticker, group in series.groupby("ticker", sort=True):
        values = pd.to_numeric(group["pb"], errors="raise")
        latest = float(values.iloc[-1])
        summaries.append(
            {
                "ticker": str(ticker),
                "observation_count": len(group),
                "first_date": group["date"].iloc[0],
                "last_date": group["date"].iloc[-1],
                "history_span_calendar_days": (
                    cast(date, group["date"].iloc[-1]) - cast(date, group["date"].iloc[0])
                ).days,
                "latest_pb": latest,
                "pb_min": float(values.min()),
                "pb_p25": float(values.quantile(0.25)),
                "pb_median": float(values.median()),
                "pb_p75": float(values.quantile(0.75)),
                "pb_max": float(values.max()),
                "latest_pb_percentile": float(values.le(latest).mean() * 100.0),
                "band_status": _band_status(len(group)),
                "decision_score_enabled": False,
                "historical_vintage_certified": False,
                "point_in_time_backtest_eligible": False,
            }
        )
    summary_frame = pd.DataFrame(summaries).sort_values("ticker", kind="stable").reset_index(drop=True)
    return HistoricalPbEvidence(
        evaluation_date=evaluation_date,
        series=series,
        summary=summary_frame,
        warnings=tuple(warnings),
    )


__all__ = [
    "HistoricalPbEvidence",
    "MIN_ONE_YEAR_OBSERVATIONS",
    "MIN_TWO_YEAR_OBSERVATIONS",
    "build_historical_pb_evidence",
]
