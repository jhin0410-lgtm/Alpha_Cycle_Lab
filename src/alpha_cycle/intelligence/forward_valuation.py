"""Certified forward valuation state for Alpha Cycle Lab decision-system v2.

Forward valuation may use only expectations that already passed the provider-agnostic
ExpectationStateSnapshot contract.  Existing trailing valuation evidence supplies the
point-in-time market-cap state; this module never substitutes trailing actual earnings for
missing forward expectations and does not produce fair value or target prices.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import pandas as pd

from alpha_cycle.intelligence.expectation_state import (
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
)
from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot

FORWARD_VALUATION_SCHEMA_VERSION = 1


class ForwardValuationMetric(StrEnum):
    FORWARD_PE = "forward_pe"
    FORWARD_PS = "forward_ps"


class ForwardValuationStatus(StrEnum):
    AVAILABLE = "available"
    MARKET_CAP_UNAVAILABLE = "market_cap_unavailable"
    NON_POSITIVE_EXPECTATION = "non_positive_expectation"
    UNSUPPORTED_EXPECTATION_METRIC = "unsupported_expectation_metric"


@dataclass(frozen=True)
class ForwardValuationObservation:
    """One transparent forward multiple tied to one certified expectation observation."""

    security_id: str
    expectation_provider_id: str
    expectation_kind: ExpectationKind
    expectation_metric: ExpectationMetric
    target_period: str
    target_period_end: date
    expectation_observed_at: datetime
    expectation_source_evidence_id: str
    expectation_value: float
    expectation_unit: str
    expectation_value_krw: float
    market_cap_krw: float | None
    valuation_metric: ForwardValuationMetric | None
    multiple: float | None
    status: ForwardValuationStatus

    def __post_init__(self) -> None:
        _require_text(self.security_id, "security_id")
        _require_text(self.expectation_provider_id, "expectation_provider_id")
        _require_text(self.target_period, "target_period")
        _validate_sha(self.expectation_source_evidence_id, "expectation_source_evidence_id")
        if self.expectation_observed_at.tzinfo is None:
            raise ValueError("expectation_observed_at must be timezone-aware")
        _require_finite(self.expectation_value, "expectation_value")
        _require_finite(self.expectation_value_krw, "expectation_value_krw")
        if self.market_cap_krw is not None:
            _require_finite(self.market_cap_krw, "market_cap_krw")
            if self.market_cap_krw <= 0:
                raise ValueError("market_cap_krw must be positive when supplied")
        if self.multiple is not None:
            _require_finite(self.multiple, "multiple")
            if self.multiple <= 0:
                raise ValueError("forward valuation multiple must be positive")
        if self.status is ForwardValuationStatus.AVAILABLE:
            if self.market_cap_krw is None or self.multiple is None or self.valuation_metric is None:
                raise ValueError("available forward valuation requires market cap, metric, and multiple")
        elif self.multiple is not None:
            raise ValueError("unavailable forward valuation cannot expose a multiple")

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.security_id,
            self.expectation_provider_id,
            self.expectation_kind.value,
            self.expectation_metric.value,
            self.target_period,
        )

    def payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "expectation_provider_id": self.expectation_provider_id,
            "expectation_kind": self.expectation_kind.value,
            "expectation_metric": self.expectation_metric.value,
            "target_period": self.target_period,
            "target_period_end": self.target_period_end.isoformat(),
            "expectation_observed_at": self.expectation_observed_at.isoformat(),
            "expectation_source_evidence_id": self.expectation_source_evidence_id,
            "expectation_value": self.expectation_value,
            "expectation_unit": self.expectation_unit,
            "expectation_value_krw": self.expectation_value_krw,
            "market_cap_krw": self.market_cap_krw,
            "valuation_metric": self.valuation_metric.value if self.valuation_metric else None,
            "multiple": self.multiple,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class ForwardValuationStateSnapshot:
    """Content-addressed bridge from PIT market-cap evidence to certified expectations."""

    captured_at: datetime
    evaluation_date: date
    valuation_evidence_snapshot_id: str
    expectation_state_snapshot_id: str
    observations: tuple[ForwardValuationObservation, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        _validate_sha(self.valuation_evidence_snapshot_id, "valuation_evidence_snapshot_id")
        _validate_sha(self.expectation_state_snapshot_id, "expectation_state_snapshot_id")
        if not self.observations:
            raise ValueError("ForwardValuationStateSnapshot requires at least one observation")
        keys = [observation.key for observation in self.observations]
        if len(set(keys)) != len(keys):
            raise ValueError("ForwardValuationStateSnapshot contains duplicate observation keys")
        _validate_text_tuple(self.warnings, "warnings")

    def payload_without_id(self) -> dict[str, object]:
        ordered = sorted(self.observations, key=lambda observation: observation.key)
        return {
            "schema_version": FORWARD_VALUATION_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "valuation_evidence_snapshot_id": self.valuation_evidence_snapshot_id,
            "expectation_state_snapshot_id": self.expectation_state_snapshot_id,
            "observations": [observation.payload() for observation in ordered],
            "warnings": list(self.warnings),
            "fair_value_enabled": False,
            "target_price_enabled": False,
            "valuation_score_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


def build_forward_valuation_state(
    valuation: ValuationEvidenceSnapshot,
    expectations: ExpectationStateSnapshot,
    *,
    captured_at: datetime | None = None,
) -> ForwardValuationStateSnapshot:
    """Build forward multiples without trailing substitution or provider aggregation."""

    if valuation.evaluation_date != expectations.evaluation_date:
        raise ValueError("valuation and expectation states must share the same evaluation date")
    capture = captured_at or max(valuation.captured_at, expectations.captured_at)
    if capture.tzinfo is None or capture.utcoffset() is None:
        raise ValueError("forward valuation captured_at must be timezone-aware")
    if capture < valuation.captured_at or capture < expectations.captured_at:
        raise ValueError("forward valuation capture cannot precede either source snapshot")

    market_caps = _market_cap_lookup(valuation.valuation_metrics)
    rows = tuple(
        _build_observation(expectation, market_caps.get(expectation.security_id))
        for expectation in expectations.observations
    )
    warnings: list[str] = []
    if any(row.status is ForwardValuationStatus.MARKET_CAP_UNAVAILABLE for row in rows):
        warnings.append(
            "One or more forward expectations lack a complete point-in-time market capitalization."
        )
    if any(row.status is ForwardValuationStatus.UNSUPPORTED_EXPECTATION_METRIC for row in rows):
        warnings.append(
            "Some certified expectations are preserved but do not map to an enabled forward multiple."
        )
    if any(row.status is ForwardValuationStatus.NON_POSITIVE_EXPECTATION for row in rows):
        warnings.append(
            "Some forward multiples are unavailable because the certified denominator is non-positive."
        )
    return ForwardValuationStateSnapshot(
        captured_at=capture,
        evaluation_date=valuation.evaluation_date,
        valuation_evidence_snapshot_id=valuation.snapshot_id,
        expectation_state_snapshot_id=expectations.snapshot_id,
        observations=rows,
        warnings=tuple(warnings),
    )


def persist_forward_valuation_state(
    snapshot: ForwardValuationStateSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    """Persist an immutable forward-valuation snapshot and mutable latest pointer."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    pointer = root / "latest_forward_valuation_state.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot.snapshot_id:
            raise ValueError("existing forward-valuation directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            payload = snapshot.payload_without_id()
            available = sum(
                observation.status is ForwardValuationStatus.AVAILABLE
                for observation in snapshot.observations
            )
            manifest = {
                "schema_version": FORWARD_VALUATION_SCHEMA_VERSION,
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "evaluation_date": snapshot.evaluation_date.isoformat(),
                "valuation_evidence_snapshot_id": snapshot.valuation_evidence_snapshot_id,
                "expectation_state_snapshot_id": snapshot.expectation_state_snapshot_id,
                "observation_count": len(snapshot.observations),
                "available_multiple_count": available,
                "fair_value_enabled": False,
                "target_price_enabled": False,
                "valuation_score_enabled": False,
                "order_api_enabled": False,
                "warnings": list(snapshot.warnings),
                "files": ["forward_valuations.json"],
            }
            (temporary / "forward_valuations.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.rename(directory)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
    pointer.write_text(
        json.dumps(
            {
                "schema_version": FORWARD_VALUATION_SCHEMA_VERSION,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_path": str(directory),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pointer


def _build_observation(
    expectation: CertifiedExpectationObservation,
    market_cap_krw: float | None,
) -> ForwardValuationObservation:
    expectation_krw = _to_krw(expectation.value, expectation.unit)
    metric: ForwardValuationMetric | None
    if expectation.metric is ExpectationMetric.NET_INCOME:
        metric = ForwardValuationMetric.FORWARD_PE
    elif expectation.metric is ExpectationMetric.REVENUE:
        metric = ForwardValuationMetric.FORWARD_PS
    else:
        metric = None

    if market_cap_krw is None:
        status = ForwardValuationStatus.MARKET_CAP_UNAVAILABLE
        multiple = None
    elif metric is None:
        status = ForwardValuationStatus.UNSUPPORTED_EXPECTATION_METRIC
        multiple = None
    elif expectation_krw <= 0:
        status = ForwardValuationStatus.NON_POSITIVE_EXPECTATION
        multiple = None
    else:
        status = ForwardValuationStatus.AVAILABLE
        multiple = market_cap_krw / expectation_krw

    return ForwardValuationObservation(
        security_id=expectation.security_id,
        expectation_provider_id=expectation.provider_id,
        expectation_kind=expectation.expectation_kind,
        expectation_metric=expectation.metric,
        target_period=expectation.target_period,
        target_period_end=expectation.target_period_end,
        expectation_observed_at=expectation.observed_at,
        expectation_source_evidence_id=expectation.source_evidence_id,
        expectation_value=float(expectation.value),
        expectation_unit=expectation.unit,
        expectation_value_krw=expectation_krw,
        market_cap_krw=market_cap_krw,
        valuation_metric=metric,
        multiple=multiple,
        status=status,
    )


def _market_cap_lookup(frame: pd.DataFrame) -> dict[str, float | None]:
    required = {"ticker", "market_cap_complete", "market_cap"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("valuation_metrics missing columns: " + ",".join(sorted(missing)))
    output: dict[str, float | None] = {}
    for raw in frame.loc[:, ["ticker", "market_cap_complete", "market_cap"]].to_dict(
        orient="records"
    ):
        ticker = str(raw["ticker"]).strip()
        _require_text(ticker, "valuation ticker")
        if ticker in output:
            raise ValueError(f"duplicate valuation ticker: {ticker}")
        complete = bool(raw["market_cap_complete"])
        market_cap_raw = raw["market_cap"]
        market_cap = _optional_number(market_cap_raw)
        if complete and market_cap is None:
            raise ValueError(f"complete market cap is missing for ticker: {ticker}")
        if market_cap is not None and market_cap <= 0:
            raise ValueError(f"market cap must be positive for ticker: {ticker}")
        output[ticker] = market_cap if complete else None
    return output


def _to_krw(value: float, unit: str) -> float:
    factors = {
        "KRW": 1.0,
        "KRW_thousand": 1_000.0,
        "KRW_million": 1_000_000.0,
        "KRW_billion": 1_000_000_000.0,
        "KRW_trillion": 1_000_000_000_000.0,
    }
    try:
        factor = factors[unit]
    except KeyError as exc:
        raise ValueError(f"unsupported expectation currency/unit for valuation: {unit}") from exc
    result = float(value) * factor
    _require_finite(result, "expectation_value_krw")
    return result


def _optional_number(value: object) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _require_finite(value: float, field: str) -> None:
    if not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): item for key, item in cast(dict[object, object], payload).items()}


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ForwardValuationMetric",
    "ForwardValuationObservation",
    "ForwardValuationStateSnapshot",
    "ForwardValuationStatus",
    "build_forward_valuation_state",
    "persist_forward_valuation_state",
]
