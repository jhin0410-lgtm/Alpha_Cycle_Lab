"""Explainable transformations from raw research data into investment features."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class KpiSpec:
    name: str
    aliases: tuple[str, ...]
    statements: tuple[str, ...]


KPI_SPECS = (
    KpiSpec(
        "revenue",
        (
            "ifrs-full_revenue",
            "dart_revenue",
            "매출액",
            "영업수익",
            "수익매출액",
            "revenue",
        ),
        ("IS", "CIS"),
    ),
    KpiSpec(
        "operating_income",
        (
            "dart_operatingincomeloss",
            "ifrs-full_profitlossfromoperatingactivities",
            "영업이익손실",
            "영업이익",
            "영업손실",
            "operatingincomeloss",
        ),
        ("IS", "CIS"),
    ),
    KpiSpec(
        "net_income",
        (
            "ifrs-full_profitloss",
            "dart_profitloss",
            "당기순이익손실",
            "당기순이익",
            "당기순손익",
            "profitloss",
        ),
        ("IS", "CIS"),
    ),
    KpiSpec(
        "assets",
        ("ifrs-full_assets", "자산총계", "assets"),
        ("BS",),
    ),
    KpiSpec(
        "liabilities",
        ("ifrs-full_liabilities", "부채총계", "liabilities"),
        ("BS",),
    ),
    KpiSpec(
        "equity",
        ("ifrs-full_equity", "자본총계", "equity"),
        ("BS",),
    ),
    KpiSpec(
        "operating_cash_flow",
        (
            "ifrs-full_cashflowsfromusedinoperatingactivities",
            "영업활동현금흐름",
            "영업활동으로인한현금흐름",
            "cashflowsfromusedinoperatingactivities",
        ),
        ("CF",),
    ),
    KpiSpec(
        "capex",
        (
            "ifrs-full_purchaseofpropertyplantandequipmentclassifiedasinvestingactivities",
            "유형자산의취득",
            "유형자산취득",
            "purchaseofpropertyplantandequipment",
        ),
        ("CF",),
    ),
    KpiSpec(
        "cash",
        (
            "ifrs-full_cashandcashequivalents",
            "현금및현금성자산",
            "cashandcashequivalents",
        ),
        ("BS",),
    ),
    KpiSpec(
        "inventory",
        ("ifrs-full_inventories", "재고자산", "inventories"),
        ("BS",),
    ),
    KpiSpec(
        "receivables",
        (
            "ifrs-full_tradeandothercurrentreceivables",
            "ifrs-full_tradereceivables",
            "매출채권및기타채권",
            "매출채권",
            "tradereceivables",
        ),
        ("BS",),
    ),
)


@dataclass(frozen=True)
class DisclosureRule:
    category: str
    priority: str
    material_score: int
    noise: bool
    patterns: tuple[str, ...]


DISCLOSURE_RULES = (
    DisclosureRule(
        "low_signal_insider",
        "low",
        0,
        True,
        ("임원ㆍ주요주주특정증권등소유상황보고서",),
    ),
    DisclosureRule(
        "operational_risk",
        "critical",
        5,
        False,
        ("생산중단", "영업정지", "횡령", "배임", "부도", "회생절차", "소송등의제기"),
    ),
    DisclosureRule(
        "contract_order",
        "critical",
        5,
        False,
        ("단일판매ㆍ공급계약", "공급계약체결", "수주계약", "수주"),
    ),
    DisclosureRule(
        "capex_investment",
        "high",
        5,
        False,
        ("신규시설투자", "시설투자", "유형자산취득", "타법인주식및출자증권취득"),
    ),
    DisclosureRule(
        "earnings",
        "high",
        5,
        False,
        ("영업(잠정)실적", "잠정실적", "매출액또는손익구조", "사업보고서", "분기보고서", "반기보고서"),
    ),
    DisclosureRule(
        "capital_allocation",
        "high",
        4,
        False,
        ("자기주식취득", "자기주식처분", "주식소각", "현금ㆍ현물배당결정", "배당결정"),
    ),
    DisclosureRule(
        "financing",
        "high",
        4,
        False,
        ("유상증자", "무상증자", "전환사채", "신주인수권부사채", "단기차입금증가", "회사채발행"),
    ),
    DisclosureRule(
        "ownership_governance",
        "medium",
        3,
        False,
        ("최대주주변경", "주식등의대량보유상황보고서", "최대주주등소유주식변동"),
    ),
    DisclosureRule(
        "investor_relations",
        "medium",
        2,
        False,
        ("기업설명회", "IR개최", "IR자료"),
    ),
    DisclosureRule(
        "related_party",
        "low",
        1,
        True,
        ("동일인등", "특수관계인"),
    ),
)


PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _normalized(value: object) -> str:
    text = str(value).strip().casefold()
    return re.sub(r"[^0-9a-z가-힣]+", "", text)


def _amount(value: object) -> float | None:
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "None", "nan"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    result = float(-amount if negative else amount)
    return result if math.isfinite(result) else None


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], value) if isinstance(value, dict) else {}


def _as_rows(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [cast(Mapping[str, object], item) for item in value if isinstance(item, dict)]


def _financial_rows(raw_opendart: Mapping[str, object], ticker: str) -> list[Mapping[str, object]]:
    company_payload = _as_mapping(raw_opendart.get(ticker))
    financial_wrapper = _as_mapping(company_payload.get("financial"))
    financial_payload = _as_mapping(financial_wrapper.get("financials"))
    return _as_rows(financial_payload.get("list"))


def _candidate_score(raw: Mapping[str, object], spec: KpiSpec) -> int:
    account_id = _normalized(raw.get("account_id", ""))
    account_name = _normalized(raw.get("account_nm", ""))
    statement = str(raw.get("sj_div", "")).strip().upper()
    aliases = tuple(_normalized(alias) for alias in spec.aliases)
    score = 0
    for alias in aliases:
        if alias and alias in {account_id, account_name}:
            score = max(score, 100)
        elif alias and (alias in account_id or alias in account_name):
            score = max(score, 60)
    if score == 0:
        return 0
    if statement in spec.statements:
        score += 15
    detail = str(raw.get("account_detail", "")).strip()
    if detail in {"", "-"}:
        score += 5
    order = str(raw.get("ord", "")).strip()
    if order.isdigit():
        score += max(0, 5 - min(int(order), 5))
    return score


def _select_kpi(
    rows: Sequence[Mapping[str, object]],
    spec: KpiSpec,
) -> tuple[Mapping[str, object] | None, int, int]:
    candidates = [(raw, _candidate_score(raw, spec)) for raw in rows]
    matched = [(raw, score) for raw, score in candidates if score > 0]
    if not matched:
        return None, 0, 0
    matched.sort(
        key=lambda item: (
            item[1],
            str(item[0].get("account_detail", "")) in {"", "-"},
            -int(str(item[0].get("ord", "999999")))
            if str(item[0].get("ord", "")).isdigit()
            else -999999,
            str(item[0].get("account_id", "")),
        ),
        reverse=True,
    )
    selected, score = matched[0]
    return selected, score, len(matched)


def _growth(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None or prior == 0:
        return None
    return current / abs(prior) - 1.0


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    result = numerator / denominator
    return result if math.isfinite(result) else None


def extract_financial_kpis(
    raw_opendart: Mapping[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    """Extract canonical current/prior financial KPIs from raw OpenDART payloads."""

    wide_rows: list[dict[str, object]] = []
    mapping_rows: list[dict[str, object]] = []
    warnings: list[str] = []
    tickers = sorted(key for key in raw_opendart if not str(key).startswith("_"))
    for ticker in tickers:
        rows = _financial_rows(raw_opendart, ticker)
        wide: dict[str, object] = {"ticker": ticker}
        matched_count = 0
        for spec in KPI_SPECS:
            selected, score, candidate_count = _select_kpi(rows, spec)
            current: float | None = None
            prior: float | None = None
            prior2: float | None = None
            if selected is not None:
                matched_count += 1
                current = _amount(selected.get("thstrm_amount"))
                prior = _amount(selected.get("frmtrm_amount"))
                prior2 = _amount(selected.get("bfefrmtrm_amount"))
                mapping_rows.append(
                    {
                        "ticker": ticker,
                        "metric": spec.name,
                        "statement": str(selected.get("sj_div", "")).strip(),
                        "account_id": str(selected.get("account_id", "")).strip(),
                        "account_name": str(selected.get("account_nm", "")).strip(),
                        "account_detail": str(selected.get("account_detail", "")).strip(),
                        "receipt_no": str(selected.get("rcept_no", "")).strip(),
                        "match_score": score,
                        "candidate_count": candidate_count,
                    }
                )
            wide[spec.name] = current
            wide[f"{spec.name}_prior"] = prior
            wide[f"{spec.name}_prior2"] = prior2
            wide[f"{spec.name}_yoy"] = _growth(current, prior)

        revenue = cast(float | None, wide.get("revenue"))
        revenue_prior = cast(float | None, wide.get("revenue_prior"))
        operating_income = cast(float | None, wide.get("operating_income"))
        operating_income_prior = cast(float | None, wide.get("operating_income_prior"))
        net_income = cast(float | None, wide.get("net_income"))
        net_income_prior = cast(float | None, wide.get("net_income_prior"))
        equity = cast(float | None, wide.get("equity"))
        equity_prior = cast(float | None, wide.get("equity_prior"))
        liabilities = cast(float | None, wide.get("liabilities"))
        ocf = cast(float | None, wide.get("operating_cash_flow"))
        capex = cast(float | None, wide.get("capex"))

        wide["operating_margin"] = _ratio(operating_income, revenue)
        wide["operating_margin_prior"] = _ratio(operating_income_prior, revenue_prior)
        current_margin = cast(float | None, wide["operating_margin"])
        prior_margin = cast(float | None, wide["operating_margin_prior"])
        wide["operating_margin_change_pp"] = (
            (current_margin - prior_margin) * 100.0
            if current_margin is not None and prior_margin is not None
            else None
        )
        wide["net_margin"] = _ratio(net_income, revenue)
        wide["net_margin_prior"] = _ratio(net_income_prior, revenue_prior)
        average_equity = (
            (equity + equity_prior) / 2.0
            if equity is not None and equity_prior is not None
            else equity
        )
        wide["roe"] = _ratio(net_income, average_equity)
        wide["debt_to_equity"] = _ratio(liabilities, equity)
        wide["ocf_to_net_income"] = _ratio(ocf, net_income)
        wide["free_cash_flow"] = ocf - abs(capex) if ocf is not None and capex is not None else None
        wide["inventory_growth"] = wide.get("inventory_yoy")
        wide["receivables_growth"] = wide.get("receivables_yoy")
        wide["kpi_coverage"] = matched_count / len(KPI_SPECS)
        wide_rows.append(wide)
        if matched_count < 6:
            warnings.append(
                f"{ticker}: only {matched_count}/{len(KPI_SPECS)} canonical KPIs matched"
            )

    return (
        pd.DataFrame(wide_rows).sort_values("ticker", kind="stable").reset_index(drop=True),
        pd.DataFrame(mapping_rows).sort_values(
            ["ticker", "metric"], kind="stable"
        ).reset_index(drop=True),
        tuple(warnings),
    )


def classify_disclosures(
    disclosures: pd.DataFrame,
    *,
    evaluation_date: date,
    recent_days: int = 365,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Classify filing titles into transparent catalyst and noise buckets."""

    if recent_days <= 0:
        raise ValueError("recent_days must be positive")
    required = {"ticker", "rcept_no", "report_name", "receipt_date"}
    missing = sorted(required - set(disclosures.columns))
    if missing:
        raise ValueError(f"Missing disclosure columns: {', '.join(missing)}")
    data = disclosures.copy()
    if data.empty:
        columns = [
            "ticker",
            "rcept_no",
            "report_name",
            "receipt_date",
            "category",
            "priority",
            "material_score",
            "is_noise",
            "is_correction",
            "age_days",
            "is_recent",
        ]
        empty = pd.DataFrame(columns=columns)
        summary = pd.DataFrame(
            columns=[
                "ticker",
                "total_disclosures",
                "noise_disclosures",
                "material_disclosures",
                "critical_disclosures",
                "high_disclosures",
                "recent_material_disclosures",
                "latest_material_date",
            ]
        )
        return empty, empty.copy(), summary

    data["receipt_date"] = pd.to_datetime(data["receipt_date"], errors="raise").dt.date
    classified: list[dict[str, object]] = []
    for raw in data.to_dict(orient="records"):
        report_name = str(raw.get("report_name", "")).strip()
        normalized = _normalized(report_name)
        selected: DisclosureRule | None = None
        for rule in DISCLOSURE_RULES:
            if any(_normalized(pattern) in normalized for pattern in rule.patterns):
                selected = rule
                break
        if selected is None:
            selected = DisclosureRule("other", "low", 1, True, ())
        receipt_date = cast(date, raw["receipt_date"])
        age_days = (evaluation_date - receipt_date).days
        if age_days < 0:
            raise ValueError("Disclosure receipt_date cannot follow evaluation_date")
        classified.append(
            {
                "ticker": str(raw.get("ticker", "")).strip(),
                "rcept_no": str(raw.get("rcept_no", "")).strip(),
                "report_name": report_name,
                "receipt_date": receipt_date,
                "category": selected.category,
                "priority": selected.priority,
                "material_score": selected.material_score,
                "is_noise": selected.noise,
                "is_correction": bool(raw.get("is_correction", "정정" in report_name)),
                "age_days": age_days,
                "is_recent": age_days <= recent_days,
            }
        )
    events = pd.DataFrame(classified).sort_values(
        ["ticker", "receipt_date", "rcept_no"], kind="stable"
    ).reset_index(drop=True)
    catalysts = events.loc[
        (~events["is_noise"])
        & (events["is_recent"])
        & (events["priority"].map(PRIORITY_ORDER) >= PRIORITY_ORDER["high"])
    ].sort_values(
        ["material_score", "receipt_date", "ticker"],
        ascending=[False, False, True],
        kind="stable",
    )

    summaries: list[dict[str, object]] = []
    for ticker, group in events.groupby("ticker", sort=True):
        material = group.loc[~group["is_noise"]]
        recent_material = material.loc[material["is_recent"]]
        summaries.append(
            {
                "ticker": str(ticker),
                "total_disclosures": len(group),
                "noise_disclosures": int(group["is_noise"].sum()),
                "material_disclosures": len(material),
                "critical_disclosures": int((material["priority"] == "critical").sum()),
                "high_disclosures": int((material["priority"] == "high").sum()),
                "recent_material_disclosures": len(recent_material),
                "latest_material_date": (
                    material["receipt_date"].max() if not material.empty else pd.NaT
                ),
            }
        )
    return events, catalysts.reset_index(drop=True), pd.DataFrame(summaries)


