"""Observational semiconductor industry-to-issuer earnings transmission evidence.

The module aligns revision-sensitive KOSIS semiconductor monthly diagnostics with
OpenDART issuer quarterly financial history.  It tests pre-declared economic
transmission hypotheses at 0-2 quarter lags.  The output is descriptive only:
KOSIS history is not point-in-time vintage certified, strongest observed lags are
in-sample descriptions, and no relationship changes an investment score or
creates a forecast.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

KOREA_TZ = ZoneInfo("Asia/Seoul")
MINIMUM_TRANSMISSION_OBSERVATIONS = 12
TRANSMISSION_LAGS = (0, 1, 2)


@dataclass(frozen=True)
class TransmissionHypothesis:
    feature: str
    target: str
    expected_sign: int
    rationale: str

    def __post_init__(self) -> None:
        if self.expected_sign not in {-1, 1}:
            raise ValueError("Transmission expected_sign must be -1 or 1")
        if not self.feature or not self.target or not self.rationale.strip():
            raise ValueError("Transmission hypothesis fields cannot be blank")


TRANSMISSION_HYPOTHESES = (
    TransmissionHypothesis(
        "shipment_yoy_pct",
        "revenue_yoy",
        1,
        "산업 출하 증가는 기업 매출 성장과 같은 방향이어야 한다.",
    ),
    TransmissionHypothesis(
        "shipment_yoy_pct",
        "operating_income_yoy",
        1,
        "산업 출하 증가는 고정비 레버리지와 함께 영업이익 성장에 우호적이어야 한다.",
    ),
    TransmissionHypothesis(
        "shipment_minus_inventory_yoy_pp",
        "operating_margin_change_yoy_pp",
        1,
        "출하가 재고보다 빠르게 증가하는 tightness는 가격·믹스와 마진에 우호적이어야 한다.",
    ),
    TransmissionHypothesis(
        "inventory_yoy_pct",
        "operating_margin_change_yoy_pp",
        -1,
        "재고 증가가 출하를 앞서는 국면은 가격·마진 압력과 연결될 수 있다.",
    ),
    TransmissionHypothesis(
        "utilization_yoy_pct",
        "operating_margin_change_yoy_pp",
        1,
        "가동률 상승은 고정비 흡수 개선을 통해 마진에 우호적이어야 한다.",
    ),
    TransmissionHypothesis(
        "utilization_yoy_pct",
        "operating_income_yoy",
        1,
        "가동률 상승은 영업레버리지와 이익 회복의 동행 신호여야 한다.",
    ),
    TransmissionHypothesis(
        "production_yoy_pct",
        "revenue_yoy",
        1,
        "산업 생산 증가는 기업 매출 성장과 대체로 같은 방향이어야 한다.",
    ),
    TransmissionHypothesis(
        "capacity_yoy_pct",
        "revenue_yoy",
        1,
        "공급능력 증가는 중기 매출 잠재력과 양의 관계를 가질 수 있다.",
    ),
)


@dataclass(frozen=True)
class SemiconductorTransmissionEvidence:
    evidence_id: str
    evaluation_date: date
    kosis_artifact_id: str
    relationships: pd.DataFrame
    quarterly_industry: pd.DataFrame
    quarterly_issuer: pd.DataFrame
    decision_score_enabled: bool = False
    forecast_enabled: bool = False
    causal_claim_enabled: bool = False
    point_in_time_backtest_eligible: bool = False
    historical_vintage_certified: bool = False

    def __post_init__(self) -> None:
        for value, field in (
            (self.evidence_id, "evidence_id"),
            (self.kosis_artifact_id, "kosis_artifact_id"),
        ):
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{field} must be a lowercase SHA-256 digest")
        if self.relationships.empty:
            raise ValueError("Semiconductor transmission contains no relationships")
        if self.decision_score_enabled or self.forecast_enabled or self.causal_claim_enabled:
            raise ValueError("Semiconductor transmission must remain descriptive and non-scoring")
        if self.point_in_time_backtest_eligible or self.historical_vintage_certified:
            raise ValueError("Revision-sensitive KOSIS transmission cannot claim PIT certification")


def _json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast(Mapping[str, object], payload)


def _false_flag(payload: Mapping[str, object], key: str) -> None:
    if payload.get(key) is not False:
        raise ValueError(f"KOSIS transmission requires {key}=false")


def _sha(value: object, field: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"KOSIS transmission {field} must be SHA-256")
    return text


def _load_kosis_monthly(
    pointer_path: Path,
    evaluation_date: date,
) -> tuple[str, pd.DataFrame]:
    pointer = _json_object(pointer_path, "KOSIS semiconductor history pointer")
    if str(pointer.get("status", "")) != "semiconductor_history_captured":
        raise ValueError("KOSIS semiconductor pointer status is not captured")
    for key in (
        "historical_vintage_certified",
        "point_in_time_backtest_eligible",
        "decision_score_enabled",
    ):
        _false_flag(pointer, key)
    artifact_id = _sha(pointer.get("artifact_id"), "artifact_id")
    manifest_path = Path(str(pointer.get("manifest_path", "")).strip())
    diagnostics_path = Path(str(pointer.get("diagnostics_path", "")).strip())
    if not str(manifest_path) or not str(diagnostics_path):
        raise ValueError("KOSIS semiconductor pointer paths are incomplete")

    manifest = _json_object(manifest_path, "KOSIS semiconductor manifest")
    if _sha(manifest.get("artifact_id"), "manifest artifact_id") != artifact_id:
        raise ValueError("KOSIS semiconductor pointer/manifest artifact mismatch")
    for key in (
        "historical_vintage_certified",
        "point_in_time_backtest_eligible",
        "decision_score_enabled",
    ):
        _false_flag(manifest, key)
    if manifest.get("revision_sensitive") is not True:
        raise ValueError("KOSIS transmission requires revision_sensitive=true")
    captured_text = str(manifest.get("captured_at", "")).strip()
    try:
        captured = datetime.fromisoformat(captured_text)
    except ValueError as exc:
        raise ValueError("KOSIS semiconductor captured_at is invalid") from exc
    if captured.tzinfo is None or captured.utcoffset() is None:
        raise ValueError("KOSIS semiconductor captured_at must be timezone-aware")
    if captured.astimezone(KOREA_TZ).date() > evaluation_date:
        raise ValueError("KOSIS current history cannot be applied before capture date")

    diagnostics = _json_object(diagnostics_path, "KOSIS semiconductor diagnostics")
    monthly_raw = diagnostics.get("monthly")
    if not isinstance(monthly_raw, list) or not monthly_raw:
        raise ValueError("KOSIS semiconductor diagnostics monthly history is missing")
    rows: list[dict[str, object]] = []
    for value in monthly_raw:
        if not isinstance(value, dict):
            raise ValueError("KOSIS semiconductor monthly row must be an object")
        raw = cast(Mapping[str, object], value)
        period = str(raw.get("period", "")).strip()
        if len(period) != 6 or not period.isdigit():
            raise ValueError("KOSIS semiconductor monthly period must be YYYYMM")
        year, month = int(period[:4]), int(period[4:])
        if month < 1 or month > 12:
            raise ValueError("KOSIS semiconductor monthly period month is invalid")
        month_end = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
        if month_end.date() > evaluation_date:
            continue
        row: dict[str, object] = {"period": period, "month_end": month_end}
        for column in (
            "production_yoy_pct",
            "shipment_yoy_pct",
            "inventory_yoy_pct",
            "capacity_yoy_pct",
            "utilization_yoy_pct",
            "production_mom_sa_pct",
            "shipment_mom_sa_pct",
            "inventory_mom_sa_pct",
            "utilization_mom_sa_pct",
            "shipment_minus_inventory_yoy_pp",
            "production_minus_shipment_yoy_pp",
            "inventory_vs_shipment_index_ratio",
        ):
            row[column] = pd.to_numeric(pd.Series([raw.get(column)]), errors="coerce").iloc[0]
        rows.append(row)
    monthly = pd.DataFrame(rows).sort_values("month_end", kind="stable").reset_index(drop=True)
    if monthly.empty:
        raise ValueError("KOSIS semiconductor monthly history has no rows by evaluation date")
    return artifact_id, monthly


def _quarterize_industry(monthly: pd.DataFrame) -> pd.DataFrame:
    values = monthly.copy()
    values["quarter"] = values["month_end"].dt.to_period("Q")
    metric_columns = [
        column
        for column in values.columns
        if column not in {"period", "month_end", "quarter"}
    ]
    rows: list[dict[str, object]] = []
    for quarter, group in values.groupby("quarter", sort=True):
        ordered = group.sort_values("month_end", kind="stable")
        row: dict[str, object] = {
            "quarter": str(quarter),
            "quarter_end": cast(pd.Period, quarter).end_time.normalize(),
            "months_available": int(len(ordered)),
        }
        for column in metric_columns:
            numeric = pd.to_numeric(ordered[column], errors="coerce").dropna()
            row[column] = float(numeric.mean()) if not numeric.empty else np.nan
            row[f"{column}__quarter_end"] = (
                float(numeric.iloc[-1]) if not numeric.empty else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("quarter_end", kind="stable").reset_index(drop=True)


def _quarterize_issuer(financial_history: pd.DataFrame, evaluation_date: date) -> pd.DataFrame:
    required = {
        "ticker",
        "period_label",
        "period_end",
        "available_date",
        "revenue_yoy",
        "operating_income_yoy",
        "operating_margin_change_yoy_pp",
    }
    missing = required - set(financial_history.columns)
    if missing:
        raise ValueError(
            "Semiconductor transmission financial history missing columns: "
            + ",".join(sorted(missing))
        )
    history = financial_history.copy()
    history["ticker"] = history["ticker"].astype("string").str.strip().str.zfill(6)
    history["period_end"] = pd.to_datetime(history["period_end"], errors="raise")
    history["available_date"] = pd.to_datetime(history["available_date"], errors="raise")
    history = history.loc[
        history["ticker"].isin({"005930", "000660"})
        & history["period_label"].astype(str).isin({"Q1", "Q2", "Q3", "Q4"})
        & history["period_end"].le(pd.Timestamp(evaluation_date))
        & history["available_date"].le(pd.Timestamp(evaluation_date))
    ].copy()
    if history.empty:
        raise ValueError("Semiconductor transmission has no visible issuer quarters")
    if history.duplicated(["ticker", "period_end"]).any():
        duplicates = history.loc[
            history.duplicated(["ticker", "period_end"], keep=False),
            ["ticker", "period_end", "period_label"],
        ]
        raise ValueError(f"Semiconductor transmission duplicate issuer quarters: {duplicates.to_dict('records')}")
    history["quarter"] = history["period_end"].dt.to_period("Q").astype(str)
    for column in (
        "revenue_yoy",
        "operating_income_yoy",
        "operating_margin_change_yoy_pp",
    ):
        history[column] = pd.to_numeric(history[column], errors="coerce")
    return history.sort_values(["ticker", "period_end"], kind="stable").reset_index(drop=True)


def _correlation(x: pd.Series, y: pd.Series, method: str) -> float | None:
    if len(x) < 2 or len(y) < 2:
        return None
    value = x.corr(y, method=method)
    if pd.isna(value):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _relationship_rows(
    industry: pd.DataFrame,
    issuer: pd.DataFrame,
) -> pd.DataFrame:
    industry_lookup = industry.set_index("quarter")
    rows: list[dict[str, object]] = []
    for ticker, company in issuer.groupby("ticker", sort=True):
        company = company.sort_values("period_end", kind="stable")
        for hypothesis in TRANSMISSION_HYPOTHESES:
            lag_rows: list[dict[str, object]] = []
            for lag in TRANSMISSION_LAGS:
                aligned_x: list[float] = []
                aligned_y: list[float] = []
                for raw in company.to_dict(orient="records"):
                    quarter = pd.Period(str(raw["quarter"]), freq="Q")
                    industry_quarter = str(quarter - lag)
                    if industry_quarter not in industry_lookup.index:
                        continue
                    feature_raw = industry_lookup.loc[industry_quarter, hypothesis.feature]
                    target_raw = raw.get(hypothesis.target)
                    feature = pd.to_numeric(pd.Series([feature_raw]), errors="coerce").iloc[0]
                    target = pd.to_numeric(pd.Series([target_raw]), errors="coerce").iloc[0]
                    if pd.isna(feature) or pd.isna(target):
                        continue
                    aligned_x.append(float(feature))
                    aligned_y.append(float(target))
                x = pd.Series(aligned_x, dtype="float64")
                y = pd.Series(aligned_y, dtype="float64")
                pearson = _correlation(x, y, "pearson")
                spearman = _correlation(x, y, "spearman")
                observation_count = int(len(x))
                ready = observation_count >= MINIMUM_TRANSMISSION_OBSERVATIONS
                sign_supported = (
                    ready
                    and spearman is not None
                    and math.copysign(1, spearman) == hypothesis.expected_sign
                )
                lag_rows.append(
                    {
                        "ticker": str(ticker),
                        "feature": hypothesis.feature,
                        "target": hypothesis.target,
                        "lag_quarters": lag,
                        "expected_sign": hypothesis.expected_sign,
                        "rationale": hypothesis.rationale,
                        "observation_count": observation_count,
                        "history_ready": ready,
                        "pearson": pearson if ready else None,
                        "spearman": spearman if ready else None,
                        "expected_sign_supported": bool(sign_supported) if ready else None,
                        "decision_score_enabled": False,
                        "forecast_enabled": False,
                        "causal_claim_enabled": False,
                    }
                )
            ready_rows = [
                row
                for row in lag_rows
                if bool(row["history_ready"]) and row["spearman"] is not None
            ]
            strongest_lag: int | None = None
            strongest_abs_spearman: float | None = None
            if ready_rows:
                strongest = max(
                    ready_rows,
                    key=lambda row: abs(float(cast(float, row["spearman"]))),
                )
                strongest_lag = int(cast(int, strongest["lag_quarters"]))
                strongest_abs_spearman = abs(float(cast(float, strongest["spearman"])))
            for row in lag_rows:
                row["strongest_observed_lag_quarters"] = strongest_lag
                row["strongest_observed_abs_spearman"] = strongest_abs_spearman
                row["lag_selection_is_in_sample_descriptive"] = True
                rows.append(row)
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("Semiconductor transmission produced no relationship rows")
    return result.sort_values(
        ["ticker", "feature", "target", "lag_quarters"],
        kind="stable",
    ).reset_index(drop=True)


def _serializable(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, np.generic):
        return _serializable(value.item())
    if isinstance(value, float):
        if np.isnan(value):
            return None
        if not np.isfinite(value):
            raise ValueError("Semiconductor transmission values must be finite")
    return value


def build_semiconductor_transmission_evidence(
    kosis_history_pointer: str | Path,
    financial_history: pd.DataFrame,
    *,
    evaluation_date: date,
) -> SemiconductorTransmissionEvidence:
    """Build non-scoring lagged industry-to-issuer transmission evidence."""

    artifact_id, monthly = _load_kosis_monthly(Path(kosis_history_pointer), evaluation_date)
    industry = _quarterize_industry(monthly)
    issuer = _quarterize_issuer(financial_history, evaluation_date)
    relationships = _relationship_rows(industry, issuer)
    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "kosis_artifact_id": artifact_id,
        "minimum_observations": MINIMUM_TRANSMISSION_OBSERVATIONS,
        "lags": list(TRANSMISSION_LAGS),
        "relationships": [
            {str(key): _serializable(value) for key, value in raw.items()}
            for raw in relationships.to_dict(orient="records")
        ],
        "decision_score_enabled": False,
        "forecast_enabled": False,
        "causal_claim_enabled": False,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
    }
    evidence_id = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return SemiconductorTransmissionEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        kosis_artifact_id=artifact_id,
        relationships=relationships,
        quarterly_industry=industry,
        quarterly_issuer=issuer,
    )


def summarize_semiconductor_transmission(
    evidence: SemiconductorTransmissionEvidence,
) -> pd.DataFrame:
    """Collapse lag rows into one descriptive readiness row per hypothesis/ticker."""

    rows: list[dict[str, object]] = []
    grouped = evidence.relationships.groupby(["ticker", "feature", "target"], sort=True)
    for (ticker, feature, target), group in grouped:
        ready = group.loc[group["history_ready"].astype(bool)].copy()
        strongest_lag = group["strongest_observed_lag_quarters"].dropna()
        strongest_value = group["strongest_observed_abs_spearman"].dropna()
        expected_sign = int(group["expected_sign"].iloc[0])
        support_count = int(
            ready["expected_sign_supported"].fillna(False).astype(bool).sum()
        )
        rows.append(
            {
                "ticker": str(ticker),
                "feature": str(feature),
                "target": str(target),
                "expected_sign": expected_sign,
                "ready_lag_count": int(len(ready)),
                "total_lag_count": int(len(group)),
                "expected_sign_supported_lag_count": support_count,
                "strongest_observed_lag_quarters": (
                    int(strongest_lag.iloc[0]) if not strongest_lag.empty else None
                ),
                "strongest_observed_abs_spearman": (
                    float(strongest_value.iloc[0]) if not strongest_value.empty else None
                ),
                "transmission_status": (
                    "descriptive_history_ready" if not ready.empty else "insufficient_history"
                ),
                "decision_score_enabled": False,
                "forecast_enabled": False,
                "causal_claim_enabled": False,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["ticker", "feature", "target"], kind="stable"
    ).reset_index(drop=True)


def append_semiconductor_transmission_report(
    report: str,
    evidence: SemiconductorTransmissionEvidence,
) -> str:
    summary = summarize_semiconductor_transmission(evidence)
    lines = [
        report.rstrip(),
        "",
        "## 반도체 산업 → 기업 실적 transmission (관측·비점수)",
        "",
        f"- evidence: `{evidence.evidence_id[:12]}` / KOSIS `{evidence.kosis_artifact_id[:12]}`",
        (
            f"- 최소 표본: {MINIMUM_TRANSMISSION_OBSERVATIONS}개 분기; "
            "0~2분기 lag를 모두 보고 strongest lag는 in-sample descriptive 값으로만 표시합니다."
        ),
        "- KOSIS history는 revision-sensitive이고 historical vintage가 인증되지 않아 PIT backtest·forecast·causal claim에 사용하지 않습니다.",
        "- 이 섹션은 composite/valuation score를 변경하지 않습니다.",
        "",
        "| 종목 | 산업 변수 | 기업 변수 | 준비 lag | 예상부호 지지 | strongest lag | |ρ| | 상태 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for raw in summary.to_dict(orient="records"):
        lag = raw.get("strongest_observed_lag_quarters")
        strength = raw.get("strongest_observed_abs_spearman")
        lag_text = "N/A" if lag is None or pd.isna(lag) else str(int(cast(int, lag)))
        strength_text = (
            "N/A" if strength is None or pd.isna(strength) else f"{float(strength):.2f}"
        )
        lines.append(
            f"| {raw['ticker']} | {raw['feature']} | {raw['target']} | "
            f"{raw['ready_lag_count']}/{raw['total_lag_count']} | "
            f"{raw['expected_sign_supported_lag_count']} | {lag_text} | "
            f"{strength_text} | {raw['transmission_status']} |"
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "MINIMUM_TRANSMISSION_OBSERVATIONS",
    "TRANSMISSION_HYPOTHESES",
    "TRANSMISSION_LAGS",
    "SemiconductorTransmissionEvidence",
    "TransmissionHypothesis",
    "append_semiconductor_transmission_report",
    "build_semiconductor_transmission_evidence",
    "summarize_semiconductor_transmission",
]
