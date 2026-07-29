"""Transparent scorecard and Korean report generation for decision snapshots."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import yaml

COMPONENT_WEIGHTS = {
    "earnings_momentum_score": 0.25,
    "financial_quality_score": 0.20,
    "catalyst_score": 0.15,
    "market_timing_score": 0.15,
    "macro_fit_score": 0.10,
    "valuation_score": 0.15,
}


@dataclass(frozen=True)
class DecisionPolicy:
    recent_disclosure_days: int = 365
    positive_threshold: float = 3.8
    mixed_threshold: float = 2.8
    minimum_coverage: float = 0.55

    def __post_init__(self) -> None:
        if self.recent_disclosure_days <= 0:
            raise ValueError("recent_disclosure_days must be positive")
        if not 1.0 <= self.mixed_threshold <= self.positive_threshold <= 5.0:
            raise ValueError("decision thresholds must satisfy 1 <= mixed <= positive <= 5")
        if not 0.0 < self.minimum_coverage <= 1.0:
            raise ValueError("minimum_coverage must be in (0, 1]")


@dataclass(frozen=True)
class CompanyExposure:
    sector: str | None = None
    export_fx_sensitivity: float | None = None
    rate_duration_sensitivity: float | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.export_fx_sensitivity, "export_fx_sensitivity"),
            (self.rate_duration_sensitivity, "rate_duration_sensitivity"),
        ):
            if value is not None and not -1.0 <= value <= 1.0:
                raise ValueError(f"{field} must be between -1 and 1")


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    positives: tuple[str, ...]
    negatives: tuple[str, ...]


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _clamp(value: float) -> float:
    return min(5.0, max(1.0, value))


def _earnings(row: Mapping[str, object]) -> ScoreResult:
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    revenue_yoy = _number(row.get("revenue_yoy"))
    operating_yoy = _number(row.get("operating_income_yoy"))
    margin_change = _number(row.get("operating_margin_change_pp"))
    free_cash_flow = _number(row.get("free_cash_flow"))
    if revenue_yoy is not None:
        if revenue_yoy >= 0.15:
            scores.append(5.0)
            positives.append(f"매출 YoY {revenue_yoy:.1%}")
        elif revenue_yoy > 0:
            scores.append(4.0)
            positives.append(f"매출 성장 {revenue_yoy:.1%}")
        elif revenue_yoy > -0.10:
            scores.append(2.5)
            negatives.append(f"매출 감소 {revenue_yoy:.1%}")
        else:
            scores.append(1.0)
            negatives.append(f"매출 급감 {revenue_yoy:.1%}")
    if operating_yoy is not None:
        if operating_yoy >= 0.30:
            scores.append(5.0)
            positives.append(f"영업이익 YoY {operating_yoy:.1%}")
        elif operating_yoy > 0:
            scores.append(4.0)
            positives.append(f"영업이익 증가 {operating_yoy:.1%}")
        elif operating_yoy > -0.20:
            scores.append(2.0)
            negatives.append(f"영업이익 감소 {operating_yoy:.1%}")
        else:
            scores.append(1.0)
            negatives.append(f"영업이익 급감 {operating_yoy:.1%}")
    if margin_change is not None:
        if margin_change >= 3.0:
            scores.append(5.0)
            positives.append(f"영업이익률 {margin_change:+.1f}%p 개선")
        elif margin_change > 0:
            scores.append(4.0)
            positives.append(f"영업이익률 {margin_change:+.1f}%p 개선")
        elif margin_change > -3.0:
            scores.append(2.5)
            negatives.append(f"영업이익률 {margin_change:+.1f}%p 둔화")
        else:
            scores.append(1.0)
            negatives.append(f"영업이익률 {margin_change:+.1f}%p 악화")
    if free_cash_flow is not None:
        scores.append(4.0 if free_cash_flow > 0 else 2.0)
        target = positives if free_cash_flow > 0 else negatives
        target.append("잉여현금흐름 양수" if free_cash_flow > 0 else "잉여현금흐름 음수")
    return ScoreResult(_mean(scores), tuple(positives), tuple(negatives))


def _quality(row: Mapping[str, object]) -> ScoreResult:
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    margin = _number(row.get("operating_margin"))
    roe = _number(row.get("roe"))
    leverage = _number(row.get("debt_to_equity"))
    conversion = _number(row.get("ocf_to_net_income"))
    if margin is not None:
        if margin >= 0.20:
            scores.append(5.0)
            positives.append(f"영업이익률 {margin:.1%}")
        elif margin > 0:
            scores.append(3.5)
            positives.append(f"영업이익률 양수 {margin:.1%}")
        else:
            scores.append(1.0)
            negatives.append(f"영업적자 마진 {margin:.1%}")
    if roe is not None:
        if roe >= 0.15:
            scores.append(5.0)
            positives.append(f"ROE {roe:.1%}")
        elif roe > 0:
            scores.append(3.0)
            positives.append(f"ROE 양수 {roe:.1%}")
        else:
            scores.append(1.0)
            negatives.append(f"ROE 음수 {roe:.1%}")
    if leverage is not None:
        if leverage <= 0.5:
            scores.append(5.0)
            positives.append(f"부채/자본 {leverage:.2f}x")
        elif leverage <= 1.5:
            scores.append(3.5)
        else:
            scores.append(1.5)
            negatives.append(f"부채/자본 {leverage:.2f}x")
    if conversion is not None:
        if conversion >= 1.0:
            scores.append(5.0)
            positives.append(f"영업현금/순이익 {conversion:.2f}x")
        elif conversion > 0:
            scores.append(3.0)
        else:
            scores.append(1.0)
            negatives.append("이익의 현금전환이 음수")
    return ScoreResult(_mean(scores), tuple(positives), tuple(negatives))


def _catalyst(row: Mapping[str, object]) -> ScoreResult:
    critical = int(_number(row.get("critical_disclosures")) or 0)
    high = int(_number(row.get("high_disclosures")) or 0)
    recent = int(_number(row.get("recent_material_disclosures")) or 0)
    positives: list[str] = []
    if critical:
        positives.append(f"중요도 critical 공시 {critical}건")
    if high:
        positives.append(f"중요도 high 공시 {high}건")
    if recent <= 0:
        return ScoreResult(2.0, (), ("최근 중요 공시가 확인되지 않음",))
    score = min(5.0, 2.5 + min(recent, 10) * 0.2 + min(critical + high, 5) * 0.1)
    return ScoreResult(score, tuple(positives), ())


def _market(row: Mapping[str, object]) -> ScoreResult:
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    return_20 = _number(row.get("return_20"))
    price_to_sma = _number(row.get("price_to_sma_20"))
    rank = _number(row.get("relative_strength_rank_20"))
    trend = _number(row.get("trend_direction_20"))
    if return_20 is not None:
        if return_20 >= 0.10:
            scores.append(5.0)
            positives.append(f"20일 수익률 {return_20:.1%}")
        elif return_20 > 0:
            scores.append(4.0)
            positives.append(f"20일 수익률 양수 {return_20:.1%}")
        elif return_20 > -0.10:
            scores.append(2.5)
            negatives.append(f"20일 수익률 {return_20:.1%}")
        else:
            scores.append(1.0)
            negatives.append(f"20일 약세 {return_20:.1%}")
    if price_to_sma is not None:
        scores.append(4.0 if price_to_sma >= 0 else 2.0)
        target = positives if price_to_sma >= 0 else negatives
        target.append(f"20일선 대비 {price_to_sma:+.1%}")
    if rank is not None:
        scores.append(1.0 + 4.0 * rank)
        if rank >= 0.75:
            positives.append(f"상대강도 순위 {rank:.0%}")
        elif rank <= 0.25:
            negatives.append(f"상대강도 순위 {rank:.0%}")
    if trend is not None:
        scores.append(4.0 if trend > 0 else 2.0 if trend < 0 else 3.0)
    return ScoreResult(_mean(scores), tuple(positives), tuple(negatives))


def _macro(regimes: Mapping[str, str], exposure: CompanyExposure | None) -> ScoreResult:
    if exposure is None:
        return ScoreResult(None, (), ("기업별 거시 민감도 설정 없음",))
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    if exposure.export_fx_sensitivity is not None:
        regime = regimes.get("usd_krw")
        sensitivity = exposure.export_fx_sensitivity
        if regime == "krw_weakening":
            score, text = 3.0 + sensitivity * 1.5, "원화 약세와 수출 민감도"
        elif regime == "krw_strengthening":
            score, text = 3.0 - sensitivity * 1.5, "원화 강세와 수출 민감도"
        else:
            score, text = 3.0, "환율 중립 국면"
        scores.append(_clamp(score))
        (positives if score >= 3.0 else negatives).append(text)
    if exposure.rate_duration_sensitivity is not None:
        regime = regimes.get("kr_base_rate")
        sensitivity = exposure.rate_duration_sensitivity
        if regime == "easing_last_move":
            score, text = 3.0 + sensitivity * 1.5, "금리 인하 방향과 듀레이션 민감도"
        elif regime == "tightening_last_move":
            score, text = 3.0 - sensitivity * 1.5, "금리 인상 방향과 듀레이션 민감도"
        else:
            score, text = 3.0, "기준금리 관측구간 동결"
        scores.append(_clamp(score))
        (positives if score >= 3.0 else negatives).append(text)
    return ScoreResult(_mean(scores), tuple(positives), tuple(negatives))


def _composite(components: Mapping[str, float | None]) -> tuple[float | None, float]:
    weighted = 0.0
    available = 0.0
    for name, weight in COMPONENT_WEIGHTS.items():
        score = components.get(name)
        if score is not None:
            weighted += score * weight
            available += weight
    coverage = available / sum(COMPONENT_WEIGHTS.values())
    return (weighted / available if available else None), coverage


def load_company_exposures(path: str | Path | None) -> dict[str, CompanyExposure]:
    if path is None:
        return {}
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("companies"), dict):
        raise ValueError("Company exposure config must contain a companies object")
    companies = cast(Mapping[object, object], payload["companies"])
    result: dict[str, CompanyExposure] = {}
    for raw_ticker, raw_value in companies.items():
        ticker = str(raw_ticker).strip().zfill(6)
        if not isinstance(raw_value, dict):
            raise ValueError(f"Company exposure entry must be an object: {ticker}")
        values = cast(Mapping[str, object], raw_value)
        result[ticker] = CompanyExposure(
            sector=str(values["sector"]).strip() if values.get("sector") else None,
            export_fx_sensitivity=(
                float(cast(float | int, values["export_fx_sensitivity"]))
                if values.get("export_fx_sensitivity") is not None
                else None
            ),
            rate_duration_sensitivity=(
                float(cast(float | int, values["rate_duration_sensitivity"]))
                if values.get("rate_duration_sensitivity") is not None
                else None
            ),
        )
    return result


def build_scorecards(
    financial_kpis: pd.DataFrame,
    disclosure_summary: pd.DataFrame,
    macro_regime: pd.DataFrame,
    market_context: pd.DataFrame,
    exposures: Mapping[str, CompanyExposure],
    policy: DecisionPolicy,
) -> pd.DataFrame:
    regimes = {
        str(raw["series_id"]): str(raw["regime"])
        for raw in macro_regime.to_dict(orient="records")
    }
    sources: list[tuple[str, pd.DataFrame]] = [
        ("financial", financial_kpis),
        ("disclosure", disclosure_summary),
        ("market", market_context),
    ]
    indexed: dict[str, dict[str, Mapping[str, object]]] = {}
    for name, frame in sources:
        indexed[name] = {
            str(raw["ticker"]): cast(Mapping[str, object], raw)
            for raw in frame.to_dict(orient="records")
        }
    tickers = sorted(set().union(*(set(values) for values in indexed.values())))
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        earnings = _earnings(indexed["financial"].get(ticker, {}))
        quality = _quality(indexed["financial"].get(ticker, {}))
        catalyst = _catalyst(indexed["disclosure"].get(ticker, {}))
        market = _market(indexed["market"].get(ticker, {}))
        macro = _macro(regimes, exposures.get(ticker))
        components = {
            "earnings_momentum_score": earnings.score,
            "financial_quality_score": quality.score,
            "catalyst_score": catalyst.score,
            "market_timing_score": market.score,
            "macro_fit_score": macro.score,
            "valuation_score": None,
        }
        composite, coverage = _composite(components)
        if composite is None or coverage < policy.minimum_coverage:
            state, action = "insufficient_data", "research_gap"
        elif composite >= policy.positive_threshold:
            state = "positive_setup"
            action = (
                "fundamental_positive_timing_confirmed"
                if market.score is not None and market.score >= 3.2
                else "fundamental_positive_wait_for_timing"
            )
        elif composite >= policy.mixed_threshold:
            state, action = "mixed_setup", "selective_or_wait"
        else:
            state, action = "negative_setup", "avoid_or_reduce_candidate"
        positives = [
            *earnings.positives,
            *quality.positives,
            *catalyst.positives,
            *market.positives,
            *macro.positives,
        ]
        negatives = [
            *earnings.negatives,
            *quality.negatives,
            *catalyst.negatives,
            *market.negatives,
            *macro.negatives,
            "밸류에이션·컨센서스 데이터 미연결",
        ]
        exposure = exposures.get(ticker)
        rows.append(
            {
                "ticker": ticker,
                "sector": exposure.sector if exposure is not None else None,
                **components,
                "composite_score": composite,
                "score_coverage": coverage,
                "decision_state": state,
                "action_bias": action,
                "positive_evidence": json.dumps(positives, ensure_ascii=False),
                "opposing_evidence": json.dumps(negatives, ensure_ascii=False),
                "invalidation_triggers": json.dumps(
                    [
                        "영업이익 YoY가 0% 이하로 전환",
                        "영업이익률이 추가로 3%p 이상 악화",
                        "20일 수익률 -10% 이하이면서 20일선 하회",
                        "핵심 촉매의 지연·취소 또는 부정적 정정공시",
                    ],
                    ensure_ascii=False,
                ),
                "valuation_status": "not_available",
            }
        )
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def _fmt_pct(value: object) -> str:
    number = _number(value)
    return f"{number:.1%}" if number is not None else "N/A"


def _fmt_score(value: object) -> str:
    number = _number(value)
    return f"{number:.2f}/5" if number is not None else "미평가"


def _decode(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    parsed: object = json.loads(value)
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def build_report(
    evaluation_date: date,
    scorecards: pd.DataFrame,
    financial_kpis: pd.DataFrame,
    catalysts: pd.DataFrame,
    macro_regime: pd.DataFrame,
    market_context: pd.DataFrame,
    warnings: tuple[str, ...],
) -> str:
    financial = {
        str(raw["ticker"]): cast(Mapping[str, object], raw)
        for raw in financial_kpis.to_dict(orient="records")
    }
    markets = {
        str(raw["ticker"]): cast(Mapping[str, object], raw)
        for raw in market_context.to_dict(orient="records")
    }
    lines = [
        "# Alpha Cycle 투자 의사결정 리포트",
        "",
        f"- 기준일: {evaluation_date.isoformat()}",
        "- 밸류에이션·컨센서스 미연결 시 최종 매수 판단이 아닌 의사결정 보조",
        "",
        "## 거시 국면",
        "",
    ]
    for raw in macro_regime.to_dict(orient="records"):
        lines.append(
            f"- {raw['series_id']}: {raw['regime']} / 최신값 {raw['latest_value']} "
            f"({raw['latest_date']})"
        )
    for raw in scorecards.to_dict(orient="records"):
        score = cast(Mapping[str, object], raw)
        ticker = str(score["ticker"])
        fin = financial.get(ticker, {})
        market = markets.get(ticker, {})
        ticker_catalysts = catalysts.loc[catalysts["ticker"] == ticker].head(8)
        lines.extend(
            [
                "",
                f"## {ticker}",
                "",
                "### 1. 핵심 결론",
                "",
                f"- 상태: **{score['decision_state']}**",
                f"- 실행 편향: `{score['action_bias']}`",
                f"- 종합점수: {_fmt_score(score.get('composite_score'))}",
                f"- 데이터 커버리지: {_fmt_pct(score.get('score_coverage'))}",
                "- 밸류에이션: 미평가",
                "",
                "### 2. 실적과 재무",
                "",
                f"- 매출 YoY: {_fmt_pct(fin.get('revenue_yoy'))}",
                f"- 영업이익 YoY: {_fmt_pct(fin.get('operating_income_yoy'))}",
                f"- 영업이익률: {_fmt_pct(fin.get('operating_margin'))}",
                f"- 영업이익률 변화: {fin.get('operating_margin_change_pp', 'N/A')}%p",
                f"- ROE: {_fmt_pct(fin.get('roe'))}",
                f"- FCF: {fin.get('free_cash_flow', 'N/A')}",
                "",
                "### 3. 시장 타이밍",
                "",
                f"- 20일 수익률: {_fmt_pct(market.get('return_20'))}",
                f"- 60일 수익률: {_fmt_pct(market.get('return_60'))}",
                f"- 20일선 대비: {_fmt_pct(market.get('price_to_sma_20'))}",
                f"- 60일 최대낙폭: {_fmt_pct(market.get('max_drawdown_60'))}",
                "",
                "### 4. 최근 핵심 공시",
                "",
            ]
        )
        if ticker_catalysts.empty:
            lines.append("- 최근 high/critical 공시 없음")
        else:
            for event in ticker_catalysts.to_dict(orient="records"):
                lines.append(
                    f"- {event['receipt_date']} [{event['priority']}] {event['report_name']}"
                )
        lines.extend(
            [
                "",
                "### 5. 반대 논리",
                "",
                *[f"- {item}" for item in _decode(score.get("opposing_evidence"))],
                "",
                "### 6. 시나리오",
                "",
                "- Bull: 이익 성장·마진 개선·핵심 촉매·상대강도가 함께 유지",
                "- Base: 현재 실적 성장률과 마진·환율·가격 추세가 대체로 유지",
                "- Bear: 이익 둔화·마진 압박·촉매 지연·20일선 하회가 동시 발생",
                "",
                "### 7. 투자 논리 폐기 조건",
                "",
                *[f"- {item}" for item in _decode(score.get("invalidation_triggers"))],
            ]
        )
    if warnings:
        lines.extend(["", "## 데이터 경고", "", *[f"- {item}" for item in warnings]])
    return "\n".join(lines).rstrip() + "\n"