def build_macro_regime(macro: pd.DataFrame) -> pd.DataFrame:
    """Summarize each macro series without claiming a causal equity forecast."""

    required = {"series_id", "observation_date", "value", "unit"}
    missing = sorted(required - set(macro.columns))
    if missing:
        raise ValueError(f"Missing macro columns: {', '.join(missing)}")
    rows: list[dict[str, object]] = []
    for series_id, group in macro.groupby("series_id", sort=True):
        ordered = group.copy()
        ordered["observation_date"] = pd.to_datetime(
            ordered["observation_date"], errors="raise"
        ).dt.date
        ordered["value"] = pd.to_numeric(ordered["value"], errors="raise")
        ordered = ordered.sort_values("observation_date", kind="stable")
        values = ordered["value"].astype(float).reset_index(drop=True)
        dates = ordered["observation_date"].reset_index(drop=True)
        latest = float(values.iloc[-1])
        change_1 = latest - float(values.iloc[-2]) if len(values) >= 2 else None
        base_20 = float(values.iloc[-21]) if len(values) >= 21 else float(values.iloc[0])
        pct_change_20 = latest / base_20 - 1.0 if base_20 != 0 else None
        differences = values.diff()
        changed = differences.loc[differences.abs() > 1e-12]
        last_change_date: date | None = None
        last_change_value: float | None = None
        if not changed.empty:
            index = int(changed.index[-1])
            last_change_date = cast(date, dates.iloc[index])
            last_change_value = float(changed.iloc[-1])

        normalized_id = str(series_id).casefold()
        if normalized_id == "kr_base_rate":
            if last_change_value is None:
                regime = "unchanged_observed_window"
            elif last_change_value < 0:
                regime = "easing_last_move"
            else:
                regime = "tightening_last_move"
        elif normalized_id == "usd_krw":
            if pct_change_20 is None:
                regime = "insufficient_history"
            elif pct_change_20 >= 0.02:
                regime = "krw_weakening"
            elif pct_change_20 <= -0.02:
                regime = "krw_strengthening"
            else:
                regime = "range_bound"
        elif pct_change_20 is None:
            regime = "insufficient_history"
        elif pct_change_20 > 0.01:
            regime = "rising"
        elif pct_change_20 < -0.01:
            regime = "falling"
        else:
            regime = "flat"

        rows.append(
            {
                "series_id": str(series_id),
                "latest_date": dates.iloc[-1],
                "latest_value": latest,
                "unit": str(ordered["unit"].iloc[-1]),
                "observations": len(ordered),
                "change_1": change_1,
                "pct_change_20": pct_change_20,
                "last_change_date": last_change_date,
                "last_change_value": last_change_value,
                "regime": regime,
            }
        )
    return pd.DataFrame(rows).sort_values("series_id", kind="stable").reset_index(drop=True)


