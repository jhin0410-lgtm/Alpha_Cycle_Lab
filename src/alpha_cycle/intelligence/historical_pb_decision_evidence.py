"""Attach current own-history P/B observations without changing decision scores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from alpha_cycle.historical_pb_readiness_cli import inspect_historical_pb_readiness


@dataclass(frozen=True)
class HistoricalPbDecisionEvidence:
    artifact_id: str
    evaluation_date: date
    symbols: pd.DataFrame
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False
    fair_value_estimate_enabled: bool = False
    target_price_enabled: bool = False
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.artifact_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.artifact_id
        ):
            raise ValueError("historical P/B artifact_id must be a lowercase SHA-256 digest")
        if self.symbols.empty:
            raise ValueError("historical P/B decision evidence contains no symbols")
        if self.historical_vintage_certified:
            raise ValueError("historical P/B vintage certification must remain false")
        if self.point_in_time_backtest_eligible:
            raise ValueError("historical P/B backtest eligibility must remain false")
        if self.fair_value_estimate_enabled or self.target_price_enabled:
            raise ValueError("historical P/B fair-value surfaces must remain disabled")
        if self.decision_score_enabled:
            raise ValueError("historical P/B decision scoring must remain disabled")

    @property
    def tickers(self) -> tuple[str, ...]:
        return tuple(sorted(self.symbols["ticker"].astype(str).tolist()))


def _bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise ValueError(f"historical P/B readiness has invalid boolean {field}")


def _number(value: object, field: str) -> float:
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        raise ValueError(f"historical P/B readiness has invalid {field}")
    return float(converted)


def load_historical_pb_decision_evidence(
    pointer_path: str | Path,
) -> HistoricalPbDecisionEvidence:
    """Load the strict readiness view used for current non-scoring decisions."""

    payload = inspect_historical_pb_readiness(Path(pointer_path))
    if payload.get("status") != "historical_pb_readiness_inspected":
        raise ValueError("historical P/B readiness status is not usable")
    for key in (
        "historical_vintage_certified",
        "point_in_time_backtest_eligible",
        "fair_value_estimate_enabled",
        "target_price_enabled",
        "decision_score_enabled",
    ):
        if payload.get(key) is not False:
            raise ValueError(f"historical P/B readiness must keep {key}=false")

    artifact_id = str(payload.get("artifact_id", "")).strip()
    evaluation_date = date.fromisoformat(str(payload.get("evaluation_date", "")))
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise ValueError("historical P/B readiness contains no symbols")

    rows: list[dict[str, object]] = []
    for raw in raw_symbols:
        if not isinstance(raw, dict):
            raise ValueError("historical P/B readiness symbol row must be an object")
        ticker = str(raw.get("ticker", "")).strip().zfill(6)
        if len(ticker) != 6 or not ticker.isdigit():
            raise ValueError("historical P/B readiness contains invalid ticker")
        band_status = str(raw.get("historical_band_status", "")).strip()
        if band_status not in {
            "insufficient_history",
            "observational_1y_ready",
            "observational_2y_ready",
        }:
            raise ValueError("historical P/B readiness contains invalid band status")
        current = _bool(raw.get("current_observation_available"), "current observation")
        history_ready = _bool(
            raw.get("historical_band_history_ready"),
            "historical band history readiness",
        )
        usable = _bool(
            raw.get("current_observational_band_usable"),
            "current observational band usability",
        )
        if usable != (current and history_ready):
            raise ValueError("historical P/B readiness usability flags are inconsistent")
        percentile = _number(raw.get("latest_pb_percentile"), "latest_pb_percentile")
        if percentile < 0.0 or percentile > 100.0:
            raise ValueError("historical P/B percentile must be between 0 and 100")
        observation_count = int(_number(raw.get("observation_count"), "observation_count"))
        if observation_count <= 0:
            raise ValueError("historical P/B observation_count must be positive")
        rows.append(
            {
                "ticker": ticker,
                "observation_count": observation_count,
                "first_date": str(raw.get("first_date", "")),
                "last_date": str(raw.get("last_date", "")),
                "latest_observation_lag_days": int(
                    _number(raw.get("latest_observation_lag_days"), "latest lag")
                ),
                "current_observation_available": current,
                "historical_band_status": band_status,
                "historical_band_history_ready": history_ready,
                "current_observational_band_usable": usable,
                "latest_pb": _number(raw.get("latest_pb"), "latest_pb"),
                "pb_min": _number(raw.get("pb_min"), "pb_min"),
                "pb_p25": _number(raw.get("pb_p25"), "pb_p25"),
                "pb_median": _number(raw.get("pb_median"), "pb_median"),
                "pb_p75": _number(raw.get("pb_p75"), "pb_p75"),
                "pb_max": _number(raw.get("pb_max"), "pb_max"),
                "latest_pb_percentile": percentile,
            }
        )
    frame = pd.DataFrame(rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    if frame["ticker"].duplicated().any():
        raise ValueError("historical P/B readiness contains duplicate tickers")
    return HistoricalPbDecisionEvidence(
        artifact_id=artifact_id,
        evaluation_date=evaluation_date,
        symbols=frame,
    )


def attach_historical_pb_to_scorecards(
    scorecards: pd.DataFrame,
    evidence: HistoricalPbDecisionEvidence,
) -> pd.DataFrame:
    """Attach own-history P/B context while leaving score columns untouched."""

    if "ticker" not in scorecards.columns:
        raise ValueError("scorecards must contain ticker")
    result = scorecards.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    supplement = evidence.symbols.copy()
    supplement = supplement.rename(
        columns={
            column: f"historical_pb_{column}"
            for column in supplement.columns
            if column != "ticker"
        }
    )
    supplement["historical_pb_artifact_id"] = evidence.artifact_id
    supplement["historical_pb_decision_score_enabled"] = False
    supplement["historical_pb_historical_vintage_certified"] = False
    supplement["historical_pb_evidence_available"] = supplement[
        "historical_pb_current_observational_band_usable"
    ].astype(bool)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def sync_record_historical_pb_fields(
    records: pd.DataFrame,
    scorecards: pd.DataFrame,
) -> pd.DataFrame:
    """Copy compact P/B evidence fields into decision records."""

    fields = [
        "ticker",
        "evidence_gaps",
        "historical_pb_evidence_available",
        "historical_pb_artifact_id",
        "historical_pb_observation_count",
        "historical_pb_last_date",
        "historical_pb_latest_observation_lag_days",
        "historical_pb_current_observation_available",
        "historical_pb_historical_band_status",
        "historical_pb_current_observational_band_usable",
        "historical_pb_latest_pb",
        "historical_pb_pb_median",
        "historical_pb_pb_p75",
        "historical_pb_latest_pb_percentile",
        "historical_pb_decision_score_enabled",
        "historical_pb_historical_vintage_certified",
    ]
    available = [column for column in fields if column in scorecards.columns]
    supplement = scorecards.loc[:, available].copy()
    supplement["ticker"] = supplement["ticker"].astype("string").str.zfill(6)
    if supplement["ticker"].duplicated().any():
        raise ValueError("historical P/B scorecards contain duplicate tickers")
    result = records.copy()
    result["ticker"] = result["ticker"].astype("string").str.zfill(6)
    replaceable = [
        column for column in available if column != "ticker" and column in result.columns
    ]
    if replaceable:
        result = result.drop(columns=replaceable)
    return result.merge(supplement, on="ticker", how="left", validate="one_to_one")


def append_historical_pb_report(
    report: str,
    evidence: HistoricalPbDecisionEvidence,
) -> str:
    """Append current own-history P/B distribution context to the decision report."""

    lines = [
        report.rstrip(),
        "",
        "## 자사 역사 P/B 증거 (비점수)",
        "",
        f"- evaluation date: `{evidence.evaluation_date.isoformat()}`",
        f"- artifact: `{evidence.artifact_id[:12]}`",
        (
            "- 현재 가격은 unadjusted Kiwoom 가격과 해당 시점에 관측 가능한 "
            "OpenDART 주식수·자본으로 재구성했습니다."
        ),
        (
            "- historical vintage / PIT backtest 인증은 없으며 fair value·목표가·"
            "의사결정 점수에는 사용하지 않습니다."
        ),
        "",
        "| 종목 | 현재 P/B | P25 | 중앙값 | P75 | 역사 percentile | 관측치 | 상태 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for raw in evidence.symbols.to_dict(orient="records"):
        usable = bool(raw["current_observational_band_usable"])
        status = str(raw["historical_band_status"])
        if not bool(raw["current_observation_available"]):
            status += "/stale"
        elif not usable:
            status += "/current-but-not-ready"
        else:
            status += "/current"
        lines.append(
            "| "
            f"{raw['ticker']} | {float(raw['latest_pb']):.2f}x | "
            f"{float(raw['pb_p25']):.2f}x | {float(raw['pb_median']):.2f}x | "
            f"{float(raw['pb_p75']):.2f}x | "
            f"{float(raw['latest_pb_percentile']):.1f}% | "
            f"{int(raw['observation_count'])} | {status} |"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "HistoricalPbDecisionEvidence",
    "append_historical_pb_report",
    "attach_historical_pb_to_scorecards",
    "load_historical_pb_decision_evidence",
    "sync_record_historical_pb_fields",
]
