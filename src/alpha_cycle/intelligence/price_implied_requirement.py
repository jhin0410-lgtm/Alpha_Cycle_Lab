"""Conditional price-implied operating requirements for Decision System v2.1.

This module does not claim that one operating number is literally the market consensus. It
inverts complete PIT market capitalization through explicitly frozen reference multiples and
reports the operating value that would be required *conditional on that reference frame*.
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

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DecisionSystemV21Guardrails,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.expectation_state import ExpectationMetric
from alpha_cycle.intelligence.forward_valuation import ForwardValuationMetric
from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot

PRICE_IMPLIED_SCHEMA_VERSION = 1


class ReferenceFrameKind(StrEnum):
    HISTORICAL_FORWARD_VINTAGE = "historical_forward_vintage"
    PEER_FORWARD_COMPS = "peer_forward_comps"
    EXPLICIT_SCENARIO_ASSUMPTION = "explicit_scenario_assumption"


class PriceImpliedRequirementStatus(StrEnum):
    AVAILABLE = "available"
    MARKET_CAP_UNAVAILABLE = "market_cap_unavailable"


@dataclass(frozen=True)
class ValuationReferencePoint:
    """One frozen conditional valuation multiple used for reverse inference."""

    reference_id: str
    metric: ForwardValuationMetric
    target_period: str
    target_period_end: date
    reference_multiple: float
    reference_kind: ReferenceFrameKind
    observed_at: datetime
    rationale: str
    source_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.reference_id, "reference_id")
        _require_text(self.target_period, "target_period")
        _require_text(self.rationale, "rationale")
        _require_aware(self.observed_at, "observed_at")
        _require_finite(self.reference_multiple, "reference_multiple")
        if self.reference_multiple <= 0:
            raise ValueError("reference_multiple must be positive")
        _validate_sha_tuple(self.source_evidence_ids, "source_evidence_ids")
        if (
            self.reference_kind is not ReferenceFrameKind.EXPLICIT_SCENARIO_ASSUMPTION
            and not self.source_evidence_ids
        ):
            raise ValueError(
                "evidence-based valuation reference requires source_evidence_ids"
            )

    def payload(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "metric": self.metric.value,
            "target_period": self.target_period,
            "target_period_end": self.target_period_end.isoformat(),
            "reference_multiple": self.reference_multiple,
            "reference_kind": self.reference_kind.value,
            "observed_at": self.observed_at.isoformat(),
            "rationale": self.rationale,
            "source_evidence_ids": list(self.source_evidence_ids),
            "market_expectation_certified": False,
        }


@dataclass(frozen=True)
class ValuationReferenceFrameSnapshot:
    """Content-addressed set of conditional multiple assumptions for one security."""

    captured_at: datetime
    evaluation_date: date
    security_id: str
    reference_points: tuple[ValuationReferencePoint, ...]
    source_snapshot_ids: tuple[str, ...]
    guardrail_evidence_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _require_text(self.security_id, "security_id")
        _validate_sha_tuple(self.source_snapshot_ids, "source_snapshot_ids")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _validate_text_tuple(self.warnings, "warnings")
        if not self.reference_points:
            raise ValueError("valuation reference frame requires at least one reference point")
        ids = [item.reference_id for item in self.reference_points]
        if len(set(ids)) != len(ids):
            raise ValueError("valuation reference frame contains duplicate reference ids")
        for point in self.reference_points:
            if point.observed_at > self.captured_at:
                raise ValueError("reference point cannot be observed after frame capture")
            if point.observed_at.date() > self.evaluation_date:
                raise ValueError("reference point is after the evaluation date")
            if point.target_period_end < self.evaluation_date:
                raise ValueError("price-implied reference target must not be historical")

    def payload_without_id(self) -> dict[str, object]:
        ordered = sorted(self.reference_points, key=lambda item: item.reference_id)
        return {
            "schema_version": PRICE_IMPLIED_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "security_id": self.security_id,
            "reference_points": [item.payload() for item in ordered],
            "source_snapshot_ids": sorted(self.source_snapshot_ids),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "warnings": list(self.warnings),
            "single_market_expectation_claimed": False,
            "reference_point_selection_enabled": False,
            "fair_value_enabled": False,
            "target_price_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class PriceImpliedRequirementObservation:
    """Operating value required by current market cap under one frozen reference multiple."""

    security_id: str
    reference_id: str
    reference_kind: ReferenceFrameKind
    valuation_metric: ForwardValuationMetric
    implied_metric: ExpectationMetric
    target_period: str
    target_period_end: date
    reference_multiple: float
    market_cap_krw: float | None
    implied_value_krw: float | None
    status: PriceImpliedRequirementStatus

    def __post_init__(self) -> None:
        _require_text(self.security_id, "security_id")
        _require_text(self.reference_id, "reference_id")
        _require_text(self.target_period, "target_period")
        _require_finite(self.reference_multiple, "reference_multiple")
        if self.reference_multiple <= 0:
            raise ValueError("reference_multiple must be positive")
        if self.market_cap_krw is not None:
            _require_finite(self.market_cap_krw, "market_cap_krw")
            if self.market_cap_krw <= 0:
                raise ValueError("market_cap_krw must be positive")
        if self.implied_value_krw is not None:
            _require_finite(self.implied_value_krw, "implied_value_krw")
            if self.implied_value_krw <= 0:
                raise ValueError("implied_value_krw must be positive")
        if self.status is PriceImpliedRequirementStatus.AVAILABLE:
            if self.market_cap_krw is None or self.implied_value_krw is None:
                raise ValueError("available price-implied requirement needs market cap and value")
        elif self.implied_value_krw is not None:
            raise ValueError("unavailable price-implied requirement cannot expose a value")

    @property
    def key(self) -> tuple[str, str]:
        return (self.security_id, self.reference_id)

    def payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "reference_id": self.reference_id,
            "reference_kind": self.reference_kind.value,
            "valuation_metric": self.valuation_metric.value,
            "implied_metric": self.implied_metric.value,
            "target_period": self.target_period,
            "target_period_end": self.target_period_end.isoformat(),
            "reference_multiple": self.reference_multiple,
            "market_cap_krw": self.market_cap_krw,
            "implied_value_krw": self.implied_value_krw,
            "status": self.status.value,
            "market_expectation_claimed": False,
        }


@dataclass(frozen=True)
class PriceImpliedRequirementSnapshot:
    """Conditional reverse-valuation surface, not a consensus forecast."""

    captured_at: datetime
    evaluation_date: date
    security_id: str
    valuation_evidence_snapshot_id: str
    reference_frame_snapshot_id: str
    guardrail_evidence_id: str
    observations: tuple[PriceImpliedRequirementObservation, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _require_text(self.security_id, "security_id")
        _validate_sha(
            self.valuation_evidence_snapshot_id,
            "valuation_evidence_snapshot_id",
        )
        _validate_sha(self.reference_frame_snapshot_id, "reference_frame_snapshot_id")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _validate_text_tuple(self.warnings, "warnings")
        if not self.observations:
            raise ValueError("price-implied requirement snapshot requires observations")
        keys = [item.key for item in self.observations]
        if len(set(keys)) != len(keys):
            raise ValueError("price-implied requirement contains duplicate observation keys")

    def payload_without_id(self) -> dict[str, object]:
        ordered = sorted(self.observations, key=lambda item: item.key)
        return {
            "schema_version": PRICE_IMPLIED_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "security_id": self.security_id,
            "valuation_evidence_snapshot_id": self.valuation_evidence_snapshot_id,
            "reference_frame_snapshot_id": self.reference_frame_snapshot_id,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "observations": [item.payload() for item in ordered],
            "warnings": list(self.warnings),
            "market_expectation_claimed": False,
            "single_price_implied_truth_claimed": False,
            "fair_value_enabled": False,
            "target_price_enabled": False,
            "decision_score_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


def build_valuation_reference_frame(
    *,
    captured_at: datetime,
    evaluation_date: date,
    security_id: str,
    reference_points: tuple[ValuationReferencePoint, ...],
    source_snapshot_ids: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> ValuationReferenceFrameSnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    return ValuationReferenceFrameSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        security_id=security_id,
        reference_points=reference_points,
        source_snapshot_ids=source_snapshot_ids,
        guardrail_evidence_id=active.evidence_id,
        warnings=warnings,
    )


def build_price_implied_requirement(
    valuation: ValuationEvidenceSnapshot,
    reference_frame: ValuationReferenceFrameSnapshot,
    *,
    captured_at: datetime | None = None,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> PriceImpliedRequirementSnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    if reference_frame.guardrail_evidence_id != active.evidence_id:
        raise ValueError("reference frame is bound to a different v2.1 guardrail snapshot")
    if valuation.evaluation_date != reference_frame.evaluation_date:
        raise ValueError("valuation and reference frame must share the same evaluation date")
    capture = captured_at or max(valuation.captured_at, reference_frame.captured_at)
    _require_aware(capture, "captured_at")
    if capture < valuation.captured_at or capture < reference_frame.captured_at:
        raise ValueError("price-implied capture cannot precede its source snapshots")

    market_cap = _market_cap_for_security(
        valuation.valuation_metrics,
        reference_frame.security_id,
    )
    rows = tuple(
        _build_requirement(reference_frame.security_id, point, market_cap)
        for point in reference_frame.reference_points
    )
    warnings = list(reference_frame.warnings)
    if market_cap is None:
        warnings.append(
            "Price-implied requirements are unavailable because complete PIT market cap "
            "is unavailable."
        )
    return PriceImpliedRequirementSnapshot(
        captured_at=capture,
        evaluation_date=valuation.evaluation_date,
        security_id=reference_frame.security_id,
        valuation_evidence_snapshot_id=valuation.snapshot_id,
        reference_frame_snapshot_id=reference_frame.snapshot_id,
        guardrail_evidence_id=active.evidence_id,
        observations=rows,
        warnings=tuple(warnings),
    )


def persist_valuation_reference_frame(
    snapshot: ValuationReferenceFrameSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
        "valuation_reference_frame",
    )


def persist_price_implied_requirement(
    snapshot: PriceImpliedRequirementSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
        "price_implied_requirement",
    )


def _build_requirement(
    security_id: str,
    point: ValuationReferencePoint,
    market_cap_krw: float | None,
) -> PriceImpliedRequirementObservation:
    if point.metric is ForwardValuationMetric.FORWARD_PE:
        implied_metric = ExpectationMetric.NET_INCOME
    elif point.metric is ForwardValuationMetric.FORWARD_PS:
        implied_metric = ExpectationMetric.REVENUE
    else:  # pragma: no cover - enum exhaustiveness defense
        raise ValueError(f"unsupported valuation metric: {point.metric}")
    if market_cap_krw is None:
        status = PriceImpliedRequirementStatus.MARKET_CAP_UNAVAILABLE
        implied_value = None
    else:
        status = PriceImpliedRequirementStatus.AVAILABLE
        implied_value = market_cap_krw / point.reference_multiple
    return PriceImpliedRequirementObservation(
        security_id=security_id,
        reference_id=point.reference_id,
        reference_kind=point.reference_kind,
        valuation_metric=point.metric,
        implied_metric=implied_metric,
        target_period=point.target_period,
        target_period_end=point.target_period_end,
        reference_multiple=point.reference_multiple,
        market_cap_krw=market_cap_krw,
        implied_value_krw=implied_value,
        status=status,
    )


def _market_cap_for_security(frame: pd.DataFrame, security_id: str) -> float | None:
    required = {"ticker", "market_cap_complete", "market_cap"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "valuation_metrics missing columns: " + ",".join(sorted(missing))
        )
    rows = frame.loc[
        frame["ticker"].astype(str).str.strip() == security_id,
        ["ticker", "market_cap_complete", "market_cap"],
    ].to_dict(orient="records")
    if len(rows) > 1:
        raise ValueError(f"duplicate valuation ticker: {security_id}")
    if not rows:
        return None
    complete_raw = rows[0]["market_cap_complete"]
    if not isinstance(complete_raw, bool):
        raise ValueError(
            f"market_cap_complete must be a boolean for ticker: {security_id}"
        )
    market_cap = _optional_number(rows[0]["market_cap"])
    if complete_raw and market_cap is None:
        raise ValueError(f"complete market cap is missing for ticker: {security_id}")
    if market_cap is not None and market_cap <= 0:
        raise ValueError(f"market cap must be positive for ticker: {security_id}")
    return market_cap if complete_raw else None


def _persist(
    snapshot_id: str,
    captured_at: datetime,
    payload: dict[str, object],
    output_root: str | Path,
    object_type: str,
) -> Path:
    root = Path(output_root) / object_type
    root.mkdir(parents=True, exist_ok=True)
    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot_id[:12]}"
    pointer = root / f"latest_{object_type}.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot_id:
            raise ValueError(f"existing {object_type} directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            filename = f"{object_type}.json"
            manifest = {
                "schema_version": PRICE_IMPLIED_SCHEMA_VERSION,
                "object_type": object_type,
                "snapshot_id": snapshot_id,
                "captured_at": captured_at.isoformat(),
                "immutable": True,
                "market_expectation_claimed": False,
                "fair_value_enabled": False,
                "target_price_enabled": False,
                "decision_score_enabled": False,
                "automatic_execution_enabled": False,
                "files": [filename],
            }
            (temporary / filename).write_text(
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
                "schema_version": PRICE_IMPLIED_SCHEMA_VERSION,
                "object_type": object_type,
                "snapshot_id": snapshot_id,
                "snapshot_path": str(directory),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pointer


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


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for text_value in values:
        _require_text(text_value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    for digest in values:
        _validate_sha(digest, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {
        str(key): item
        for key, item in cast(dict[object, object], payload).items()
    }


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
    "PriceImpliedRequirementObservation",
    "PriceImpliedRequirementSnapshot",
    "PriceImpliedRequirementStatus",
    "ReferenceFrameKind",
    "ValuationReferenceFrameSnapshot",
    "ValuationReferencePoint",
    "build_price_implied_requirement",
    "build_valuation_reference_frame",
    "persist_price_implied_requirement",
    "persist_valuation_reference_frame",
]
