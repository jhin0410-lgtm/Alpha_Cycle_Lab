"""Describe whether own-history P/B expansion is accompanied by observable TTM ROE.

The evidence is descriptive and non-scoring. TTM ROE uses the OpenDART
consolidated profit/loss field over average total equity, so the report calls it
a ROE proxy rather than a certified owners-of-parent ROE measure.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import cast

import numpy as np
import pandas as pd

from alpha_cycle.intelligence.historical_pb_decision_evidence import (
    HistoricalPbDecisionEvidence,
)

_QUARTER_NUMBER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


@dataclass(frozen=True)
class PbRoeValuationRegimeEvidence:
    evidence_id: str
    evaluation_date: date
    valuation_snapshot_id: str
    historical_pb_artifact_id: str
    rows: pd.DataFrame
    decision_score_enabled: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    point_in_time_backtest_eligible: bool = False

    def __post_init__(self) -> None:
        for value, field in (
            (self.evidence_id, "evidence_id"),
            (self.valuation_snapshot_id, "valuation_snapshot_id"),
            (self.historical_pb_artifact_id, "historical_pb_artifact_id"),
        ):
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{field} must be a lowercase SHA-256 digest")
        if self.rows.empty:
            raise ValueError("P/B-ROE regime evidence contains no symbols")
        if self.decision_score_enabled:
            raise ValueError("P/B-ROE regime scoring must remain disabled")
        if self.fair_value_estimate_enabled or self.target_price_enabled:
            raise ValueError("P/B-ROE fair-value surfaces must remain disabled")
        if self.point_in_time_backtest_eligible:
            raise ValueError("P/B-ROE backtest eligibility must remain disabled")


def _finite_float(value: object, field: str) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"P/B-ROE {field} must be numeric") from exc
    if not np.isfinite(number):
        raise ValueError(f"P/B-ROE {field} must be finite")
    return number


def _ticker_series(values: pd.Series) -> pd.Series:
    result = values.astype("string").str.strip().str.zfill(6)
    if result.isna().any() or (~result.str.fullmatch(r"[0-9]{6}")).any():
        raise ValueError("P/B-ROE financial history contains invalid ticker")
    return result


def _bool_series(values: pd.Series) -> pd.Series:
    return values.map(
        lambda value: value
        if isinstance(value, bool)
        else str(value).strip().casefold() in {"true", "1", "yes"}
    )


def _normalize_history(history: pd.DataFrame, evaluation_date: date) -> pd.DataFrame:
    required = {
        "ticker",
        "business_year",
        "period_label",
        "period_end",
        "available_date",
        "derived",
        "net_income",
        "equity",
    }
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"P/B-ROE financial history missing columns: {sorted(missing)}")
    result = history.copy()
    result["ticker"] = _ticker_series(result["ticker"])
    result["business_year"] = pd.to_numeric(
        result["business_year"], errors="raise"
    ).astype(int)
    result["period_label"] = result["period_label"].astype("string").str.strip()
    result["period_end"] = pd.to_datetime(result["period_end"], errors="raise")
    result["available_date"] = pd.to_datetime(result["available_date"], errors="raise")
    result["derived"] = _bool_series(result["derived"])
    result["net_income"] = pd.to_numeric(result["net_income"], errors="coerce")
    result["equity"] = pd.to_numeric(result["equity"], errors="coerce")
    cutoff = pd.Timestamp(evaluation_date)
    result = result.loc[
        result["period_end"].le(cutoff) & result["available_date"].le(cutoff)
    ].copy()
    if result.empty:
        raise ValueError("P/B-ROE financial history has no visible rows by evaluation date")
    return result.sort_values(
        ["ticker", "period_end", "period_label", "available_date"],
        kind="stable",
    ).reset_index(drop=True)


def _equity_at(
    equity_rows: pd.DataFrame,
    period_end: pd.Timestamp,
    as_of: pd.Timestamp,
) -> float | None:
    eligible = equity_rows.loc[
        equity_rows["period_end"].eq(period_end)
        & equity_rows["available_date"].le(as_of)
        & equity_rows["equity"].gt(0)
    ]
    if eligible.empty:
        return None
    value = eligible.sort_values("available_date", kind="stable").iloc[-1]["equity"]
    return _finite_float(value, "equity")


def _quarter_sequence(window: pd.DataFrame) -> list[int]:
    return [
        int(str(raw["business_year"])) * 4
        + _QUARTER_NUMBER[str(raw["period_label"])]
        - 1
        for raw in window.to_dict(orient="records")
    ]


def _ttm_roe_history(history: pd.DataFrame, ticker: str) -> pd.DataFrame:
    company = history.loc[history["ticker"].astype(str).eq(ticker)].copy()
    quarterly = company.loc[
        company["period_label"].isin(_QUARTER_NUMBER)
        & company["net_income"].notna()
    ].copy()
    if quarterly.empty:
        return pd.DataFrame()
    if quarterly.duplicated(["business_year", "period_label"]).any():
        raise ValueError(f"P/B-ROE quarterly flow rows are duplicated: {ticker}")
    quarterly = quarterly.sort_values("period_end", kind="stable").reset_index(drop=True)
    equity_rows = company.loc[
        ~company["derived"].astype(bool) & company["equity"].gt(0)
    ].copy()

    observations: list[dict[str, object]] = []
    for index in range(3, len(quarterly)):
        window = quarterly.iloc[index - 3 : index + 1].copy()
        sequence = _quarter_sequence(window)
        if any(
            right - left != 1
            for left, right in zip(sequence, sequence[1:], strict=False)
        ):
            continue
        end_period = cast(pd.Timestamp, window["period_end"].iloc[-1])
        start_period = end_period - pd.DateOffset(years=1)
        as_of = cast(pd.Timestamp, window["available_date"].max())
        beginning_equity = _equity_at(equity_rows, start_period, as_of)
        ending_equity = _equity_at(equity_rows, end_period, as_of)
        if beginning_equity is None or ending_equity is None:
            continue
        average_equity = (beginning_equity + ending_equity) / 2.0
        if average_equity <= 0:
            continue
        ttm_net_income = _finite_float(
            pd.to_numeric(window["net_income"], errors="raise").sum(),
            "TTM net income",
        )
        observations.append(
            {
                "ticker": ticker,
                "ttm_period_end": end_period,
                "ttm_available_date": as_of,
                "ttm_net_income": ttm_net_income,
                "beginning_equity": beginning_equity,
                "ending_equity": ending_equity,
                "average_equity": average_equity,
                "ttm_roe": ttm_net_income / average_equity,
            }
        )
    if not observations:
        return pd.DataFrame()
    return pd.DataFrame(observations).sort_values(
        ["ttm_available_date", "ttm_period_end"], kind="stable"
    ).reset_index(drop=True)


def _percentile(values: pd.Series, current: float) -> float:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        raise ValueError("P/B-ROE percentile requires observations")
    return float(numeric.le(current).mean() * 100.0)


def _serializable_row(row: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, (pd.Timestamp, date)):
            result[key] = value.isoformat()
        elif isinstance(value, np.generic):
            result[key] = value.item()
        elif value is pd.NA or value is pd.NaT:
            result[key] = None
        elif isinstance(value, float) and np.isnan(value):
            result[key] = None
        else:
            result[key] = value
    return result


def build_pb_roe_valuation_regime_evidence(
    financial_history: pd.DataFrame,
    historical_pb: HistoricalPbDecisionEvidence,
    *,
    evaluation_date: date,
    valuation_snapshot_id: str,
) -> PbRoeValuationRegimeEvidence:
    if historical_pb.evaluation_date != evaluation_date:
        raise ValueError("P/B-ROE regime requires current historical P/B evidence")
    history = _normalize_history(financial_history, evaluation_date)
    rows: list[dict[str, object]] = []
    for pb_raw in historical_pb.symbols.to_dict(orient="records"):
        ticker = str(pb_raw["ticker"]).zfill(6)
        pb_latest = _finite_float(pb_raw["latest_pb"], "latest P/B")
        pb_median = _finite_float(pb_raw["pb_median"], "median P/B")
        pb_percentile = _finite_float(
            pb_raw["latest_pb_percentile"], "P/B percentile"
        )
        usable_pb = bool(pb_raw.get("current_observational_band_usable"))
        base: dict[str, object] = {
            "ticker": ticker,
            "historical_pb_artifact_id": historical_pb.artifact_id,
            "valuation_snapshot_id": valuation_snapshot_id,
            "pb_latest": pb_latest,
            "pb_median": pb_median,
            "pb_percentile": pb_percentile,
            "pb_current_usable": usable_pb,
            "pb_premium_to_median_pct": (pb_latest / pb_median - 1.0) * 100.0,
            "roe_basis": "consolidated_profitloss_over_average_total_equity",
            "decision_score_enabled": False,
            "fair_value_estimate_enabled": False,
            "target_price_enabled": False,
            "point_in_time_backtest_eligible": False,
        }
        roe_history = _ttm_roe_history(history, ticker)
        if roe_history.empty:
            rows.append(
                {
                    **base,
                    "regime_evidence_available": False,
                    "regime_status": "ttm_roe_unavailable",
                    "ttm_roe_observation_count": 0,
                }
            )
            continue
        current = roe_history.iloc[-1]
        current_roe = _finite_float(current["ttm_roe"], "current TTM ROE")
        roe_values = pd.to_numeric(roe_history["ttm_roe"], errors="raise")
        roe_percentile = _percentile(roe_values, current_roe)
        available_date = cast(pd.Timestamp, current["ttm_available_date"])
        rows.append(
            {
                **base,
                "regime_evidence_available": usable_pb,
                "regime_status": (
                    "descriptive_non_scoring" if usable_pb else "pb_unavailable"
                ),
                "ttm_roe": current_roe,
                "ttm_roe_percentile": roe_percentile,
                "ttm_roe_p25": _finite_float(roe_values.quantile(0.25), "ROE P25"),
                "ttm_roe_median": _finite_float(roe_values.median(), "ROE median"),
                "ttm_roe_p75": _finite_float(roe_values.quantile(0.75), "ROE P75"),
                "ttm_roe_observation_count": int(len(roe_values)),
                "ttm_period_end": cast(pd.Timestamp, current["ttm_period_end"]).date(),
                "ttm_available_date": available_date.date(),
                "ttm_roe_lag_days": (evaluation_date - available_date.date()).days,
                "pb_minus_roe_percentile_pp": pb_percentile - roe_percentile,
            }
        )

    frame = pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    if frame["ticker"].duplicated().any():
        raise ValueError("P/B-ROE regime evidence contains duplicate tickers")
    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "valuation_snapshot_id": valuation_snapshot_id,
        "historical_pb_artifact_id": historical_pb.artifact_id,
        "rows": [
            _serializable_row(cast(dict[str, object], raw))
            for raw in frame.to_dict(orient="records")
        ],
    }
    evidence_id = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PbRoeValuationRegimeEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        valuation_snapshot_id=valuation_snapshot_id,
        historical_pb_artifact_id=historical_pb.artifact_id,
        rows=frame,
    )


def attach_pb_roe_regime_to_scorecards(
    scorecards: pd.DataFrame,
    evidence: PbRoeValuationRegimeEvidence,
) -> pd.DataFrame:
    if "ticker" not in scorecards.columns:
        raise ValueError("scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = evidence.rows.rename(
        columns={
            column: f"pb_roe_regime_{column}"
            for column in evidence.rows.columns
            if column != "ticker"
        }
    ).copy()
    supplement["pb_roe_regime_evidence_id"] = evidence.evidence_id
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def sync_record_pb_roe_regime_fields(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    fields = [
        "ticker",
        "pb_roe_regime_evidence_id",
        "pb_roe_regime_regime_evidence_available",
        "pb_roe_regime_regime_status",
        "pb_roe_regime_pb_latest",
        "pb_roe_regime_pb_median",
        "pb_roe_regime_pb_percentile",
        "pb_roe_regime_pb_premium_to_median_pct",
        "pb_roe_regime_roe_basis",
        "pb_roe_regime_ttm_roe",
        "pb_roe_regime_ttm_roe_percentile",
        "pb_roe_regime_ttm_roe_median",
        "pb_roe_regime_ttm_roe_observation_count",
        "pb_roe_regime_ttm_period_end",
        "pb_roe_regime_ttm_available_date",
        "pb_roe_regime_ttm_roe_lag_days",
        "pb_roe_regime_pb_minus_roe_percentile_pp",
        "pb_roe_regime_decision_score_enabled",
    ]
    available = [column for column in fields if column in scorecards.columns]
    supplement = scorecards.loc[:, available].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    result = records.copy()
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
    header = (
        "| 종목 | P/B | P/B 역사% | P/B 중앙값 대비 | TTM ROE proxy | "
        "ROE 역사% | ROE 관측치 | P/B%-ROE% | ROE 기준분기 | 상태 |"
    )
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
            "- Q4는 FY 누계-Q3 누계로 만든 단일분기 flow를 허용하지만, "
            "자본은 non-derived OpenDART 행만 사용합니다."
        ),
        (
            "- P/B·ROE percentile은 기술적 진단이며 cost of equity·지속성장률·"
            "forward ROE가 없어 fair value나 목표가를 산출하지 않습니다."
        ),
        "- 현재 의사결정 점수에는 반영하지 않습니다.",
        "",
        header,
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for raw in evidence.rows.to_dict(orient="records"):
        current_roe = raw.get("ttm_roe")
        if not bool(raw.get("regime_evidence_available")) or pd.isna(current_roe):
            lines.append(
                f"| {raw['ticker']} | {_finite_float(raw['pb_latest'], 'P/B'):.2f}x | "
                f"{_finite_float(raw['pb_percentile'], 'P/B percentile'):.1f}% | "
                f"{_finite_float(raw['pb_premium_to_median_pct'], 'P/B premium'):+.1f}% | "
                f"N/A | N/A | {int(raw.get('ttm_roe_observation_count', 0))} | "
                f"N/A | N/A | {raw['regime_status']} |"
            )
            continue
        lines.append(
            f"| {raw['ticker']} | {_finite_float(raw['pb_latest'], 'P/B'):.2f}x | "
            f"{_finite_float(raw['pb_percentile'], 'P/B percentile'):.1f}% | "
            f"{_finite_float(raw['pb_premium_to_median_pct'], 'P/B premium'):+.1f}% | "
            f"{_finite_float(current_roe, 'TTM ROE') * 100.0:.1f}% | "
            f"{_finite_float(raw['ttm_roe_percentile'], 'ROE percentile'):.1f}% | "
            f"{int(str(raw['ttm_roe_observation_count']))} | "
            f"{_finite_float(raw['pb_minus_roe_percentile_pp'], 'percentile gap'):+.1f}%p | "
            f"{raw['ttm_period_end']} | {raw['regime_status']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "PbRoeValuationRegimeEvidence",
    "append_pb_roe_regime_report",
    "attach_pb_roe_regime_to_scorecards",
    "build_pb_roe_valuation_regime_evidence",
    "sync_record_pb_roe_regime_fields",
]
