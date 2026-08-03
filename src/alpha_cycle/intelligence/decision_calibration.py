"""Calibration guards for decision playbooks and report interpretation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import cast

import pandas as pd

_EXTERNAL_EVIDENCE_GAPS = (
    "컨센서스·실적 추정치 상향·하향 데이터 미연결",
    "산업 가격·재고·공급·설비투자 사이클 데이터 미연결",
    "기관·외국인 수급 데이터 미연결",
    "향후 촉매의 확정 일정·시장 기대치 데이터 미연결",
    "글로벌 비교기업과 과거 밸류에이션 밴드 미연결",
)
_VALUATION_GAP_PREFIXES = (
    "밸류에이션 미평가",
    "밸류에이션 근거 불완전:",
    "상대 밸류에이션 비교기업 수 부족",
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


def _receipt_date(value: object) -> date | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _event_age_days(event: Mapping[str, object], evaluation_date: date) -> int | None:
    receipt_date = _receipt_date(event.get("receipt_date"))
    if receipt_date is not None:
        return (evaluation_date - receipt_date).days
    raw_age = event.get("age_days")
    if isinstance(raw_age, (int, float)) and not isinstance(raw_age, bool):
        return int(raw_age)
    return None


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


def _whole_number(value: object) -> int | None:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        return None
    return int(converted)


def _calibrated_evidence_gaps(
    row: Mapping[str, object],
    events: list[Mapping[str, object]],
) -> list[str]:
    gaps = _decode_list(row.get("evidence_gaps"))
    gaps.extend(_EXTERNAL_EVIDENCE_GAPS)
    if any(bool(event.get("is_correction", False)) for event in events):
        gaps.append("정정공시 본문·변경 수치·투자 영향 미분석")

    valuation_status = str(row.get("valuation_status", "not_available"))
    if valuation_status == "insufficient_peer_universe":
        gaps = [
            item
            for item in gaps
            if not item.startswith(_VALUATION_GAP_PREFIXES)
        ]
        peer_count = _whole_number(row.get("valuation_peer_count"))
        peer_minimum = _whole_number(row.get("valuation_peer_minimum"))
        if peer_count is not None and peer_minimum is not None:
            gaps.append(
                "상대 밸류에이션 비교기업 수 부족 "
                f"({peer_count}개/최소 {peer_minimum}개)"
            )
        else:
            gaps.append("상대 밸류에이션 비교기업 수 부족")
    return gaps


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
        row["review_priority"] = _calibrated_review_priority(
            row,
            events,
            evaluation_date,
        )
        row["evidence_gaps"] = _json_list(
            _calibrated_evidence_gaps(row, events)
        )
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


def clarify_valuation_report(
    report: str,
    valuation_metrics: pd.DataFrame,
) -> str:
    """Replace generic score language with the actual peer-universe limitation."""

    if valuation_metrics.empty or "ticker" not in valuation_metrics.columns:
        return report
    lookup = {
        str(raw["ticker"]).zfill(6): {str(key): value for key, value in raw.items()}
        for raw in valuation_metrics.to_dict(orient="records")
    }
    lines: list[str] = []
    in_valuation_section = False
    current_ticker: str | None = None
    generic_explanation = "- 점수는 완전한 기업끼리의 상대순위를 중립값으로 축소한 값"
    for line in report.splitlines():
        if line == "## 밸류에이션 및 다기간 실적":
            in_valuation_section = True
            current_ticker = None
        elif line.startswith("## ") and in_valuation_section:
            in_valuation_section = False
            current_ticker = None
        elif in_valuation_section and line.startswith("### "):
            current_ticker = line.removeprefix("### ").strip().zfill(6)

        if (
            in_valuation_section
            and line == generic_explanation
            and current_ticker in lookup
        ):
            metric = lookup[current_ticker]
            if str(metric.get("valuation_status")) == "insufficient_peer_universe":
                peer_count = _whole_number(metric.get("valuation_peer_count"))
                peer_minimum = _whole_number(metric.get("valuation_peer_minimum"))
                if peer_count is not None and peer_minimum is not None:
                    lines.append(
                        "- 상대 점수 미산출: 비교기업 "
                        f"{peer_count}개 / 최소 {peer_minimum}개 필요"
                    )
                    continue
        lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "calibrate_decision_scorecards",
    "clarify_report_coverage",
    "clarify_valuation_report",
]
