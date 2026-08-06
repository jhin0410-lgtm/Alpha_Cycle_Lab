"""Keep filing-title materiality separate from investment direction."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import COMPONENT_WEIGHTS, DecisionPolicy

_POSITIVE_TITLE_PREFIXES = ("중요도 critical 공시 ", "중요도 high 공시 ")
_DIRECTION_GAP = "공시 본문·변경 수치·시장 기대 대비 투자 방향 미분석"


def _decode(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    try:
        parsed: object = json.loads(value)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _encode(values: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(item for item in values if item)), ensure_ascii=False)


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT or isinstance(value, bool):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def annotate_catalyst_direction(catalysts: pd.DataFrame) -> pd.DataFrame:
    if "ticker" not in catalysts.columns:
        raise ValueError("Catalysts must contain ticker")
    result = catalysts.copy()
    statuses: list[str] = []
    for raw in result.to_dict(orient="records"):
        category = str(raw.get("category", ""))
        if bool(raw.get("is_correction", False)):
            status = "unresolved_correction_title_only"
        elif category == "operational_risk":
            status = "negative_operational_risk_title"
        else:
            status = "unresolved_title_only"
        statuses.append(status)
    result["direction_status"] = statuses
    result["direction_basis"] = "filing_title_only"
    return result


def _direction_counts(catalysts: pd.DataFrame) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for raw in catalysts.to_dict(orient="records"):
        ticker = str(raw.get("ticker", "")).zfill(6)
        values = counts.setdefault(ticker, {"negative": 0, "unresolved": 0})
        status = str(raw.get("direction_status", "unresolved_title_only"))
        values["negative" if status.startswith("negative_") else "unresolved"] += 1
    return counts


def _recompute(row: dict[str, object], policy: DecisionPolicy) -> None:
    weighted = 0.0
    available = 0.0
    for column, weight in COMPONENT_WEIGHTS.items():
        score = _number(row.get(column))
        if score is not None:
            weighted += score * weight
            available += weight
    coverage = available / sum(COMPONENT_WEIGHTS.values())
    composite = weighted / available if available else None
    technical_gated = str(row.get("technical_evidence_status", "")) == "execution_gated"
    if composite is None or coverage < policy.minimum_coverage:
        state, action = "insufficient_data", "research_gap"
    elif composite >= policy.positive_threshold:
        state = "positive_setup"
        market_score = _number(row.get("market_timing_score"))
        if technical_gated:
            action = "fundamental_positive_wait_for_adjusted_timing"
        elif market_score is not None and market_score >= 3.2:
            action = "fundamental_positive_timing_confirmed"
        else:
            action = "fundamental_positive_wait_for_timing"
    elif composite >= policy.mixed_threshold:
        state = "mixed_setup"
        action = "selective_or_wait_for_adjusted_timing" if technical_gated else "selective_or_wait"
    else:
        state, action = "negative_setup", "avoid_or_reduce_candidate"
    row.update(
        composite_score=composite,
        score_coverage=coverage,
        decision_state=state,
        action_bias=action,
    )


def _restore_technical_action(row: pd.Series[Any]) -> str | None:
    if str(row.get("technical_evidence_status", "")) != "execution_gated":
        return None
    state = str(row.get("decision_state", ""))
    if state == "positive_setup":
        return "fundamental_positive_wait_for_adjusted_timing"
    if state == "mixed_setup":
        return "selective_or_wait_for_adjusted_timing"
    return None


def apply_catalyst_evidence_policy(
    snapshot: InvestmentDecisionSnapshot,
    *,
    policy: DecisionPolicy,
) -> InvestmentDecisionSnapshot:
    catalysts = annotate_catalyst_direction(snapshot.catalysts)
    counts = _direction_counts(catalysts)
    rows: list[dict[str, object]] = []
    unresolved: list[str] = []
    negative: list[str] = []
    for raw in snapshot.scorecards.to_dict(orient="records"):
        row = {str(key): value for key, value in raw.items()}
        ticker = str(row["ticker"]).zfill(6)
        values = counts.get(ticker, {"negative": 0, "unresolved": 0})
        positives = [
            item
            for item in _decode(row.get("positive_evidence"))
            if not item.startswith(_POSITIVE_TITLE_PREFIXES)
        ]
        opposing = _decode(row.get("opposing_evidence"))
        if values["negative"]:
            row["catalyst_score"] = 1.0
            row["catalyst_evidence_status"] = "negative_title_evidence"
            opposing.append(
                f"부정 방향 운영위험 공시 제목 {values['negative']}건; 본문 영향 확인 필요"
            )
            negative.append(ticker)
        elif values["unresolved"]:
            row["catalyst_score"] = None
            row["catalyst_evidence_status"] = "unresolved_title_only"
            opposing.append(
                f"중요 공시 {values['unresolved']}건 방향 미평가: 제목만으로 긍정 촉매 판단 불가"
            )
            unresolved.append(ticker)
        else:
            row["catalyst_score"] = None
            row["catalyst_evidence_status"] = "no_directional_catalyst_evidence"
            opposing.append("방향성이 검증된 촉매 근거 없음")
        row["positive_evidence"] = _encode(positives)
        row["opposing_evidence"] = _encode(opposing)
        _recompute(row, policy)
        rows.append(row)

    warnings = list(snapshot.warnings)
    if unresolved:
        warnings.append("catalyst_direction_unresolved_title_only:" + ",".join(sorted(set(unresolved))))
    if negative:
        warnings.append("negative_operational_risk_title_evidence:" + ",".join(sorted(set(negative))))
    scorecards = pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    return replace(
        snapshot,
        catalysts=catalysts,
        scorecards=scorecards,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def gate_catalyst_playbook(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    for index, raw in result.iterrows():
        restored_action = _restore_technical_action(raw)
        if restored_action is not None:
            result.at[index, "action_bias"] = restored_action
        status = str(raw.get("catalyst_evidence_status", ""))
        if status not in {
            "unresolved_title_only",
            "negative_title_evidence",
            "no_directional_catalyst_evidence",
        }:
            continue
        gaps = _decode(raw.get("evidence_gaps"))
        gaps.append(_DIRECTION_GAP)
        entry = _decode(raw.get("entry_conditions"))
        entry.append("핵심 공시 본문·변경 수치·시장 기대 대비 투자 방향 확인")
        additions = _decode(raw.get("add_conditions"))
        additions.append("매출·이익·현금흐름 영향 확인 뒤 비중 확대")
        reductions = _decode(raw.get("reduce_conditions"))
        if status == "negative_title_evidence":
            reductions.insert(0, "운영위험 공시 본문과 손익 영향 확인 전 비중 확대 금지")
        result.at[index, "evidence_gaps"] = _encode(gaps)
        result.at[index, "entry_conditions"] = _encode(entry)
        result.at[index, "add_conditions"] = _encode(additions)
        result.at[index, "reduce_conditions"] = _encode(reductions)
    return result


def apply_catalyst_report_policy(report: str) -> str:
    result = report.replace("- 확인된 촉매\n", "- 확인된 주요 공시·촉매 후보\n")
    marker = "## 실행 플레이북\n"
    note = "\n- 공시 중요도와 투자 방향을 구분하며, 본문 검증 전 긍정 촉매로 점수화하지 않음\n"
    return result.replace(marker, marker + note, 1) if marker in result else result


__all__ = [
    "annotate_catalyst_direction",
    "apply_catalyst_evidence_policy",
    "apply_catalyst_report_policy",
    "gate_catalyst_playbook",
]
