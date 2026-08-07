"""Issuer-observed semiconductor cycle proxy from already-certified local evidence.

The proxy deliberately does not claim to be an industry-statistics certification. It
summarizes the latest point-in-time quarterly financial evidence for Samsung
Electronics and SK hynix and checks whether equity-price trend confirms the issuer
fundamentals. No decision score is changed by this module.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

DEFAULT_SEMICONDUCTOR_TICKERS = ("005930", "000660")
SOURCE_SCOPE = "issuer_observed_semiconductor_cycle_proxy"
PROXY_VERSION = 1
_QUARTERS = frozenset({"Q1", "Q2", "Q3", "Q4"})


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT or isinstance(value, bool):
        return None
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        return None
    result = float(converted)
    return result if math.isfinite(result) else None


def _growth(
    current: float | None,
    prior: float | None,
    *,
    absolute: bool = False,
) -> float | None:
    if current is None or prior is None:
        return None
    left = abs(current) if absolute else current
    right = abs(prior) if absolute else prior
    if right == 0:
        return None
    return left / abs(right) - 1.0


def _is_positive(value: object) -> bool:
    number = _number(value)
    return number is not None and number > 0


def _latest_quarterly_rows(
    financial_history: pd.DataFrame,
    expected_tickers: Sequence[str],
) -> dict[str, Mapping[str, object]]:
    if financial_history.empty or "ticker" not in financial_history.columns:
        return {}
    required = {"period_label", "period_end", "available_date"}
    if not required.issubset(financial_history.columns):
        return {}
    history = financial_history.copy()
    history["ticker"] = history["ticker"].astype("string").str.zfill(6)
    history = history.loc[
        history["ticker"].isin(tuple(expected_tickers))
        & history["period_label"].astype(str).isin(_QUARTERS)
    ].copy()
    if history.empty:
        return {}
    history["period_end"] = pd.to_datetime(history["period_end"], errors="raise")
    history["available_date"] = pd.to_datetime(history["available_date"], errors="raise")
    result: dict[str, Mapping[str, object]] = {}
    for ticker, group in history.groupby("ticker", sort=True):
        ordered = group.sort_values(
            ["period_end", "available_date", "period_order"],
            kind="stable",
        )
        raw = ordered.iloc[-1].to_dict()
        result[str(ticker)] = {str(key): value for key, value in raw.items()}
    return result


def _market_lookup(market_context: pd.DataFrame) -> dict[str, Mapping[str, object]]:
    if market_context.empty or "ticker" not in market_context.columns:
        return {}
    result: dict[str, Mapping[str, object]] = {}
    for raw_value in market_context.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        ticker = str(raw.get("ticker", "")).strip().zfill(6)
        if ticker:
            result[ticker] = raw
    return result


def _market_confirmed(market: Mapping[str, object]) -> bool | None:
    signals: list[bool] = []
    for key, threshold in (
        ("return_20", 0.0),
        ("return_60", 0.0),
        ("price_to_sma_20", 0.0),
    ):
        value = _number(market.get(key))
        if value is not None:
            signals.append(
                value > threshold if key != "price_to_sma_20" else value >= threshold
            )
    if len(signals) < 2:
        return None
    return sum(signals) >= 2


def _issuer_phase(
    revenue_yoy: float | None,
    operating_income_yoy: float | None,
    margin_change_pp: float | None,
) -> str:
    if revenue_yoy is None or operating_income_yoy is None or margin_change_pp is None:
        return "insufficient_financial_evidence"
    if revenue_yoy > 0 and operating_income_yoy > 0 and margin_change_pp > 0:
        return "earnings_expansion"
    if revenue_yoy > 0 and operating_income_yoy > 0:
        return "revenue_profit_expansion_margin_lag"
    if operating_income_yoy < 0 and margin_change_pp < 0:
        return "earnings_contraction"
    return "mixed_transition"


@dataclass(frozen=True)
class SemiconductorCycleProxy:
    source_scope: str
    proxy_version: int
    industry_cycle_certified: bool
    expected_tickers: tuple[str, ...]
    observed_tickers: tuple[str, ...]
    coverage_status: str
    cycle_proxy_state: str
    issuer_rows: tuple[dict[str, object], ...]
    aggregate: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "source_scope": self.source_scope,
            "proxy_version": self.proxy_version,
            "industry_cycle_certified": self.industry_cycle_certified,
            "expected_tickers": list(self.expected_tickers),
            "observed_tickers": list(self.observed_tickers),
            "coverage_status": self.coverage_status,
            "cycle_proxy_state": self.cycle_proxy_state,
            "issuer_rows": list(self.issuer_rows),
            "aggregate": dict(self.aggregate),
        }


def build_semiconductor_cycle_proxy(
    financial_history: pd.DataFrame,
    market_context: pd.DataFrame,
    *,
    expected_tickers: Sequence[str] = DEFAULT_SEMICONDUCTOR_TICKERS,
) -> SemiconductorCycleProxy:
    """Build a non-scoring semiconductor cycle proxy from issuer and market evidence."""

    expected = tuple(dict.fromkeys(str(value).zfill(6) for value in expected_tickers))
    if not expected:
        raise ValueError("expected_tickers cannot be empty")
    financial = _latest_quarterly_rows(financial_history, expected)
    markets = _market_lookup(market_context)
    rows: list[dict[str, object]] = []

    for ticker in expected:
        raw = financial.get(ticker)
        if raw is None:
            continue
        revenue_yoy = _number(raw.get("revenue_yoy"))
        operating_income_yoy = _number(raw.get("operating_income_yoy"))
        margin_change_pp = _number(raw.get("operating_margin_change_yoy_pp"))
        inventory_yoy = _growth(
            _number(raw.get("inventory")),
            _number(raw.get("inventory_prior_same")),
        )
        derived = bool(raw.get("derived", False))
        capex_yoy = (
            None
            if derived
            else _growth(
                _number(raw.get("capex_ytd")),
                _number(raw.get("capex_prior_ytd")),
                absolute=True,
            )
        )
        inventory_supportive = (
            inventory_yoy <= revenue_yoy + 0.10
            if inventory_yoy is not None and revenue_yoy is not None
            else None
        )
        market = markets.get(ticker, {})
        market_confirmed = _market_confirmed(market)
        rows.append(
            {
                "ticker": ticker,
                "period_label": str(raw.get("period_label", "")),
                "period_end": str(raw.get("period_end", "")),
                "available_date": str(raw.get("available_date", "")),
                "derived_quarter": derived,
                "revenue_yoy": revenue_yoy,
                "operating_income_yoy": operating_income_yoy,
                "operating_margin_change_yoy_pp": margin_change_pp,
                "inventory_yoy": inventory_yoy,
                "inventory_supportive_vs_revenue": inventory_supportive,
                "capex_ytd_yoy": capex_yoy,
                "return_20": _number(market.get("return_20")),
                "return_60": _number(market.get("return_60")),
                "price_to_sma_20": _number(market.get("price_to_sma_20")),
                "market_confirmed": market_confirmed,
                "issuer_phase": _issuer_phase(
                    revenue_yoy,
                    operating_income_yoy,
                    margin_change_pp,
                ),
            }
        )

    observed = tuple(str(row["ticker"]) for row in rows)
    complete = set(observed) == set(expected)
    if not complete:
        state = "insufficient_issuer_coverage"
        coverage = "partial"
    else:
        coverage = "complete_issuer_proxy"
        issuer_count = len(rows)
        operating_growth = sum(
            _is_positive(row.get("operating_income_yoy")) for row in rows
        )
        margin_improving = sum(
            _is_positive(row.get("operating_margin_change_yoy_pp")) for row in rows
        )
        market_confirmed_count = sum(
            row.get("market_confirmed") is True for row in rows
        )
        if (
            operating_growth == issuer_count
            and margin_improving >= max(1, issuer_count // 2)
        ):
            if market_confirmed_count == issuer_count:
                state = "issuer_expansion_market_confirmed"
            elif market_confirmed_count == 0:
                state = "issuer_expansion_market_unconfirmed"
            else:
                state = "issuer_expansion_partial_market_confirmation"
        elif operating_growth == 0 and margin_improving == 0:
            state = "issuer_contraction"
        else:
            state = "issuer_cycle_mixed_transition"

    inventory_observed = [
        row.get("inventory_supportive_vs_revenue")
        for row in rows
        if isinstance(row.get("inventory_supportive_vs_revenue"), bool)
    ]
    aggregate: dict[str, object] = {
        "issuer_count_expected": len(expected),
        "issuer_count_observed": len(rows),
        "revenue_growth_breadth": sum(
            _is_positive(row.get("revenue_yoy")) for row in rows
        ),
        "operating_income_growth_breadth": sum(
            _is_positive(row.get("operating_income_yoy")) for row in rows
        ),
        "margin_improvement_breadth": sum(
            _is_positive(row.get("operating_margin_change_yoy_pp")) for row in rows
        ),
        "inventory_supportive_breadth": sum(
            value is True for value in inventory_observed
        ),
        "inventory_breadth_observed": len(inventory_observed),
        "market_confirmation_breadth": sum(
            row.get("market_confirmed") is True for row in rows
        ),
        "market_confirmation_observed": sum(
            isinstance(row.get("market_confirmed"), bool) for row in rows
        ),
    }
    return SemiconductorCycleProxy(
        source_scope=SOURCE_SCOPE,
        proxy_version=PROXY_VERSION,
        industry_cycle_certified=False,
        expected_tickers=expected,
        observed_tickers=observed,
        coverage_status=coverage,
        cycle_proxy_state=state,
        issuer_rows=tuple(rows),
        aggregate=aggregate,
    )


def attach_semiconductor_cycle_proxy_to_scorecards(
    scorecards: pd.DataFrame,
    proxy: SemiconductorCycleProxy,
) -> pd.DataFrame:
    """Attach informational proxy evidence without altering any score component."""

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    issuer_lookup = {str(row["ticker"]): row for row in proxy.issuer_rows}
    result["cycle_proxy_state"] = proxy.cycle_proxy_state
    result["cycle_proxy_scope"] = proxy.source_scope
    result["industry_cycle_certified"] = proxy.industry_cycle_certified
    result["cycle_proxy_coverage_status"] = proxy.coverage_status
    result["cycle_proxy_issuer_phase"] = result["ticker"].map(
        lambda ticker: str(
            issuer_lookup.get(str(ticker), {}).get("issuer_phase", "not_observed")
        )
    )
    result["cycle_proxy_period"] = result["ticker"].map(
        lambda ticker: str(issuer_lookup.get(str(ticker), {}).get("period_label", ""))
    )
    result["cycle_proxy_market_confirmed"] = result["ticker"].map(
        lambda ticker: issuer_lookup.get(str(ticker), {}).get("market_confirmed")
    )
    result["cycle_proxy_json"] = json.dumps(
        proxy.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
    )
    return result


def attach_semiconductor_cycle_proxy_to_records(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    """Copy compact cycle fields into decision records for downstream consumption."""

    columns = [
        "ticker",
        "cycle_proxy_state",
        "cycle_proxy_scope",
        "industry_cycle_certified",
        "cycle_proxy_coverage_status",
        "cycle_proxy_issuer_phase",
        "cycle_proxy_period",
        "cycle_proxy_market_confirmed",
    ]
    missing = [column for column in columns if column not in scorecards.columns]
    if missing:
        raise ValueError("Scorecards are missing cycle proxy fields: " + ",".join(missing))
    supplement = scorecards.loc[:, columns].copy()
    return records.merge(supplement, on="ticker", how="left", validate="one_to_one")


def _pct(value: object) -> str:
    number = _number(value)
    return "N/A" if number is None else f"{number * 100:.1f}%"


def _pp(value: object) -> str:
    number = _number(value)
    return "N/A" if number is None else f"{number:+.1f}%p"


def append_semiconductor_cycle_proxy_report(
    report: str,
    proxy: SemiconductorCycleProxy,
) -> str:
    """Append a transparent non-scoring cycle-proxy section to the decision report."""

    header = (
        "| 종목 | 기준분기 | 매출 YoY | 영업이익 YoY | 마진 YoY 변화 | "
        "재고 YoY | Capex YTD YoY | 20일 수익률 | 시장확인 | 발행사 국면 |"
    )
    lines = [
        report.rstrip(),
        "",
        "## 반도체 사이클 프록시 (산업지표 미인증)",
        "",
        f"- 상태: `{proxy.cycle_proxy_state}`",
        f"- 범위: `{proxy.source_scope}` / coverage `{proxy.coverage_status}`",
        "- 이 지표는 삼성전자·SK하이닉스의 공시 재무와 가격 흐름만 사용하며, "
        "메모리 가격·산업 생산/출하/재고 통계를 대체하지 않습니다.",
        "- 현재 의사결정 점수에는 반영하지 않습니다.",
        "",
        header,
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in proxy.issuer_rows:
        confirmed = row.get("market_confirmed")
        if confirmed is True:
            market_text = "확인"
        elif confirmed is False:
            market_text = "미확인"
        else:
            market_text = "자료부족"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("ticker", "")),
                    str(row.get("period_label", "")),
                    _pct(row.get("revenue_yoy")),
                    _pct(row.get("operating_income_yoy")),
                    _pp(row.get("operating_margin_change_yoy_pp")),
                    _pct(row.get("inventory_yoy")),
                    _pct(row.get("capex_ytd_yoy")),
                    _pct(row.get("return_20")),
                    market_text,
                    str(row.get("issuer_phase", "")),
                ]
            )
            + " |"
        )
    aggregate = proxy.aggregate
    observed = aggregate["issuer_count_observed"]
    market_observed = aggregate["market_confirmation_observed"]
    lines.extend(
        [
            "",
            "### 프록시 breadth",
            "",
            f"- 매출 증가: {aggregate['revenue_growth_breadth']}/{observed}",
            (
                "- 영업이익 증가: "
                f"{aggregate['operating_income_growth_breadth']}/{observed}"
            ),
            (
                "- 영업마진 개선: "
                f"{aggregate['margin_improvement_breadth']}/{observed}"
            ),
            (
                "- 가격 추세 확인: "
                f"{aggregate['market_confirmation_breadth']}/{market_observed}"
            ),
            "",
            (
                "공식 산업 사이클 인증에는 KOSIS 반도체 생산·출하·재고와 "
                "메모리 가격/공급 데이터가 추가로 필요합니다."
            ),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DEFAULT_SEMICONDUCTOR_TICKERS",
    "PROXY_VERSION",
    "SOURCE_SCOPE",
    "SemiconductorCycleProxy",
    "append_semiconductor_cycle_proxy_report",
    "attach_semiconductor_cycle_proxy_to_records",
    "attach_semiconductor_cycle_proxy_to_scorecards",
    "build_semiconductor_cycle_proxy",
]
