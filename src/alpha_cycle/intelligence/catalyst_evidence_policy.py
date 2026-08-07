"""Keep filing-title materiality separate from investment direction."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
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


def _document_record(
    evidence: Mapping[str, object] | None,
    receipt: str,
) -> Mapping[str, object] | None:
    if evidence is None:
        return None
    value = evidence.get(receipt)
    return value if isinstance(value, Mapping) else None


def _valid_sha256(value: object) -> bool:
    text = str(value).strip().casefold()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _body_status(record: Mapping[str, object] | None) -> tuple[bool, bool]:
    if record is None or record.get("status") != "collected":
        return False, False
    chars = record.get("text_chars")
    if isinstance(chars, bool) or not isinstance(chars, int) or chars <= 0:
        return False, False
    if not _valid_sha256(record.get("text_sha256")) or not _valid_sha256(
        record.get("archive_sha256")
    ):
        return False, False
    truncated = record.get("text_truncated")
    if not isinstance(truncated, bool):
        return False, False
    return True, truncated


def annotate_catalyst_direction(
    catalysts: pd.DataFrame,
    *,
    document_evidence: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    if "ticker" not in catalysts.columns:
        raise ValueError("Catalysts must contain ticker")
    result = catalysts.copy()
    statuses: list[str] = []
    bases: list[str] = []
    document_statuses: list[str] = []
    text_hashes: list[str | None] = []
    archive_hashes: list[str | None] = []
    text_chars: list[int | None] = []
    truncated_values: list[bool | None] = []
    for raw in result.to_dict(orient="records"):
        category = str(raw.get("category", ""))
        receipt = str(raw.get("rcept_no", "")).strip()
        record = _document_record(document_evidence, receipt)
        record_status = str(record.get("status", "not_selected")) if record is not None else "not_selected"
        body_available, truncated = _body_status(record)
        if body_available:
            if bool(raw.get("is_correction", False)):
                status = (
                    "unresolved_correction_partial_body"
                    if truncated
                    else "unresolved_correction_body_available"
                )
            elif category == "operational_risk":
                status = "negative_operational_risk_title_body_available"
            else:
                status = "unresolved_partial_body" if truncated else "unresolved_body_available"
            basis = "filing_body_partial" if truncated else "filing_body_available_unclassified"
            document_statuses.append("collected")
            assert record is not None
            text_hashes.append(str(record.get("text_sha256")))
            archive_hashes.append(str(record.get("archive_sha256")))
            chars_value = record.get("text_chars")
            text_chars.append(
                chars_value
                if isinstance(chars_value, int) and not isinstance(chars_value, bool)
                else None
            )
            truncated_values.append(truncated)
        elif record_status == "excluded_periodic":
            status = "not_directional_periodic_report"
            basis = "periodic_report_financial_evidence_path"
            document_statuses.append(record_status)
            text_hashes.append(None)
            archive_hashes.append(None)
            text_chars.append(None)
            truncated_values.append(None)
        elif record_status == "excluded_capacity":
            status = "deferred_body_backlog"
            basis = "bounded_body_collection_backlog"
            document_statuses.append(record_status)
            text_hashes.append(None)
            archive_hashes.append(None)
            text_chars.append(None)
            truncated_values.append(None)
        else:
            if bool(raw.get("is_correction", False)):
                status = "unresolved_correction_title_only"
            elif category == "operational_risk":
                status = "negative_operational_risk_title"
            else:
                status = "unresolved_title_only"
            basis = "filing_title_only"
            document_statuses.append(record_status)
            text_hashes.append(None)
            archive_hashes.append(None)
            text_chars.append(None)
            truncated_values.append(None)
        statuses.append(status)
        bases.append(basis)
    result["direction_status"] = statuses
    result["direction_basis"] = bases
    result["document_evidence_status"] = document_statuses
    result["document_text_sha256"] = text_hashes
    result["document_archive_sha256"] = archive_hashes
    result["document_text_chars"] = text_chars
    result["document_text_truncated"] = truncated_values
    return result


def _direction_counts(catalysts: pd.DataFrame) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for raw in catalysts.to_dict(orient="records"):
        ticker = str(raw.get("ticker", "")).zfill(6)
        values = counts.setdefault(
            ticker,
            {
                "negative": 0,
                "unresolved_title": 0,
                "unresolved_body": 0,
                "backlog": 0,
                "non_directional": 0,
            },
        )
        status = str(raw.get("direction_status", "unresolved_title_only"))
        if status == "deferred_body_backlog":
            values["backlog"] += 1
        elif status == "not_directional_periodic_report":
            values["non_directional"] += 1
        elif status.startswith("negative_"):
            values["negative"] += 1
        elif "body" in status:
            values["unresolved_body"] += 1
        else:
            values["unresolved_title"] += 1
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
    document_evidence: Mapping[str, object] | None = None,
) -> InvestmentDecisionSnapshot:
    catalysts = annotate_catalyst_direction(
        snapshot.catalysts,
        document_evidence=document_evidence,
    )
    counts = _direction_counts(catalysts)
    rows: list[dict[str, object]] = []
    unresolved_title: list[str] = []
    unresolved_body: list[str] = []
    backlog_warnings: list[str] = []
    negative: list[str] = []
    empty_counts = {
        "negative": 0,
        "unresolved_title": 0,
        "unresolved_body": 0,
        "backlog": 0,
        "non_directional": 0,
    }
    for raw in snapshot.scorecards.to_dict(orient="records"):
        row = {str(key): value for key, value in raw.items()}
        ticker = str(row["ticker"]).zfill(6)
        values = counts.get(ticker, empty_counts)
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
        elif values["unresolved_body"] or values["unresolved_title"]:
            row["catalyst_score"] = None
            if values["unresolved_body"] and not values["unresolved_title"]:
                row["catalyst_evidence_status"] = "unresolved_body_available"
                opposing.append(
                    f"중요 공시 원문 {values['unresolved_body']}건 확보; "
                    "수치·시장 기대 대비 투자 방향 규칙 미적용"
                )
                unresolved_body.append(ticker)
            elif values["unresolved_body"]:
                row["catalyst_evidence_status"] = "unresolved_mixed_body_title"
                opposing.append(
                    f"중요 공시 원문 {values['unresolved_body']}건 확보, "
                    f"실제 원문 수집 실패·미확인 {values['unresolved_title']}건; "
                    "방향 판정 미완료"
                )
                unresolved_body.append(ticker)
                unresolved_title.append(ticker)
            else:
                row["catalyst_evidence_status"] = "unresolved_title_only"
                opposing.append(
                    f"중요 공시 {values['unresolved_title']}건 방향 미평가: "
                    "본문 증거 미확보로 긍정 촉매 판단 불가"
                )
                unresolved_title.append(ticker)
        elif values["backlog"]:
            row["catalyst_score"] = None
            row["catalyst_evidence_status"] = "bounded_body_backlog_only"
            opposing.append(
                f"원문 수집 상한 밖 중요 공시 {values['backlog']}건 존재; "
                "완전한 촉매 방향 인증 아님"
            )
        else:
            row["catalyst_score"] = None
            row["catalyst_evidence_status"] = "no_directional_catalyst_evidence"
            opposing.append("방향성이 검증된 촉매 근거 없음")
        if values["backlog"]:
            opposing.append(
                f"원문 수집 상한으로 과거 중요 공시 {values['backlog']}건은 "
                "비인증 backlog로 유지"
            )
            backlog_warnings.append(f"{ticker}={values['backlog']}")
        row["positive_evidence"] = _encode(positives)
        row["opposing_evidence"] = _encode(opposing)
        _recompute(row, policy)
        rows.append(row)

    warnings = list(snapshot.warnings)
    if unresolved_title:
        warnings.append(
            "catalyst_direction_unresolved_title_only:"
            + ",".join(sorted(set(unresolved_title)))
        )
    if unresolved_body:
        warnings.append(
            "catalyst_direction_unresolved_body_available:"
            + ",".join(sorted(set(unresolved_body)))
        )
    if backlog_warnings:
        warnings.append(
            "catalyst_document_backlog_bounded:"
            + ",".join(sorted(set(backlog_warnings)))
        )
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
            "unresolved_body_available",
            "unresolved_mixed_body_title",
            "bounded_body_backlog_only",
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