def _period_return(close: pd.Series[Any], periods: int) -> float | None:
    if len(close) <= periods:
        return None
    previous = float(close.iloc[-periods - 1])
    current = float(close.iloc[-1])
    return current / previous - 1.0 if previous > 0 else None


def build_market_context(
    candles: pd.DataFrame,
    technical_features: pd.DataFrame,
    *,
    benchmark: str | None = None,
) -> pd.DataFrame:
    """Create timing and relative-strength context from a market snapshot."""

    required = {"symbol", "timestamp", "close", "volume"}
    missing = sorted(required - set(candles.columns))
    if missing:
        raise ValueError(f"Missing candle columns: {', '.join(missing)}")
    rows: list[dict[str, object]] = []
    for symbol, group in candles.groupby("symbol", sort=True):
        ordered = group.copy()
        ordered["timestamp"] = pd.to_datetime(ordered["timestamp"], errors="raise", utc=True)
        ordered["close"] = pd.to_numeric(ordered["close"], errors="raise")
        ordered["volume"] = pd.to_numeric(ordered["volume"], errors="raise")
        ordered = ordered.sort_values("timestamp", kind="stable")
        close = ordered["close"].astype(float).reset_index(drop=True)
        volume = ordered["volume"].astype(float).reset_index(drop=True)
        returns = close.pct_change(fill_method=None).dropna()
        sma20 = float(close.iloc[-20:].mean()) if len(close) >= 20 else None
        volatility = (
            float(returns.iloc[-20:].std(ddof=1)) * math.sqrt(252.0)
            if len(returns) >= 20
            else None
        )
        trailing = close.iloc[-60:] if len(close) >= 60 else close
        peak = trailing.cummax()
        drawdown = trailing / peak - 1.0
        max_drawdown = float(drawdown.min()) if not drawdown.empty else None
        volume_ratio = None
        if len(volume) >= 21:
            average = float(volume.iloc[-21:-1].mean())
            volume_ratio = float(volume.iloc[-1]) / average if average > 0 else None
        rows.append(
            {
                "ticker": str(symbol),
                "last_timestamp": ordered["timestamp"].iloc[-1],
                "last_price": float(close.iloc[-1]),
                "return_1": _period_return(close, 1),
                "return_5": _period_return(close, 5),
                "return_20": _period_return(close, 20),
                "return_60": _period_return(close, 60),
                "sma_20": sma20,
                "price_to_sma_20": (
                    float(close.iloc[-1]) / sma20 - 1.0 if sma20 is not None and sma20 > 0 else None
                ),
                "realized_volatility_20": volatility,
                "max_drawdown_60": max_drawdown,
                "volume_ratio_20": volume_ratio,
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    for horizon in (20, 60):
        column = f"return_{horizon}"
        result[f"relative_strength_rank_{horizon}"] = result[column].rank(
            method="average", pct=True
        )
    if benchmark is not None:
        benchmark_rows = result.loc[result["ticker"] == benchmark]
        if benchmark_rows.empty:
            raise ValueError(f"Benchmark {benchmark} is not present in the market snapshot")
        benchmark_row = benchmark_rows.iloc[0]
        for horizon in (5, 20, 60):
            column = f"return_{horizon}"
            benchmark_value = benchmark_row[column]
            result[f"excess_return_{horizon}"] = result[column].map(
                lambda value: (
                    float(value) - float(benchmark_value)
                    if pd.notna(value) and pd.notna(benchmark_value)
                    else np.nan
                )
            )
    if not technical_features.empty and "symbol" in technical_features.columns:
        supplemental = technical_features.rename(columns={"symbol": "ticker"})
        keep = [
            column
            for column in (
                "ticker",
                "rsi_14",
                "trend_efficiency_20",
                "trend_direction_20",
            )
            if column in supplemental.columns
        ]
        result = result.merge(supplemental.loc[:, keep], on="ticker", how="left")
    return result.sort_values("ticker", kind="stable").reset_index(drop=True)
