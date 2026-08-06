"""Price-adjustment policy for technical decision evidence.

Unadjusted daily bars remain useful as source observations, but corporate actions
can create discontinuities that look like returns, moving-average breaks, or
maximum drawdowns. This module keeps those observations visible while preventing
them from driving scorecards or execution conditions until adjusted prices, or an
equivalent corporate-action verification, are available.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_scoring import (
    CompanyExposure,
    DecisionPolicy,
    build_report,
    build_scorecards,
)

_TECHNICAL_COLUMNS = (
    "return_1",
    "return_5",
    "return_20",
    "return_60",
    "sma_20",
    "price_to_sma_20",
    "realized_volatility_20",
    "max_drawdown_60",
    "volume_ratio_20",
    "relative_strength_rank_20",
    "relative_strength_rank_60",
    "excess_return_5",
    "excess_return_20",
    "excess_return_60",
    "rsi_14",
    "trend_efficiency_20",
    "trend_direction_20",
)
_TECHNICAL_TRIGGER = "20일 수익률 -10% 이하이면서 20일선 하회"
_UNADJUSTED_WARNING_PREFIX = "technical_decision_evidence_unavailable_unadjusted_prices:"
_UNKNOWN_WARNING_PREFIX = "technical_decision_evidence_unavailable_unknown_adjustment_basis:"
_TICKER_HEADING = re.compile(r"^## ([0-9]{6})$")


def _read_manifest_adjusted(market_snapshot: str | Path) -> bool | None:
    manifest_path = Path(market_snapshot) / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Market snapshot manifest must be a JSON object")
    adjusted = payload.get("adjusted")
    if adjusted is None:
        return None
    if not isinstance(adjusted, bool):
        raise ValueError("Market snapshot adjusted must be boolean when present")
    return adjusted


def _basis_label(adjusted: bool | None) -> str:
    if adjusted is True:
        return "adjusted"
    if adjusted is False:
        return "unadjusted"
    return "unknown"


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


def _encode_list(values: list[str]) -> str:
    unique = list(dict.fromkeys(item.strip() for item in values if item.strip()))
    return json.dumps(unique, ensure_ascii=False)


def _number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT or isinstance(value, bool):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def gate_market_context(
    market_context: pd.DataFrame,
    *,
    adjusted: bool | None,
) -> pd.DataFrame:
    """Keep raw observations but null execution-grade technical fields when unsafe."""

    if "ticker" not in market_context.columns:
        raise ValueError("Market context must contain ticker")
    result = market_context.copy()
    result["price_adjustment_basis"] = _basis_label(adjusted)
    result["technical_decision_eligible"] = adjusted is True
    if adjusted is True:
        return result

    for column in _TECHNICAL_COLUMNS:
        if column not in result.columns:
            continue
        result[f"observed_{column}"] = result[column]
        result[column] = np.nan
    return result


def _gate_scorecard_execution_fields(scorecards: pd.DataFrame) -> pd.DataFrame:
    result = scorecards.copy()
    for index, raw in result.iterrows():
        triggers = [
            item
            for item in _decode_list(raw.get("invalidation_triggers"))
            if item != _TECHNICAL_TRIGGER
        ]
        opposing = _decode_list(raw.get("opposing_evidence"))
        opposing.append("시장 타이밍 미평가: 수정주가 또는 기업행위 검증 가격 이력 미확보")
        state = str(raw.get("decision_state", "insufficient_data"))
        action = str(raw.get("action_bias", "research_gap"))
        if state == "positive_setup":
            action = "fundamental_positive_wait_for_adjusted_timing"
        elif state == "mixed_setup":
            action = "selective_or_wait_for_adjusted_timing"
        result.at[index, "action_bias"] = action
        result.at[index, "invalidation_triggers"] = _encode_list(triggers)
        result.at[index, "opposing_evidence"] = _encode_list(opposing)
        result.at[index, "technical_evidence_status"] = "execution_gated"
    return result


def _base_decision_records(
    snapshot: InvestmentDecisionSnapshot,
    scorecards: pd.DataFrame,
    market_context: pd.DataFrame,
) -> pd.DataFrame:
    price_lookup = market_context.set_index("ticker")["last_price"].to_dict()
    records = scorecards.loc[
        :,
        [
            "ticker",
            "decision_state",
            "action_bias",
            "composite_score",
            "score_coverage",
        ],
    ].copy()
    records.insert(1, "evaluation_date", snapshot.evaluation_date)
    records.insert(2, "reference_price", records["ticker"].map(price_lookup))
    if records["reference_price"].isna().any():
        raise ValueError("Decision records are missing reference prices")
    return records


def apply_market_evidence_policy(
    snapshot: InvestmentDecisionSnapshot,
    *,
    market_snapshot: str | Path,
    exposures: Mapping[str, CompanyExposure],
    policy: DecisionPolicy,
) -> InvestmentDecisionSnapshot:
    """Rebuild base scorecards after applying the price-adjustment evidence gate."""

    adjusted = _read_manifest_adjusted(market_snapshot)
    market_context = gate_market_context(snapshot.market_context, adjusted=adjusted)
    if adjusted is True:
        return replace(snapshot, market_context=market_context)

    scorecards = build_scorecards(
        snapshot.financial_kpis,
        snapshot.disclosure_summary,
        snapshot.macro_regime,
        market_context,
        exposures,
        policy,
    )
    scorecards["ticker"] = scorecards["ticker"].astype("string").str.zfill(6)
    scorecards = _gate_scorecard_execution_fields(scorecards)

    tickers = sorted(scorecards["ticker"].astype(str).tolist())
    warning_prefix = (
        _UNADJUSTED_WARNING_PREFIX
        if adjusted is False
        else _UNKNOWN_WARNING_PREFIX
    )
    warnings = tuple(dict.fromkeys([*snapshot.warnings, warning_prefix + ",".join(tickers)]))
    report = build_report(
        snapshot.evaluation_date,
        scorecards,
        snapshot.financial_kpis,
        snapshot.catalysts,
        snapshot.macro_regime,
        market_context,
        warnings,
    )
    return replace(
        snapshot,
        market_context=market_context,
        scorecards=scorecards,
        decision_records=_base_decision_records(snapshot, scorecards, market_context),
        report_markdown=report,
        warnings=warnings,
    )


def _remove_matching(items: list[str], fragments: tuple[str, ...]) -> list[str]:
    return [item for item in items if not any(fragment in item for fragment in fragments)]


def gate_execution_playbook(
    scorecards: pd.DataFrame,
    market_context: pd.DataFrame,
) -> pd.DataFrame:
    """Remove unadjusted technical thresholds from action-oriented playbooks."""

    if "ticker" not in scorecards.columns or "ticker" not in market_context.columns:
        raise ValueError("Scorecards and market context must contain ticker")
    eligibility = {
        str(raw["ticker"]).zfill(6): bool(raw.get("technical_decision_eligible", False))
        for raw in market_context.to_dict(orient="records")
    }
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    for index, raw in result.iterrows():
        ticker = str(raw["ticker"])
        if eligibility.get(ticker, False):
            continue

        state = str(raw.get("decision_state", "insufficient_data"))
        if state == "insufficient_data":
            readiness = "research_gap"
        elif state == "negative_setup":
            readiness = "avoid_or_reduce_review"
        else:
            readiness = "wait_for_adjusted_market_evidence"

        entry = _remove_matching(
            _decode_list(raw.get("entry_conditions")),
            ("20일", "상대강도", "가격 추세"),
        )
        entry.insert(
            0,
            "수정주가 또는 기업행위 검증이 완료된 가격 이력 확보 후 진입 타이밍 판단",
        )

        additions = _remove_matching(
            _decode_list(raw.get("add_conditions")),
            ("주가 상승이 거래량", "상대강도"),
        )
        additions.append("기업행위 검증이 완료된 가격 이력에서 추세·거래량 확인")

        reductions = _remove_matching(
            _decode_list(raw.get("reduce_conditions")),
            ("20일", "상대강도", "현재 약세"),
        )
        reductions.insert(
            0,
            "기업행위 검증 전 미수정주가 기술 신호만으로 비중을 축소하지 않음",
        )

        exits = _remove_matching(
            _decode_list(raw.get("exit_conditions")),
            (_TECHNICAL_TRIGGER, "이익 모멘텀과 가격 추세가 동시에 훼손"),
        )
        exits.append("이익 모멘텀 훼손과 수정주가 기준 가격 추세 악화가 함께 확인")

        gaps = _decode_list(raw.get("evidence_gaps"))
        gaps.append("수정주가 또는 기업행위 검증 가격 이력 미확보")

        result.at[index, "action_readiness"] = readiness
        result.at[index, "entry_conditions"] = _encode_list(entry)
        result.at[index, "add_conditions"] = _encode_list(additions)
        result.at[index, "reduce_conditions"] = _encode_list(reductions)
        result.at[index, "exit_conditions"] = _encode_list(exits)
        result.at[index, "evidence_gaps"] = _encode_list(gaps)
        result.at[index, "playbook_basis"] = (
            str(raw.get("playbook_basis", "deterministic_snapshot_rules"))
            + "_technical_execution_gated"
        )
    return result


def _format_percent(value: object) -> str:
    number = _number(value)
    return f"{number:.1%}" if number is not None else "N/A"


def apply_market_report_policy(
    report: str,
    market_context: pd.DataFrame,
) -> str:
    """Label gated sections and append the retained source observations."""

    rows = {
        str(raw["ticker"]).zfill(6): cast(dict[str, object], raw)
        for raw in market_context.to_dict(orient="records")
    }
    gated = {
        ticker: row
        for ticker, row in rows.items()
        if not bool(row.get("technical_decision_eligible", False))
    }
    if not gated:
        return report

    transformed: list[str] = []
    current_ticker: str | None = None
    for line in report.rstrip().splitlines():
        heading = _TICKER_HEADING.fullmatch(line)
        if heading is not None:
            current_ticker = heading.group(1)
        transformed.append(line)
        if line == "### 3. 시장 타이밍" and current_ticker in gated:
            basis = str(gated[current_ticker].get("price_adjustment_basis", "unknown"))
            transformed.extend(
                [
                    "",
                    f"- 가격 조정 기준: {basis}",
                    "- 아래 실행용 기술 지표는 미평가; 원시 관측치는 별도 참고 섹션에 보존",
                ]
            )
        if current_ticker not in gated:
            continue
        replacements = {
            "- Bull: 이익 성장·마진 개선·핵심 촉매·상대강도가 함께 유지": (
                "- Bull: 이익 성장·마진 개선·핵심 촉매가 유지되고 수정주가 기반 타이밍이 추후 확인"
            ),
            "- Base: 현재 실적 성장률과 마진·환율·가격 추세가 대체로 유지": (
                "- Base: 현재 실적 성장률과 마진·환율이 대체로 유지; 가격 타이밍은 미평가"
            ),
            "- Bear: 이익 둔화·마진 압박·촉매 지연·20일선 하회가 동시 발생": (
                "- Bear: 이익 둔화·마진 압박·촉매 지연이 동시 발생"
            ),
        }
        if line in replacements:
            transformed[-1] = replacements[line]

    transformed.extend(
        [
            "",
            "## 가격 조정 미검증 시장 관측치",
            "",
            "- 아래 값은 공급자가 제공한 미수정주가 또는 조정 기준 미확인 일봉에서 계산한 참고 관측치",
            "- 종합점수, 행동 준비도, 진입·추가매수·축소·청산 조건에는 사용하지 않음",
        ]
    )
    for ticker, row in sorted(gated.items()):
        transformed.extend(
            [
                "",
                f"### {ticker}",
                "",
                f"- 가격 조정 기준: {row.get('price_adjustment_basis', 'unknown')}",
                f"- 관측 20일 수익률: {_format_percent(row.get('observed_return_20'))}",
                f"- 관측 60일 수익률: {_format_percent(row.get('observed_return_60'))}",
                f"- 관측 20일선 대비: {_format_percent(row.get('observed_price_to_sma_20'))}",
                f"- 관측 60일 최대낙폭: {_format_percent(row.get('observed_max_drawdown_60'))}",
            ]
        )
    return "\n".join(transformed).rstrip() + "\n"


__all__ = [
    "apply_market_evidence_policy",
    "apply_market_report_policy",
    "gate_execution_playbook",
    "gate_market_context",
]
