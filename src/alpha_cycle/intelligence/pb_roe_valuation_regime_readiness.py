"""Fail closed on shallow historical TTM ROE distributions.

Twelve quarterly TTM observations represent three years of update points and
roughly 8.3 percentage-point empirical-percentile resolution. This is a data
quality boundary, not a return-fitted investment threshold.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.historical_pb_decision_evidence import (
    HistoricalPbDecisionEvidence,
)
from alpha_cycle.intelligence.pb_roe_valuation_regime import (
    PbRoeValuationRegimeEvidence,
    attach_pb_roe_regime_to_scorecards,
    build_pb_roe_valuation_regime_evidence as _build_base_regime_evidence,
    sync_record_pb_roe_regime_fields as _sync_base_record_fields,
)

MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS = 12
_DISTRIBUTION_COLUMNS = (
    "ttm_roe_percentile",
    "ttm_roe_p25",
    "ttm_roe_median",
    "ttm_roe_p75",
    "pb_minus_roe_percentile_pp",
)


def _number(value: object, field: str) -> float:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted) or not np.isfinite(float(converted)):
        raise ValueError(f"P/B-ROE readiness has invalid {field}")
    return float(converted)


def _json_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float):
        if np.isnan(value):
            return None
        if not np.isfinite(value):
            raise ValueError("P/B-ROE readiness values must be finite")
    return value


def _rehashed_id(
    evidence: PbRoeValuationRegimeEvidence,
    rows: pd.DataFrame,
) -> str:
    payload = {
        "parent_evidence_id": evidence.evidence_id,
        "evaluation_date": evidence.evaluation_date.isoformat(),
        "valuation_snapshot_id": evidence.valuation_snapshot_id,
        "historical_pb_artifact_id": evidence.historical_pb_artifact_id,
        "minimum_ttm_roe_percentile_observations": (
            MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS
        ),
        "rows": [
            {str(key): _json_value(value) for key, value in raw.items()}
            for raw in rows.to_dict(orient="records")
        ],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def apply_pb_roe_history_readiness(
    evidence: PbRoeValuationRegimeEvidence,
) -> PbRoeValuationRegimeEvidence:
    """Publish current ROE levels but withhold immature distribution statistics."""

    rows = evidence.rows.copy()
    if "ttm_roe_observation_count" not in rows.columns:
        raise ValueError("P/B-ROE evidence lacks TTM ROE observation counts")
    for column in _DISTRIBUTION_COLUMNS:
        if column not in rows.columns:
            rows[column] = np.nan

    counts = pd.to_numeric(
        rows["ttm_roe_observation_count"], errors="coerce"
    ).fillna(0)
    if (counts < 0).any():
        raise ValueError("P/B-ROE observation counts cannot be negative")
    rows["ttm_roe_history_minimum_observations"] = (
        MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS
    )
    rows["ttm_roe_percentile_resolution_pct"] = [
        100.0 / float(count) if count > 0 else np.nan for count in counts
    ]
    rows["ttm_roe_history_ready"] = counts.ge(
        MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS
    )

    for index in rows.index:
        count = int(counts.loc[index])
        current = pd.to_numeric(
            pd.Series([rows.at[index, "ttm_roe"]]), errors="coerce"
        ).iloc[0]
        current_available = not pd.isna(current)
        pb_usable = bool(rows.at[index, "pb_current_usable"])
        ready = bool(rows.at[index, "ttm_roe_history_ready"])
        rows.at[index, "regime_evidence_available"] = current_available and pb_usable
        if not current_available:
            rows.at[index, "regime_status"] = "ttm_roe_unavailable"
        elif not ready:
            for column in _DISTRIBUTION_COLUMNS:
                rows.at[index, column] = np.nan
            rows.at[index, "regime_status"] = (
                "descriptive_level_only_roe_history_insufficient"
                if pb_usable
                else "pb_unavailable"
            )
        elif count >= MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS:
            rows.at[index, "regime_status"] = (
                "descriptive_non_scoring" if pb_usable else "pb_unavailable"
            )
        else:
            raise AssertionError("P/B-ROE readiness state is inconsistent")

    return replace(evidence, evidence_id=_rehashed_id(evidence, rows), rows=rows)


def build_pb_roe_valuation_regime_evidence(
    financial_history: pd.DataFrame,
    historical_pb: HistoricalPbDecisionEvidence,
    *,
    evaluation_date: date,
    valuation_snapshot_id: str,
) -> PbRoeValuationRegimeEvidence:
    base = _build_base_regime_evidence(
        financial_history,
        historical_pb,
        evaluation_date=evaluation_date,
        valuation_snapshot_id=valuation_snapshot_id,
    )
    return apply_pb_roe_history_readiness(base)


def sync_record_pb_roe_regime_fields(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    """Copy base regime fields plus readiness metadata into compact records."""

    result = _sync_base_record_fields(records, scorecards)
    extra = [
        "ticker",
        "pb_roe_regime_ttm_roe_history_ready",
        "pb_roe_regime_ttm_roe_history_minimum_observations",
        "pb_roe_regime_ttm_roe_percentile_resolution_pct",
    ]
    available = [column for column in extra if column in scorecards.columns]
    if len(available) <= 1:
        return result
    supplement = scorecards.loc[:, available].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [
        column for column in available if column != "ticker" and column in result.columns
    ]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def append_pb_roe_regime_report(
    report: str,
    evidence: PbRoeValuationRegimeEvidence,
) -> str:
    """Render ROE level evidence and readiness-qualified distribution context."""

    lines = [
        report.rstrip(),
        "",
        "## P/B-ROE 밸류에이션 레짐 (비점수)",
        "",
        f"- evidence: `{evidence.evidence_id[:12]}`",
        (
            "- TTM ROE proxy = 최근 4개 단일분기 연결 당기순이익 / "
            "시작·종료 자본총계 평균입니다."
        ),
        (
            "- ROE 역사 percentile은 분기 TTM 관측치가 최소 12개일 때만 공개합니다. "
            "12개는 3년 분기 관측과 약 8.3%p 해상도를 위한 품질 기준입니다."
        ),
        (
            "- cost of equity·지속성장률·forward ROE가 인증되지 않아 "
            "fair value·목표가·의사결정 점수에는 사용하지 않습니다."
        ),
        "",
        (
            "| 종목 | P/B | P/B 역사% | P/B 중앙값 대비 | TTM ROE proxy | "
            "ROE 역사% | ROE 관측치 | 해상도 | P/B%-ROE% | ROE 기준분기 | 상태 |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for raw_value in evidence.rows.to_dict(orient="records"):
        raw = {str(key): value for key, value in raw_value.items()}
        pb = _number(raw["pb_latest"], "P/B")
        pb_pct = _number(raw["pb_percentile"], "P/B percentile")
        premium = _number(raw["pb_premium_to_median_pct"], "P/B premium")
        count = int(_number(raw.get("ttm_roe_observation_count", 0), "ROE count"))
        current = pd.to_numeric(pd.Series([raw.get("ttm_roe")]), errors="coerce").iloc[0]
        resolution_value = pd.to_numeric(
            pd.Series([raw.get("ttm_roe_percentile_resolution_pct")]), errors="coerce"
        ).iloc[0]
        roe_text = "N/A" if pd.isna(current) else f"{float(current) * 100.0:.1f}%"
        resolution = (
            "N/A" if pd.isna(resolution_value) else f"{float(resolution_value):.1f}%p"
        )
        if bool(raw.get("ttm_roe_history_ready")):
            roe_pct = f"{_number(raw['ttm_roe_percentile'], 'ROE percentile'):.1f}%"
            gap = f"{_number(raw['pb_minus_roe_percentile_pp'], 'gap'):+.1f}%p"
        else:
            roe_pct = "N/A"
            gap = "N/A"
        period = raw.get("ttm_period_end")
        period_text = "N/A" if period is None or pd.isna(period) else str(period)
        lines.append(
            f"| {raw['ticker']} | {pb:.2f}x | {pb_pct:.1f}% | {premium:+.1f}% | "
            f"{roe_text} | {roe_pct} | {count} | {resolution} | {gap} | "
            f"{period_text} | {raw['regime_status']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "MINIMUM_TTM_ROE_PERCENTILE_OBSERVATIONS",
    "append_pb_roe_regime_report",
    "apply_pb_roe_history_readiness",
    "attach_pb_roe_regime_to_scorecards",
    "build_pb_roe_valuation_regime_evidence",
    "sync_record_pb_roe_regime_fields",
]
