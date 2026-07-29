"""Integrated, explainable investment-decision snapshots from local source snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import yaml

from alpha_cycle.intelligence.decision_features import (
    build_macro_regime,
    build_market_context,
    classify_disclosures,
    extract_financial_kpis,
)

DECISION_SCHEMA_VERSION = 1
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
class InvestmentDecisionSnapshot:
    captured_at: datetime
    evaluation_date: date
    research_snapshot_id: str
    market_snapshot_id: str
    policy: DecisionPolicy
    financial_kpis: pd.DataFrame
    financial_mapping: pd.DataFrame
    disclosure_events: pd.DataFrame
    catalysts: pd.DataFrame
    disclosure_summary: pd.DataFrame
    macro_regime: pd.DataFrame
    market_context: pd.DataFrame
    scorecards: pd.DataFrame
    decision_records: pd.DataFrame
    report_markdown: str
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        for value, name in (
            (self.research_snapshot_id, "research_snapshot_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
        ):
            _validate_snapshot_id(value, name)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": DECISION_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "research_snapshot_id": self.research_snapshot_id,
            "market_snapshot_id": self.market_snapshot_id,
            "policy": {
                "recent_disclosure_days": self.policy.recent_disclosure_days,
                "positive_threshold": self.policy.positive_threshold,
                "mixed_threshold": self.policy.mixed_threshold,
                "minimum_coverage": self.policy.minimum_coverage,
            },
            "financial_kpis": _records(self.financial_kpis),
            "financial_mapping": _records(self.financial_mapping),
            "disclosure_events": _records(self.disclosure_events),
            "catalysts": _records(self.catalysts),
            "disclosure_summary": _records(self.disclosure_summary),
            "macro_regime": _records(self.macro_regime),
            "market_context": _records(self.market_context),
            "scorecards": _records(self.scorecards),
            "decision_records": _records(self.decision_records),
            "report_markdown": self.report_markdown,
            "warnings": list(self.warnings),
        }

    @property
    def snapshot_id(self) -> str:
        encoded = _canonical_json(self.payload_without_id()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


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


def _json_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("Decision snapshot values must be finite")
        return value
    if isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Decision snapshot value is not serializable: {type(value).__name__}")


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {str(key): _json_value(value) for key, value in raw.items()}
        for raw in frame.to_dict(orient="records")
    ]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_snapshot_id(value: str, field: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _read_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return cast(Mapping[str, object], payload)


def _snapshot_directory(path: str | Path) -> Path:
    result = Path(path)
    if not result.is_dir():
        raise ValueError(f"Snapshot directory does not exist: {result}")
    if not (result / "manifest.json").is_file():
        raise ValueError(f"Snapshot manifest does not exist: {result / 'manifest.json'}")
    return result


def _value(row: Mapping[str, object], name: str) -> float | None:
    raw = row.get(name)
    if raw is None or pd.isna(raw):
        return None
    try:
        result = float(raw)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _mean_score(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _clamp_score(value: float) -> float:
    return min(5.0, max(1.0, value))


def _earnings_score(row: Mapping[str, object]) -> ScoreResult:
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    revenue_yoy = _value(row, "revenue_yoy")
    operating_yoy = _value(row, "operating_income_yoy")
    margin_change = _value(row, "operating_margin_change_pp")
    fcf = _value(row, "free_cash_flow")

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
    if fcf is not None:
        scores.append(4.0 if fcf > 0 else 2.0)
        target = positives if fcf > 0 else negatives
        target.append("잉여현금흐름 양수" if fcf > 0 else "잉여현금흐름 음수")
    return ScoreResult(_mean_score(scores), tuple(positives), tuple(negatives))


def _quality_score(row: Mapping[str, object]) -> ScoreResult:
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    margin = _value(row, "operating_margin")
    roe = _value(row, "roe")
    leverage = _value(row, "debt_to_equity")
    conversion = _value(row, "ocf_to_net_income")

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
    return ScoreResult(_mean_score(scores), tuple(positives), tuple(negatives))


def _catalyst_score(row: Mapping[str, object]) -> ScoreResult:
    critical = int(_value(row, "critical_disclosures") or 0)
    high = int(_value(row, "high_disclosures") or 0)
    recent = int(_value(row, "recent_material_disclosures") or 0)
    positives: list[str] = []
    if critical > 0:
        positives.append(f"중요도 critical 공시 {critical}건")
    if high > 0:
        positives.append(f"중요도 high 공시 {high}건")
    if recent <= 0:
        return ScoreResult(2.0, (), ("최근 중요 공시가 확인되지 않음",))
    score = min(5.0, 2.5 + min(recent, 10) * 0.2 + min(critical + high, 5) * 0.1)
    return ScoreResult(score, tuple(positives), ())


def _market_score(row: Mapping[str, object]) -> ScoreResult:
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    return_20 = _value(row, "return_20")
    price_to_sma = _value(row, "price_to_sma_20")
    rs_rank = _value(row, "relative_strength_rank_20")
    trend_direction = _value(row, "trend_direction_20")

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
    if rs_rank is not None:
        scores.append(1.0 + 4.0 * rs_rank)
        if rs_rank >= 0.75:
            positives.append(f"상대강도 상위 {1.0 - rs_rank:.0%}")
        elif rs_rank <= 0.25:
            negatives.append(f"상대강도 하위 {rs_rank:.0%}")
    if trend_direction is not None:
        scores.append(4.0 if trend_direction > 0 else 2.0 if trend_direction < 0 else 3.0)
    return ScoreResult(_mean_score(scores), tuple(positives), tuple(negatives))


def _macro_score(
    regimes: Mapping[str, str],
    exposure: CompanyExposure | None,
) -> ScoreResult:
    if exposure is None:
        return ScoreResult(None, (), ("기업별 거시 민감도 설정 없음",))
    scores: list[float] = []
    positives: list[str] = []
    negatives: list[str] = []
    if exposure.export_fx_sensitivity is not None:
        fx_regime = regimes.get("usd_krw")
        sensitivity = exposure.export_fx_sensitivity
        if fx_regime == "krw_weakening":
            score = 3.0 + sensitivity * 1.5
            text = "원화 약세와 수출 민감도"
        elif fx_regime == "krw_strengthening":
            score = 3.0 - sensitivity * 1.5
            text = "원화 강세와 수출 민감도"
        else:
            score = 3.0
            text = "환율 중립 국면"
        scores.append(_clamp_score(score))
        (positives if score >= 3.0 else negatives).append(text)
    if exposure.rate_duration_sensitivity is not None:
        rate_regime = regimes.get("kr_base_rate")
        sensitivity = exposure.rate_duration_sensitivity
        if rate_regime == "easing_last_move":
            score = 3.0 + sensitivity * 1.5
            text = "금리 인하 방향과 듀레이션 민감도"
        elif rate_regime == "tightening_last_move":
            score = 3.0 - sensitivity * 1.5
            text = "금리 인상 방향과 듀레이션 민감도"
        else:
            score = 3.0
            text = "기준금리 관측구간 동결"
        scores.append(_clamp_score(score))
        (positives if score >= 3.0 else negatives).append(text)
    return ScoreResult(_mean_score(scores), tuple(positives), tuple(negatives))


def _component_composite(components: Mapping[str, float | None]) -> tuple[float | None, float]:
    weighted = 0.0
    available_weight = 0.0
    total_weight = sum(COMPONENT_WEIGHTS.values())
    for name, weight in COMPONENT_WEIGHTS.items():
        score = components.get(name)
        if score is None:
            continue
        weighted += score * weight
        available_weight += weight
    coverage = available_weight / total_weight
    return (weighted / available_weight if available_weight > 0 else None), coverage


def load_company_exposures(path: str | Path | None) -> dict[str, CompanyExposure]:
    """Load explicit company macro assumptions; absent assumptions remain unscored."""

    if path is None:
        return {}
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Company exposure config must be an object")
    companies = payload.get("companies")
    if not isinstance(companies, dict):
        raise ValueError("Company exposure config must contain a companies object")
    result: dict[str, CompanyExposure] = {}
    for raw_ticker, raw_value in companies.items():
        ticker = str(raw_ticker).strip().zfill(6)
        if not isinstance(raw_value, dict):
            raise ValueError(f"Company exposure entry must be an object: {ticker}")
        mapping = cast(Mapping[str, object], raw_value)
        result[ticker] = CompanyExposure(
            sector=(str(mapping["sector"]).strip() if mapping.get("sector") else None),
            export_fx_sensitivity=(
                float(mapping["export_fx_sensitivity"])
                if mapping.get("export_fx_sensitivity") is not None
                else None
            ),
            rate_duration_sensitivity=(
                float(mapping["rate_duration_sensitivity"])
                if mapping.get("rate_duration_sensitivity") is not None
                else None
            ),
        )
    return result


def _scorecards(
    financial_kpis: pd.DataFrame,
    disclosure_summary: pd.DataFrame,
    macro_regime: pd.DataFrame,
    market_context: pd.DataFrame,
    exposures: Mapping[str, CompanyExposure],
    policy: DecisionPolicy,
) -> pd.DataFrame:
    regimes = {
        str(row["series_id"]): str(row["regime"])
        for row in macro_regime.to_dict(orient="records")
    }
    financial = {
        str(row["ticker"]): cast(Mapping[str, object], row)
        for row in financial_kpis.to_dict(orient="records")
    }
    disclosures = {
        str(row["ticker"]): cast(Mapping[str, object], row)
        for row in disclosure_summary.to_dict(orient="records")
    }
    markets = {
        str(row["ticker"]): cast(Mapping[str, object], row)
        for row in market_context.to_dict(orient="records")
    }
    tickers = sorted(set(financial) | set(disclosures) | set(markets))
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        financial_row = financial.get(ticker, {})
        disclosure_row = disclosures.get(ticker, {})
        market_row = markets.get(ticker, {})
        earnings = _earnings_score(financial_row)
        quality = _quality_score(financial_row)
        catalyst = _catalyst_score(disclosure_row)
        market = _market_score(market_row)
        macro = _macro_score(regimes, exposures.get(ticker))
        components = {
            "earnings_momentum_score": earnings.score,
            "financial_quality_score": quality.score,
            "catalyst_score": catalyst.score,
            "market_timing_score": market.score,
            "macro_fit_score": macro.score,
            "valuation_score": None,
        }
        composite, coverage = _component_composite(components)
        if composite is None or coverage < policy.minimum_coverage:
            decision_state = "insufficient_data"
            action_bias = "research_gap"
        elif composite >= policy.positive_threshold:
            decision_state = "positive_setup"
            action_bias = (
                "fundamental_positive_timing_confirmed"
                if market.score is not None and market.score >= 3.2
                else "fundamental_positive_wait_for_timing"
            )
        elif composite >= policy.mixed_threshold:
            decision_state = "mixed_setup"
            action_bias = "selective_or_wait"
        else:
            decision_state = "negative_setup"
            action_bias = "avoid_or_reduce_candidate"

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
        invalidation = [
            "영업이익 YoY가 0% 이하로 전환",
            "영업이익률이 추가로 3%p 이상 악화",
            "20일 수익률 -10% 이하이면서 20일선 하회",
            "핵심 촉매의 지연·취소 또는 부정적 정정공시",
        ]
        row: dict[str, object] = {
            "ticker": ticker,
            "sector": exposures.get(ticker).sector if ticker in exposures else None,
            **components,
            "composite_score": composite,
            "score_coverage": coverage,
            "decision_state": decision_state,
            "action_bias": action_bias,
            "positive_evidence": json.dumps(positives, ensure_ascii=False),
            "opposing_evidence": json.dumps(negatives, ensure_ascii=False),
            "invalidation_triggers": json.dumps(invalidation, ensure_ascii=False),
            "valuation_status": "not_available",
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def _fmt_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.1%}"


def _fmt_score(value: object) -> str:
    if value is None or pd.isna(value):
        return "미평가"
    return f"{float(value):.2f}/5"


def _decode_list(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    parsed: object = json.loads(value)
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _report(
    evaluation_date: date,
    scorecards: pd.DataFrame,
    financial_kpis: pd.DataFrame,
    catalysts: pd.DataFrame,
    macro_regime: pd.DataFrame,
    market_context: pd.DataFrame,
    warnings: tuple[str, ...],
) -> str:
    financial = financial_kpis.set_index("ticker", drop=False)
    market = market_context.set_index("ticker", drop=False)
    lines = [
        "# Alpha Cycle 투자 의사결정 리포트",
        "",
        f"- 기준일: {evaluation_date.isoformat()}",
        "- 성격: 데이터 기반 의사결정 보조. 밸류에이션·컨센서스 미연결 시 최종 매수 판단 불가",
        "",
        "## 거시 국면",
        "",
    ]
    if macro_regime.empty:
        lines.append("- 사용 가능한 거시 시계열이 없습니다.")
    else:
        for raw in macro_regime.to_dict(orient="records"):
            lines.append(
                f"- {raw['series_id']}: {raw['regime']} / 최신값 {raw['latest_value']} "
                f"({raw['latest_date']})"
            )
    for raw_score in scorecards.to_dict(orient="records"):
        score = cast(Mapping[str, object], raw_score)
        ticker = str(score["ticker"])
        fin = cast(Mapping[str, object], financial.loc[ticker].to_dict()) if ticker in financial.index else {}
        mkt = cast(Mapping[str, object], market.loc[ticker].to_dict()) if ticker in market.index else {}
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
                "- 밸류에이션: 미평가 — 주식수·시가총액·컨센서스 계층 필요",
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
                f"- 20일 수익률: {_fmt_pct(mkt.get('return_20'))}",
                f"- 60일 수익률: {_fmt_pct(mkt.get('return_60'))}",
                f"- 20일선 대비: {_fmt_pct(mkt.get('price_to_sma_20'))}",
                f"- 60일 최대낙폭: {_fmt_pct(mkt.get('max_drawdown_60'))}",
                "",
                "### 4. 최근 핵심 공시",
                "",
            ]
        )
        if ticker_catalysts.empty:
            lines.append("- 최근 high/critical 공시 없음")
        else:
            for catalyst in ticker_catalysts.to_dict(orient="records"):
                lines.append(
                    f"- {catalyst['receipt_date']} [{catalyst['priority']}] "
                    f"{catalyst['report_name']}"
                )
        lines.extend(
            [
                "",
                "### 5. 반대 논리",
                "",
                *[f"- {item}" for item in _decode_list(score.get("opposing_evidence"))],
                "",
                "### 6. 시나리오",
                "",
                "- Bull: 영업이익 성장과 마진 개선이 이어지고, 핵심 공시가 실제 실적으로 연결되며 상대강도가 유지되는 경우",
                "- Base: 현재 실적 성장률과 마진·환율·가격 추세가 대체로 유지되는 경우",
                "- Bear: 영업이익 둔화, 마진 압박, 촉매 지연, 20일선 하회가 동시에 나타나는 경우",
                "",
                "### 7. 투자 논리 폐기 조건",
                "",
                *[f"- {item}" for item in _decode_list(score.get("invalidation_triggers"))],
            ]
        )
    if warnings:
        lines.extend(["", "## 데이터 경고", "", *[f"- {item}" for item in warnings]])
    return "\n".join(lines).rstrip() + "\n"


def build_investment_decision_snapshot(
    research_snapshot: str | Path,
    market_snapshot: str | Path,
    *,
    benchmark: str | None = None,
    exposures: Mapping[str, CompanyExposure] | None = None,
    policy: DecisionPolicy = DecisionPolicy(),
    now: datetime | None = None,
) -> InvestmentDecisionSnapshot:
    """Build one integrated decision snapshot from immutable local source snapshots."""

    research_dir = _snapshot_directory(research_snapshot)
    market_dir = _snapshot_directory(market_snapshot)
    research_manifest = _read_json(research_dir / "manifest.json")
    market_manifest = _read_json(market_dir / "manifest.json")
    research_id = str(research_manifest.get("snapshot_id", ""))
    market_id = str(market_manifest.get("snapshot_id", ""))
    _validate_snapshot_id(research_id, "research_snapshot_id")
    _validate_snapshot_id(market_id, "market_snapshot_id")
    linked_market_id = str(research_manifest.get("market_snapshot_id", ""))
    if linked_market_id and linked_market_id != market_id:
        raise ValueError("Research snapshot is linked to a different market snapshot")
    evaluation_date = date.fromisoformat(str(research_manifest.get("evaluation_date", "")))

    raw_opendart = _read_json(research_dir / "raw_opendart.json")
    financial_kpis, financial_mapping, financial_warnings = extract_financial_kpis(
        raw_opendart
    )
    disclosures = pd.read_csv(research_dir / "disclosures.csv")
    events, catalysts, disclosure_summary = classify_disclosures(
        disclosures,
        evaluation_date=evaluation_date,
        recent_days=policy.recent_disclosure_days,
    )
    macro = pd.read_csv(research_dir / "macro.csv")
    macro_regime = build_macro_regime(macro)
    candles = pd.read_csv(market_dir / "candles.csv")
    technical = pd.read_csv(market_dir / "technical_features.csv")
    market_context = build_market_context(candles, technical, benchmark=benchmark)

    ticker_sets = {
        "financial": set(financial_kpis.get("ticker", pd.Series(dtype=str)).astype(str)),
        "market": set(market_context.get("ticker", pd.Series(dtype=str)).astype(str)),
    }
    if ticker_sets["financial"] != ticker_sets["market"]:
        raise ValueError(
            "Financial and market snapshot ticker sets differ: "
            f"financial={sorted(ticker_sets['financial'])}, market={sorted(ticker_sets['market'])}"
        )

    exposure_map = dict(exposures or {})
    scorecards = _scorecards(
        financial_kpis,
        disclosure_summary,
        macro_regime,
        market_context,
        exposure_map,
        policy,
    )
    price_lookup = market_context.set_index("ticker")["last_price"].to_dict()
    decision_records = scorecards.loc[
        :, [
            "ticker",
            "decision_state",
            "action_bias",
            "composite_score",
            "score_coverage",
        ]
    ].copy()
    decision_records.insert(1, "evaluation_date", evaluation_date)
    decision_records.insert(
        2,
        "reference_price",
        decision_records["ticker"].map(price_lookup),
    )

    warnings = [*financial_warnings]
    warnings.append("valuation_and_consensus_not_available")
    if not exposure_map:
        warnings.append("company_macro_exposures_not_configured")
    report = _report(
        evaluation_date,
        scorecards,
        financial_kpis,
        catalysts,
        macro_regime,
        market_context,
        tuple(warnings),
    )
    captured_at = now or datetime.now(UTC)
    return InvestmentDecisionSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        research_snapshot_id=research_id,
        market_snapshot_id=market_id,
        policy=policy,
        financial_kpis=financial_kpis,
        financial_mapping=financial_mapping,
        disclosure_events=events,
        catalysts=catalysts,
        disclosure_summary=disclosure_summary,
        macro_regime=macro_regime,
        market_context=market_context,
        scorecards=scorecards,
        decision_records=decision_records,
        report_markdown=report,
        warnings=tuple(warnings),
    )


def write_investment_decision_snapshot(
    output_root: str | Path,
    snapshot: InvestmentDecisionSnapshot,
) -> tuple[Path, ...]:
    """Atomically write one content-addressed decision-intelligence snapshot."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    names = (
        "manifest.json",
        "financial_kpis.csv",
        "financial_kpi_mapping.csv",
        "disclosure_events.csv",
        "catalysts.csv",
        "disclosure_summary.csv",
        "macro_regime.csv",
        "market_context.csv",
        "scorecards.csv",
        "decision_records.csv",
        "report.md",
    )
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if manifest.get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("Existing decision snapshot conflicts with requested snapshot")
        return tuple(directory / name for name in names)
    temporary = root / f".{directory.name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir()
    try:
        frames = {
            "financial_kpis.csv": snapshot.financial_kpis,
            "financial_kpi_mapping.csv": snapshot.financial_mapping,
            "disclosure_events.csv": snapshot.disclosure_events,
            "catalysts.csv": snapshot.catalysts,
            "disclosure_summary.csv": snapshot.disclosure_summary,
            "macro_regime.csv": snapshot.macro_regime,
            "market_context.csv": snapshot.market_context,
            "scorecards.csv": snapshot.scorecards,
            "decision_records.csv": snapshot.decision_records,
        }
        for name, frame in frames.items():
            frame.to_csv(temporary / name, index=False)
        (temporary / "report.md").write_text(snapshot.report_markdown, encoding="utf-8")
        manifest = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "research_snapshot_id": snapshot.research_snapshot_id,
            "market_snapshot_id": snapshot.market_snapshot_id,
            "symbols": snapshot.scorecards["ticker"].astype(str).tolist(),
            "decision_states": snapshot.scorecards["decision_state"].value_counts().to_dict(),
            "warnings": list(snapshot.warnings),
            "valuation_available": False,
            "consensus_available": False,
            "order_api_enabled": False,
            "files": list(names[1:]),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return tuple(directory / name for name in names)
