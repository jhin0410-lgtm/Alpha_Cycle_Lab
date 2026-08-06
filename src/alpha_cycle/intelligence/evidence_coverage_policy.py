"""Calibrate partial-evidence decision scores and report period semantics."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.decision_scoring import (
    COMPONENT_WEIGHTS,
    DecisionPolicy,
)

_NEUTRAL_SCORE = 3.0
_TICKER_HEADING = re.compile(r"^[0-9]{6}$")
_QUARTER_LINE = re.compile(r"^- 최근 분기: ([0-9]{4}) (Q[1-4])$")


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT or isinstance(value, bool):
        return None
    if isinstance(value, np.generic):
        value = value.item()
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
    return json.dumps(
        list(dict.fromkeys(item.strip() for item in values if item.strip())),
        ensure_ascii=False,
    )


def _observed_score(row: Mapping[str, object]) -> tuple[float | None, float]:
    weighted = 0.0
    available = 0.0
    total = sum(COMPONENT_WEIGHTS.values())
    for component, weight in COMPONENT_WEIGHTS.items():
        score = _number(row.get(component))
        if score is not None:
            weighted += score * weight
            available += weight
    return (weighted / available if available else None), available / total


def _state_and_action(
    row: Mapping[str, object],
    *,
    adjusted_score: float | None,
    coverage: float,
    policy: DecisionPolicy,
) -> tuple[str, str]:
    if adjusted_score is None or coverage < policy.minimum_coverage:
        return "insufficient_data", "research_gap"

    current_action = str(row.get("action_bias", ""))
    adjusted_timing_required = "adjusted" in current_action
    market_score = _number(row.get("market_timing_score"))
    if adjusted_score >= policy.positive_threshold:
        if adjusted_timing_required:
            return "positive_setup", "fundamental_positive_wait_for_adjusted_timing"
        if market_score is not None and market_score >= 3.2:
            return "positive_setup", "fundamental_positive_timing_confirmed"
        return "positive_setup", "fundamental_positive_wait_for_timing"
    if adjusted_score >= policy.mixed_threshold:
        if adjusted_timing_required:
            return "mixed_setup", "fundamental_mixed_wait_for_adjusted_timing"
        return "mixed_setup", "selective_or_wait"
    return "negative_setup", "avoid_or_reduce_candidate"


def apply_evidence_coverage_policy(
    scorecards: pd.DataFrame,
    policy: DecisionPolicy,
) -> pd.DataFrame:
    """Impute missing component weight at neutral instead of dropping the weight.

    The legacy score divided only by available component weight. Removing weak or
    unavailable components could therefore raise the displayed score. This policy
    preserves the observed-component average separately, then computes the decision
    score as if every unavailable component carried the neutral value 3.0.
    """

    if "ticker" not in scorecards.columns:
        raise ValueError("Scorecards must contain ticker")
    rows: list[dict[str, object]] = []
    for raw in scorecards.to_dict(orient="records"):
        row = {str(key): value for key, value in raw.items()}
        observed, coverage = _observed_score(row)
        adjusted = (
            _NEUTRAL_SCORE + (observed - _NEUTRAL_SCORE) * coverage
            if observed is not None
            else None
        )
        missing_weight = max(0.0, 1.0 - coverage)
        state, action = _state_and_action(
            row,
            adjusted_score=adjusted,
            coverage=coverage,
            policy=policy,
        )
        row["observed_component_score"] = observed
        row["evidence_adjusted_score"] = adjusted
        row["composite_score"] = adjusted
        row["score_coverage"] = coverage
        row["missing_component_weight"] = missing_weight
        row["score_calibration_method"] = (
            "missing_component_weight_imputed_at_neutral_3"
        )
        row["decision_state"] = state
        row["action_bias"] = action
        opposing = _decode_list(row.get("opposing_evidence"))
        if missing_weight > 0:
            opposing.append(
                f"미연결 점수 가중치 {missing_weight:.1%}: 중립 3.0으로 증거조정"
            )
        row["opposing_evidence"] = _json_list(opposing)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)


def _close(left: object, right: object) -> bool:
    first = _number(left)
    second = _number(right)
    if first is None or second is None:
        return False
    return math.isclose(first, second, rel_tol=1e-9, abs_tol=1.0)


def _annual_basis_years(
    financial_kpis: pd.DataFrame,
    financial_history: pd.DataFrame,
) -> dict[str, int]:
    if (
        financial_kpis.empty
        or financial_history.empty
        or "ticker" not in financial_kpis.columns
        or "ticker" not in financial_history.columns
        or "period_label" not in financial_history.columns
    ):
        return {}
    history = financial_history.copy()
    history["ticker"] = history["ticker"].astype("string").str.zfill(6)
    annual = history.loc[history["period_label"].astype(str).eq("FY")].copy()
    if "derived" in annual.columns:
        annual = annual.loc[~annual["derived"].astype(bool)]
    result: dict[str, int] = {}
    for raw in financial_kpis.to_dict(orient="records"):
        fin = cast(Mapping[str, object], raw)
        ticker = str(fin.get("ticker", "")).zfill(6)
        candidates = annual.loc[annual["ticker"].astype(str).eq(ticker)]
        if candidates.empty:
            continue
        ranked: list[tuple[int, int, Mapping[str, object]]] = []
        for candidate_raw in candidates.to_dict(orient="records"):
            candidate = cast(Mapping[str, object], candidate_raw)
            matches = sum(
                _close(fin.get(metric), candidate.get(metric))
                for metric in ("revenue", "operating_income", "net_income", "equity")
            )
            year_value = _number(candidate.get("business_year"))
            year = int(year_value) if year_value is not None else -1
            ranked.append((matches, year, candidate))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        matches, year, _ = ranked[0]
        if year >= 0 and (matches > 0 or len(ranked) == 1):
            result[ticker] = year
    return result


def _fmt_score(value: object) -> str:
    number = _number(value)
    return f"{number:.2f}/5" if number is not None else "미평가"


def _fmt_weight(value: object) -> str:
    number = _number(value)
    return f"{number:.1%}" if number is not None else "N/A"


def apply_evidence_report_policy(
    report: str,
    scorecards: pd.DataFrame,
    financial_kpis: pd.DataFrame,
    financial_history: pd.DataFrame,
) -> str:
    """Expose score shrinkage and prevent annual/quarterly YoY ambiguity."""

    score_lookup = {
        str(raw["ticker"]).zfill(6): {str(key): value for key, value in raw.items()}
        for raw in scorecards.to_dict(orient="records")
        if str(raw.get("ticker", "")).strip()
    }
    basis_years = _annual_basis_years(financial_kpis, financial_history)
    lines: list[str] = []
    current_primary: str | None = None
    current_valuation: str | None = None
    in_valuation = False
    pending_basis: str | None = None
    notice_added = False

    for line in report.splitlines():
        if line.startswith("## "):
            heading = line.removeprefix("## ").strip()
            if heading == "밸류에이션 및 다기간 실적":
                in_valuation = True
                current_primary = None
                current_valuation = None
            elif _TICKER_HEADING.fullmatch(heading) and not in_valuation:
                current_primary = heading
            else:
                current_primary = None
                if in_valuation:
                    in_valuation = False
                    current_valuation = None
        elif in_valuation and line.startswith("### "):
            candidate = line.removeprefix("### ").strip()
            current_valuation = (
                candidate if _TICKER_HEADING.fullmatch(candidate) else None
            )

        if (
            not notice_added
            and "점수 항목 커버리지는 전체 투자정보 완성도가 아니라" in line
        ):
            lines.append(line)
            lines.append(
                "- 증거조정 종합점수는 미연결 점수 가중치를 중립 3.0으로 "
                "반영해 결측 제외에 따른 점수 상승을 방지"
            )
            notice_added = True
            continue

        if current_primary in score_lookup and line.startswith("- 종합점수:"):
            row = score_lookup[current_primary]
            lines.extend(
                [
                    "- 증거조정 종합점수: "
                    + _fmt_score(row.get("evidence_adjusted_score")),
                    "- 관측 항목 평균: "
                    + _fmt_score(row.get("observed_component_score")),
                    "- 미연결 점수 가중치: "
                    + _fmt_weight(row.get("missing_component_weight"))
                    + " (중립 3.0 반영)",
                ]
            )
            continue

        if current_primary is not None and line == "### 2. 실적과 재무":
            lines.append(line)
            year = basis_years.get(current_primary)
            pending_basis = (
                f"- 기준 기간: {year} FY 연간 실적({year - 1} FY 대비); "
                "하단 최근 분기와 기간 기준이 다름"
                if year is not None
                else "- 기준 기간: OpenDART current-term/prior-term; "
                "하단 최근 분기와 직접 비교 금지"
            )
            continue

        if pending_basis is not None and line == "":
            lines.append(line)
            lines.append(pending_basis)
            pending_basis = None
            continue

        if current_primary is not None:
            year = basis_years.get(current_primary)
            if year is not None and line.startswith("- 매출 YoY:"):
                lines.append(
                    line.replace(
                        "- 매출 YoY:",
                        f"- 매출 YoY ({year} FY vs {year - 1} FY):",
                        1,
                    )
                )
                continue
            if year is not None and line.startswith("- 영업이익 YoY:"):
                lines.append(
                    line.replace(
                        "- 영업이익 YoY:",
                        f"- 영업이익 YoY ({year} FY vs {year - 1} FY):",
                        1,
                    )
                )
                continue

        if in_valuation and current_valuation is not None:
            quarter_match = _QUARTER_LINE.fullmatch(line)
            if quarter_match is not None:
                year = int(quarter_match.group(1))
                quarter = quarter_match.group(2)
                lines.append(
                    f"- 최근 분기 기준: {year} {quarter} 단일 분기"
                    f"({year - 1} {quarter} 대비)"
                )
                continue
            if line.startswith("- 매출 YoY:"):
                lines.append(
                    line.replace(
                        "- 매출 YoY:",
                        "- 매출 YoY (단일 분기, 전년 동기 대비):",
                        1,
                    )
                )
                continue
            if line.startswith("- 영업이익 YoY:"):
                lines.append(
                    line.replace(
                        "- 영업이익 YoY:",
                        "- 영업이익 YoY (단일 분기, 전년 동기 대비):",
                        1,
                    )
                )
                continue

        lines.append(line)

    if pending_basis is not None:
        lines.append(pending_basis)
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "apply_evidence_coverage_policy",
    "apply_evidence_report_policy",
]
