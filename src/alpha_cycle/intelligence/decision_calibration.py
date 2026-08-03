"""Calibration guards for decision playbooks and report interpretation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import cast

import pandas as pd

_EXTERNAL_EVIDENCE_GAPS = (
    "컨센서스·실적 추정치 상향·하향 데이터 미연결",
    "산업 가격·재고·공급·설비투자 사이클 데이터 미연결",
    "기관·외국인 수급 데이터 미연결",
    "향후 촉매의 확정 일정·시장 기대치 데이터 미연결",
    "글로벌 비교기업과 과거 밸류에이션 밴드 미연결",
)


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
    return json.dumps(
        list(dict.fromkeys(item.strip() for item in values if item.strip())),
        ensure_ascii=False,
    )


def _ticker_events(
    catalysts: pd.DataFrame,
    ticker: str,
) -> list[Mapping[str, object]]:
    if catalysts.empty or "ticker" not in catalysts.columns:
        return []
    company = catalysts.loc[
        catalysts["ticker"].astype(str).str.zfill(6).eq(ticker)
    ]
    return [
        cast(Mapping[str, object], raw)
        for raw in company.to_dict(orient="records")
    ]


def _event_age_days(event: Mapping[str, object], evaluation_date: date) -> int | None:
    raw_age = event.get("age_days")
    if isinstance(raw_age, (int, float)) and not isinstance(raw_age, bool):
        return int(raw_age)
    raw_date = event.get("receipt_date")
    try:
        receipt_date = (
            raw_date
            if isinstance(raw_date, date)
            else date.fromisoformat(str(raw_date))
        )
    except ValueError:
        return None
    return (evaluation_date - receipt_date).days


def _calibrated_review_priority(
    score: Mapping[str, object],
    events: list[Mapping[str, object]],
    evaluation_date: date,
) -> str:
    categories = {str(event.get("category", "")) for event in events}
    state = str(score.get("decision_state", "insufficient_data"))
    if "operational_risk" in categories:
        return "urgent"
    recent_correction = any(
        bool(event.get("is_correction", False))
        and (age := _event_age_days(event, evaluation_date)) is not None
        and 0 <= age <= 30
        for event in events
    )
    if recent_correction or state in {"negative_setup", "insufficient_data"}:
        return "high"
    if events or state == "positive_setup":
        return "normal"
    return "low"


def calibrate_decision_scorecards(
    scorecards: pd.DataFrame,
    catalysts: pd.DataFrame,
    *,
    evaluation_date: date,
) -> pd.DataFrame:
    """Correct priority inflation and expose material external-data gaps."""

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    rows: list[dict[str, object]] = []
    for raw in result.to_dict(orient="records"):
        row = {str(key): value for key, value in raw.items()}
        ticker = str(row["ticker"])
        events = _ticker_events(catalysts, ticker)
        gaps = _decode_list(row.get("evidence_gaps"))
        gaps.extend(_EXTERNAL_EVIDENCE_GAPS)
        if any(bool(event.get("is_correction", False)) for event in events):
            gaps.append("정정공시 본문·변경 수치·투자 영향 미분석")
        valuation_status = str(row.get("valuation_status", "not_available"))
        if valuation_status == "insufficient_peer_universe":
            gaps.append("상대 밸류에이션 비교기업 수 부족")
        row["review_priority"] = _calibrated_review_priority(
            row,
            events,
            evaluation_date,
        )
        row["evidence_gaps"] = _json_list(gaps)
        row["evidence_scope_status"] = "partial_external_data"
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def clarify_report_coverage(report: str) -> str:
    """Prevent score-component coverage from being read as total research completeness."""

    clarified = report.replace(
        "- 데이터 커버리지:",
        "- 연결 점수 항목 커버리지:",
    )
    notices = (
        "- 밸류에이션 연결·컨센서스 미연결; 최종 매수 판단이 아닌 의사결정 보조",
        "- 밸류에이션·컨센서스 미연결 시 최종 매수 판단이 아닌 의사결정 보조",
    )
    for notice in notices:
        if notice in clarified:
            clarified = clarified.replace(
                notice,
                notice
                + "\n- 점수 항목 커버리지는 전체 투자정보 완성도가 아니라 "
                "현재 연결된 점수 입력의 가용 비중",
                1,
            )
            break
    return clarified


__all__ = [
    "calibrate_decision_scorecards",
    "clarify_report_coverage",
]
