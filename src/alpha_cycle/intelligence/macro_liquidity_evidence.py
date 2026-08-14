"""Source-bounded macro/liquidity evidence for equity regime analysis.

The layer keeps discount-rate, dollar, financial-conditions, Fed balance-sheet,
and reserve-balance legs separate.  It does not invent a net-liquidity formula,
causal forecast, or investment score. Current official endpoints are not a
historical-vintage archive, so point-in-time backtest eligibility remains false.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd
import yaml


@dataclass(frozen=True)
class MacroLiquiditySeriesSpec:
    source_id: str
    series_id: str
    dimension: str
    label: str
    frequency: str
    unit: str
    interpretation: str
    url: str
    provider: str
    provider_owner: str
    underlying_source: str
    primary_official_system: bool

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.source_id,
                self.series_id,
                self.dimension,
                self.label,
                self.frequency,
                self.unit,
                self.interpretation,
                self.url,
                self.provider,
                self.provider_owner,
                self.underlying_source,
            )
        ):
            raise ValueError("Macro liquidity series fields cannot be blank")
        if self.provider != "fred":
            raise ValueError("Macro liquidity v1 supports only the registered FRED path")
        if not self.url.startswith("https://fred.stlouisfed.org/"):
            raise ValueError("Macro liquidity FRED URL must use the official FRED domain")
        if not self.primary_official_system:
            raise ValueError("Macro liquidity v1 requires official-system series")


@dataclass(frozen=True)
class MacroLiquidityEvidence:
    evidence_id: str
    evaluation_date: date
    series: pd.DataFrame
    observations: pd.DataFrame
    decision_score_enabled: bool = False
    composite_liquidity_score_enabled: bool = False
    forecast_enabled: bool = False
    causal_claim_enabled: bool = False
    historical_vintage_certified: bool = False
    point_in_time_backtest_eligible: bool = False

    def __post_init__(self) -> None:
        if len(self.evidence_id) != 64 or any(
            char not in "0123456789abcdef" for char in self.evidence_id
        ):
            raise ValueError("Macro liquidity evidence_id must be SHA-256")
        if self.series.empty or self.observations.empty:
            raise ValueError("Macro liquidity evidence requires series and observations")
        if (
            self.decision_score_enabled
            or self.composite_liquidity_score_enabled
            or self.forecast_enabled
            or self.causal_claim_enabled
            or self.historical_vintage_certified
            or self.point_in_time_backtest_eligible
        ):
            raise ValueError("Macro liquidity v1 must remain descriptive and non-PIT")


def load_macro_liquidity_registry(
    path: str | Path,
) -> tuple[MacroLiquiditySeriesSpec, ...]:
    with Path(path).open(encoding="utf-8") as handle:
        payload: object = yaml.safe_load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), dict):
        raise ValueError("Macro liquidity registry must contain sources")
    specs: list[MacroLiquiditySeriesSpec] = []
    for raw_id, raw_value in cast(dict[object, object], payload["sources"]).items():
        if not isinstance(raw_value, dict):
            raise ValueError(f"Macro liquidity source must be an object: {raw_id}")
        raw = cast(dict[object, object], raw_value)
        specs.append(
            MacroLiquiditySeriesSpec(
                source_id=str(raw_id).strip(),
                series_id=str(raw.get("series_id", "")).strip(),
                dimension=str(raw.get("dimension", "")).strip(),
                label=str(raw.get("label", "")).strip(),
                frequency=str(raw.get("frequency", "")).strip(),
                unit=str(raw.get("unit", "")).strip(),
                interpretation=str(raw.get("interpretation", "")).strip(),
                url=str(raw.get("url", "")).strip(),
                provider=str(raw.get("provider", "")).strip(),
                provider_owner=str(raw.get("provider_owner", "")).strip(),
                underlying_source=str(raw.get("underlying_source", "")).strip(),
                primary_official_system=bool(raw.get("primary_official_system", False)),
            )
        )
    if not specs:
        raise ValueError("Macro liquidity registry is empty")
    if len({spec.series_id for spec in specs}) != len(specs):
        raise ValueError("Macro liquidity registry repeats series_id")
    return tuple(specs)


def parse_fred_csv(spec: MacroLiquiditySeriesSpec, content: bytes) -> pd.DataFrame:
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise ValueError(f"FRED CSV could not be parsed: {spec.series_id}") from exc
    if "DATE" not in frame.columns or spec.series_id not in frame.columns:
        raise ValueError(f"FRED CSV columns do not match registered series: {spec.series_id}")
    result = frame.loc[:, ["DATE", spec.series_id]].rename(
        columns={"DATE": "observation_date", spec.series_id: "value"}
    )
    result["observation_date"] = pd.to_datetime(
        result["observation_date"], errors="raise"
    ).dt.date
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result = result.dropna(subset=["value"]).copy()
    if result.empty:
        raise ValueError(f"FRED CSV contains no numeric observations: {spec.series_id}")
    result["series_id"] = spec.series_id
    result["source_id"] = spec.source_id
    result["dimension"] = spec.dimension
    result["unit"] = spec.unit
    return result.sort_values("observation_date", kind="stable").reset_index(drop=True)


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    value = current / previous - 1.0
    return value if math.isfinite(value) else None


def _series_summary(spec: MacroLiquiditySeriesSpec, frame: pd.DataFrame) -> dict[str, object]:
    values = pd.to_numeric(frame["value"], errors="raise").astype(float).reset_index(drop=True)
    dates = frame["observation_date"].reset_index(drop=True)
    latest = float(values.iloc[-1])
    prior = float(values.iloc[-2]) if len(values) >= 2 else None
    base_4 = float(values.iloc[-5]) if len(values) >= 5 else float(values.iloc[0])
    base_20 = float(values.iloc[-21]) if len(values) >= 21 else float(values.iloc[0])
    change_1 = latest - prior if prior is not None else None
    change_4 = latest - base_4
    change_20 = latest - base_20
    pct_change_4 = _pct_change(latest, base_4)
    pct_change_20 = _pct_change(latest, base_20)

    if spec.series_id == "NFCI":
        level_state = "tighter_than_average" if latest > 0 else "looser_than_average" if latest < 0 else "average"
    else:
        level_state = "level_only_no_universal_threshold"

    return {
        "source_id": spec.source_id,
        "series_id": spec.series_id,
        "dimension": spec.dimension,
        "label": spec.label,
        "latest_date": dates.iloc[-1],
        "latest_value": latest,
        "unit": spec.unit,
        "observations": int(len(values)),
        "change_1": change_1,
        "change_4_observations": change_4,
        "change_20_observations": change_20,
        "pct_change_4_observations": pct_change_4,
        "pct_change_20_observations": pct_change_20,
        "level_state": level_state,
        "interpretation": spec.interpretation,
        "provider": spec.provider,
        "provider_owner": spec.provider_owner,
        "underlying_source": spec.underlying_source,
        "primary_official_system": True,
        "decision_score_enabled": False,
    }


def _json_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if pd.isna(value):
            return None
        if not math.isfinite(value):
            raise ValueError("Macro liquidity values must be finite")
    return value


def build_macro_liquidity_evidence(
    specs: tuple[MacroLiquiditySeriesSpec, ...],
    downloader: Callable[[str], bytes],
    *,
    evaluation_date: date,
) -> MacroLiquidityEvidence:
    observations: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []
    for spec in specs:
        frame = parse_fred_csv(spec, downloader(spec.url))
        visible = frame.loc[frame["observation_date"].le(evaluation_date)].copy()
        if visible.empty:
            raise ValueError(
                f"Macro liquidity series has no observations by evaluation date: {spec.series_id}"
            )
        observations.append(visible)
        summaries.append(_series_summary(spec, visible))
    observation_frame = pd.concat(observations, ignore_index=True).sort_values(
        ["series_id", "observation_date"], kind="stable"
    ).reset_index(drop=True)
    summary_frame = pd.DataFrame(summaries).sort_values(
        "series_id", kind="stable"
    ).reset_index(drop=True)
    payload = {
        "evaluation_date": evaluation_date.isoformat(),
        "series": [
            {str(key): _json_value(value) for key, value in raw.items()}
            for raw in summary_frame.to_dict(orient="records")
        ],
        "decision_score_enabled": False,
        "composite_liquidity_score_enabled": False,
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
    return MacroLiquidityEvidence(
        evidence_id=evidence_id,
        evaluation_date=evaluation_date,
        series=summary_frame,
        observations=observation_frame,
    )


__all__ = [
    "MacroLiquidityEvidence",
    "MacroLiquiditySeriesSpec",
    "build_macro_liquidity_evidence",
    "load_macro_liquidity_registry",
    "parse_fred_csv",
]
