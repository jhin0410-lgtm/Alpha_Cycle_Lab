"""Deterministic execution playbooks derived from decision snapshot evidence.

The playbook converts already-computed scores, financial KPIs, disclosure catalysts,
and market context into explicit monitoring and action conditions. It does not predict
future event dates, generate target prices, or enable order submission.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date
from typing import cast

import pandas as pd

_PLAYBOOK_COLUMNS = (
    "playbook_as_of",
    "action_readiness",
    "review_priority",
    "known_catalysts",
    "entry_conditions",
    "add_conditions",
    "reduce_conditions",
    "exit_conditions",
    "monitor_0_3m",
    "monitor_3_6m",
    "monitor_6_12m",
    "evidence_gaps",
    "playbook_basis",
)

_COMPONENT_LABELS = {
    "earnings_momentum_score": "이익 모멘텀",
    "financial_quality_score": "재무 품질",
    "catalyst_score": "촉매",
    "market_timing_score": "시장 타이밍",
    "macro_fit_score": "거시 적합도",
    "valuation_score": "밸류에이션",
}


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _decode_list(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    try:
        parsed: object = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _json_list(values: list[str]) -> str:
    deduplicated = list(dict.fromkeys(item.strip() for item in values if item.strip()))
    return json.dumps(deduplicated, ensure_ascii=False)


def _indexed(frame: pd.DataFrame) -> dict[str, Mapping[str, object]]:
    if frame.empty or "ticker" not in frame.columns:
        return {}
    return {
        str(raw["ticker"]).zfill(6): cast(Mapping[str, object], raw)
        for raw in frame.to_dict(orient="records")
    }


def _ticker_catalysts(
    catalysts: pd.DataFrame,
    ticker: str,
) -> list[Mapping[str, object]]:
    if catalysts.empty or "ticker" not in catalysts.columns:
        return []
    company = catalysts.loc[catalysts["ticker"].astype(str).str.zfill(6).eq(ticker)].copy()
    if company.empty:
        return []
    if "material_score" in company.columns and "receipt_date" in company.columns:
        company = company.sort_values(
            ["material_score", "receipt_date"],
            ascending=[False, False],
            kind="stable",
        )
    return [
        cast(Mapping[str, object], raw)
        for raw in company.head(8).to_dict(orient="records")
    ]


def _catalyst_label(event: Mapping[str, object]) -> str:
    receipt_date = str(event.get("receipt_date", "")).strip()
    category = str(event.get("category", "other")).strip() or "other"
    report_name = str(event.get("report_name", "")).strip() or "공시명 미확인"
    prefix = f"{receipt_date} " if receipt_date else ""
    return f"{prefix}[{category}] {report_name}"


def _timing_confirmed(market: Mapping[str, object]) -> bool:
    return_20 = _number(market.get("return_20"))
    price_to_sma = _number(market.get("price_to_sma_20"))
    rank = _number(market.get("relative_strength_rank_20"))
    signals = [
        return_20 is not None and return_20 > 0,
        price_to_sma is not None and price_to_sma >= 0,
        rank is not None and rank >= 0.5,
    ]
    return sum(signals) >= 2


def _readiness(
    score: Mapping[str, object],
    market: Mapping[str, object],
) -> str:
    state = str(score.get("decision_state", "insufficient_data"))
    action = str(score.get("action_bias", "research_gap"))
    valuation_status = str(score.get("valuation_status", "not_available"))
    if state == "insufficient_data" or action == "research_gap":
        return "research_gap"
    if state == "negative_setup":
        return "avoid_or_reduce_review"
    if state == "mixed_setup":
        return "watchlist_selective"
    if state == "positive_setup" and _timing_confirmed(market):
        if valuation_status in {
            "complete_peer_relative_scored",
            "complete_unscored",
        }:
            return "position_review_ready"
        return "conditional_without_complete_valuation"
    return "wait_for_timing_confirmation"


def _review_priority(
    score: Mapping[str, object],
    events: list[Mapping[str, object]],
) -> str:
    categories = {str(event.get("category", "")) for event in events}
    has_correction = any(bool(event.get("is_correction", False)) for event in events)
    state = str(score.get("decision_state", "insufficient_data"))
    if "operational_risk" in categories or has_correction:
        return "urgent"
    if state in {"negative_setup", "insufficient_data"}:
        return "high"
    if events or state == "positive_setup":
        return "normal"
    return "low"


def _entry_conditions(
    score: Mapping[str, object],
    market: Mapping[str, object],
) -> list[str]:
    state = str(score.get("decision_state", "insufficient_data"))
    readiness = _readiness(score, market)
    if state == "negative_setup":
        return [
            "신규 진입 보류",
            "영업이익과 영업이익률이 회복되고 가격 추세가 안정될 때 재평가",
        ]
    if state == "insufficient_data":
        return [
            "누락된 실적·거시·밸류에이션 근거를 보완하기 전 신규 진입 보류",
        ]
    conditions = [
        "최근 실적 또는 핵심 공시에 부정적 정정이 없을 것",
        "20일 상대강도와 20일선 방향이 동시에 악화되지 않을 것",
    ]
    if readiness == "position_review_ready":
        conditions.insert(0, "현재 긍정적 펀더멘털과 가격 추세가 다음 관찰 시점까지 유지")
    elif readiness == "conditional_without_complete_valuation":
        conditions.insert(0, "불완전한 밸류에이션을 감안해 기대수익 검증 후 제한적으로 검토")
    elif state == "mixed_setup":
        conditions.insert(0, "이익 모멘텀 또는 촉매가 추가로 확인된 뒤 선택적으로 검토")
    else:
        conditions.insert(0, "20일선 회복과 20일 수익률 양전 등 가격 확인 후 검토")
    return conditions


def _add_conditions(
    score: Mapping[str, object],
    events: list[Mapping[str, object]],
) -> list[str]:
    state = str(score.get("decision_state", "insufficient_data"))
    if state in {"negative_setup", "insufficient_data"}:
        return ["현재 상태에서는 추가매수보다 투자 논리 재검증을 우선"]
    categories = {str(event.get("category", "")) for event in events}
    conditions = [
        "다음 실적에서 영업이익 YoY와 영업이익률이 기존 투자 논리를 확인",
        "주가 상승이 거래량 또는 상대강도 개선과 동반",
    ]
    if "contract_order" in categories:
        conditions.append("수주가 실제 매출 인식 또는 수주잔고 증가로 연결")
    if "capex_investment" in categories:
        conditions.append("설비투자가 가동률·매출 성장으로 연결되고 현금흐름 훼손이 제한")
    if "capital_allocation" in categories:
        conditions.append("자사주·배당 등 자본배분 계획이 실제로 집행")
    return conditions


def _reduce_conditions(
    score: Mapping[str, object],
    financial: Mapping[str, object],
    market: Mapping[str, object],
    events: list[Mapping[str, object]],
) -> list[str]:
    conditions = [
        "20일 수익률이 -10% 이하이면서 20일선을 하회",
        "핵심 촉매가 지연·취소되거나 부정적 정정공시가 발생",
    ]
    margin_change = _number(financial.get("operating_margin_change_pp"))
    return_20 = _number(market.get("return_20"))
    valuation_score = _number(score.get("valuation_score"))
    if margin_change is not None and margin_change < 0:
        conditions.append("이미 둔화 중인 영업이익률이 다음 실적에서 추가 악화")
    else:
        conditions.append("영업이익률이 전년 대비 3%p 이상 악화")
    if return_20 is not None and return_20 < 0:
        conditions.append("현재 약세가 상대강도 하위권 고착으로 이어짐")
    if valuation_score is not None and valuation_score <= 2.5:
        conditions.append("이익 추정 상향 없이 낮은 상대 밸류에이션 점수가 지속")
    if any(str(event.get("category", "")) == "financing" for event in events):
        conditions.append("조달 규모 확대 또는 희석·이자비용 부담이 예상보다 커짐")
    return conditions


def _exit_conditions(
    score: Mapping[str, object],
    events: list[Mapping[str, object]],
) -> list[str]:
    conditions = _decode_list(score.get("invalidation_triggers"))
    if any(str(event.get("category", "")) == "operational_risk" for event in events):
        conditions.append("생산중단·영업정지·소송 등 운영 리스크가 장기화")
    conditions.extend(
        [
            "이익 모멘텀과 가격 추세가 동시에 훼손되어 원래 기대수익 경로가 사라짐",
            "현재 평가금액을 대체 투자안으로 이동했을 때 기대수익이 명확히 우월",
        ]
    )
    return conditions


def _monitoring_windows(
    financial: Mapping[str, object],
    events: list[Mapping[str, object]],
) -> tuple[list[str], list[str], list[str]]:
    categories = {str(event.get("category", "")) for event in events}
    near = ["다음 실적 공시에서 매출·영업이익 YoY와 영업이익률 확인"]
    middle = ["두 개 분기 범위에서 이익 성장과 현금흐름의 지속성 확인"]
    long = ["산업 사이클 지속성과 ROE·FCF의 구조적 개선 여부 확인"]

    for event in events[:3]:
        near.append("기존 공시 후속 확인: " + _catalyst_label(event))
    if "contract_order" in categories:
        near.append("수주 금액·계약기간·매출 인식 시점 검증")
        middle.append("수주가 매출과 영업이익으로 실제 전환되는지 확인")
    if "capex_investment" in categories:
        near.append("설비투자 집행 일정과 자금조달 방식 확인")
        middle.append("신규 설비 가동률·감가상각·마진 효과 확인")
    if "earnings" in categories:
        near.append("잠정실적과 확정실적의 정합성 및 일회성 항목 확인")
    if "capital_allocation" in categories:
        near.append("자사주·소각·배당 계획의 실제 집행 여부 확인")
    if "financing" in categories:
        near.append("희석 가능성·이자비용·자금 사용처 확인")
        middle.append("조달 이후 순차입금과 이자보상능력 변화 확인")
    if "operational_risk" in categories:
        near.append("운영 중단·소송·회생 관련 정상화 여부 우선 확인")

    inventory_growth = _number(financial.get("inventory_growth"))
    revenue_yoy = _number(financial.get("revenue_yoy"))
    receivables_growth = _number(financial.get("receivables_growth"))
    if (
        inventory_growth is not None
        and revenue_yoy is not None
        and inventory_growth > revenue_yoy + 0.10
    ):
        middle.append("매출보다 빠른 재고 증가가 정상화되는지 확인")
    if (
        receivables_growth is not None
        and revenue_yoy is not None
        and receivables_growth > revenue_yoy + 0.10
    ):
        middle.append("매출채권 증가와 현금회수 속도 확인")

    long.extend(
        [
            "성장 투자 이후 잉여현금흐름이 개선되는지 확인",
            "이익 상향 없이 밸류에이션만 확장되는 국면인지 재평가",
        ]
    )
    return near, middle, long


def _evidence_gaps(
    score: Mapping[str, object],
    events: list[Mapping[str, object]],
) -> list[str]:
    gaps = [
        f"{label} 미평가"
        for column, label in _COMPONENT_LABELS.items()
        if _number(score.get(column)) is None
    ]
    valuation_status = str(score.get("valuation_status", "not_available"))
    if valuation_status not in {
        "complete_peer_relative_scored",
        "complete_unscored",
    }:
        gaps.append(f"밸류에이션 근거 불완전: {valuation_status}")
    if not events:
        gaps.append("최근 high/critical 공시 기반 촉매가 없음")
    opposing = _decode_list(score.get("opposing_evidence"))
    if any("거시 민감도 설정 없음" in item for item in opposing):
        gaps.append("기업별 환율·금리 민감도 설정 없음")
    return gaps


def enrich_scorecards_with_playbook(
    scorecards: pd.DataFrame,
    financial_kpis: pd.DataFrame,
    catalysts: pd.DataFrame,
    market_context: pd.DataFrame,
    *,
    evaluation_date: date,
) -> pd.DataFrame:
    """Attach transparent action and monitoring conditions to each scorecard."""

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    if result["ticker"].duplicated().any():
        raise ValueError("Scorecards contain duplicate tickers")

    financial_lookup = _indexed(financial_kpis)
    market_lookup = _indexed(market_context)
    rows: list[dict[str, object]] = []
    for raw in result.to_dict(orient="records"):
        row = {str(key): value for key, value in raw.items()}
        ticker = str(row["ticker"])
        financial = financial_lookup.get(ticker, {})
        market = market_lookup.get(ticker, {})
        events = _ticker_catalysts(catalysts, ticker)
        near, middle, long = _monitoring_windows(financial, events)
        row.update(
            {
                "playbook_as_of": evaluation_date,
                "action_readiness": _readiness(row, market),
                "review_priority": _review_priority(row, events),
                "known_catalysts": _json_list(
                    [_catalyst_label(event) for event in events]
                ),
                "entry_conditions": _json_list(_entry_conditions(row, market)),
                "add_conditions": _json_list(_add_conditions(row, events)),
                "reduce_conditions": _json_list(
                    _reduce_conditions(row, financial, market, events)
                ),
                "exit_conditions": _json_list(_exit_conditions(row, events)),
                "monitor_0_3m": _json_list(near),
                "monitor_3_6m": _json_list(middle),
                "monitor_6_12m": _json_list(long),
                "evidence_gaps": _json_list(_evidence_gaps(row, events)),
                "playbook_basis": "deterministic_snapshot_rules_no_future_event_dates",
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def build_decision_records(
    scorecards: pd.DataFrame,
    *,
    evaluation_date: date,
    price_lookup: Mapping[str, object],
) -> pd.DataFrame:
    """Create compact decision records including the execution playbook."""

    required = {
        "ticker",
        "decision_state",
        "action_bias",
        "composite_score",
        "score_coverage",
        *_PLAYBOOK_COLUMNS,
    }
    missing = sorted(required - set(scorecards.columns))
    if missing:
        raise ValueError("Scorecards are missing playbook columns: " + ",".join(missing))
    columns = [
        "ticker",
        "decision_state",
        "action_bias",
        "composite_score",
        "score_coverage",
        *_PLAYBOOK_COLUMNS,
    ]
    records = scorecards.loc[:, columns].copy()
    records.insert(1, "evaluation_date", evaluation_date)
    normalized_prices = {str(key).zfill(6): value for key, value in price_lookup.items()}
    records.insert(2, "reference_price", records["ticker"].map(normalized_prices))
    if records["reference_price"].isna().any():
        raise ValueError("Decision records are missing reference prices")
    return records


def _append_list(lines: list[str], title: str, value: object) -> None:
    lines.append(f"- {title}")
    items = _decode_list(value)
    if not items:
        lines.append("  - 확인 항목 없음")
        return
    lines.extend(f"  - {item}" for item in items)


def append_execution_playbook_report(
    report: str,
    scorecards: pd.DataFrame,
) -> str:
    """Append actionable, source-bounded playbooks to the Markdown report."""

    lines = [
        report.rstrip(),
        "",
        "## 실행 플레이북",
        "",
        "- 미래 공시일·목표주가를 추정하지 않고 현재 스냅샷에서 검증 가능한 조건만 제시",
        "- 실제 주문 기능은 비활성화되어 있으며 실행 전 최신 가격·실적·공시 재확인 필요",
    ]
    for raw in scorecards.to_dict(orient="records"):
        score = cast(Mapping[str, object], raw)
        ticker = str(score.get("ticker", ""))
        lines.extend(
            [
                "",
                f"### {ticker}",
                "",
                f"- 행동 준비도: **{score.get('action_readiness', 'N/A')}**",
                f"- 재검토 우선순위: **{score.get('review_priority', 'N/A')}**",
                f"- 산출 기준: `{score.get('playbook_basis', 'N/A')}`",
            ]
        )
        _append_list(lines, "확인된 촉매", score.get("known_catalysts"))
        _append_list(lines, "진입 조건", score.get("entry_conditions"))
        _append_list(lines, "추가매수 조건", score.get("add_conditions"))
        _append_list(lines, "비중 축소 조건", score.get("reduce_conditions"))
        _append_list(lines, "청산·논리 폐기 조건", score.get("exit_conditions"))
        _append_list(lines, "0~3개월 확인 항목", score.get("monitor_0_3m"))
        _append_list(lines, "3~6개월 확인 항목", score.get("monitor_3_6m"))
        _append_list(lines, "6~12개월 확인 항목", score.get("monitor_6_12m"))
        _append_list(lines, "현재 근거 공백", score.get("evidence_gaps"))
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "append_execution_playbook_report",
    "build_decision_records",
    "enrich_scorecards_with_playbook",
]
