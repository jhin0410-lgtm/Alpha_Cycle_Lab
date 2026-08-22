"""Prospective numeric forecast ledger for Alpha Cycle Lab Decision System v2.1.

The ledger separates immutable forecast registration, later target-level outcome observation,
and later evaluation. It can reference forecasts already frozen by another research contract
without pretending the generic ledger existed at the original forecast time.
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

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DecisionSystemV21Guardrails,
    load_decision_system_v21_guardrails,
)

FORECAST_LEDGER_SCHEMA_VERSION = 1
EVALUATION_RULE_VERSION = "numeric-point-v1"


class ForecastRegistrationMode(StrEnum):
    NATIVE_PROSPECTIVE = "native_prospective"
    EXTERNAL_FROZEN_REFERENCE = "external_frozen_reference"


class ForecasterKind(StrEnum):
    MODEL = "model"
    HUMAN = "human"
    MARKET_CONSENSUS = "market_consensus"
    HYBRID = "hybrid"
    BENCHMARK = "benchmark"


class ForecastDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


class OrdinalAssessment(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class PrimaryErrorMetric(StrEnum):
    ABSOLUTE_ERROR = "absolute_error"
    SQUARED_ERROR = "squared_error"
    ABSOLUTE_PERCENTAGE_ERROR = "absolute_percentage_error"


class DiagnosticAvailability(StrEnum):
    OBSERVED = "observed"
    NOT_ESTIMABLE_SINGLE_FORECAST = "not_estimable_single_forecast"
    NOT_EVALUATED_WITHOUT_BASELINE = "not_evaluated_without_baseline"


@dataclass(frozen=True)
class ForecastRegistrationSnapshot:
    """Immutable point forecast registered before its protected outcome is observed."""

    forecast_id: str
    registered_at: datetime
    ledger_recorded_at: datetime
    forecast_origin: datetime
    information_cutoff: datetime
    security_id: str
    target_variable: str
    target_date: date
    horizon_label: str
    forecast_value: float
    unit: str
    range_lower: float | None
    range_upper: float | None
    direction: ForecastDirection | None
    direction_reference_value: float | None
    direction_flat_tolerance: float
    confidence: OrdinalAssessment
    confidence_rationale: str
    forecaster_kind: ForecasterKind
    model_family: str
    driver_refs: tuple[str, ...]
    regime_tags: tuple[str, ...]
    decision_relevance: OrdinalAssessment
    difficulty: OrdinalAssessment
    baseline_refs: tuple[str, ...]
    dependency_cluster_id: str
    source_evidence_ids: tuple[str, ...]
    registration_mode: ForecastRegistrationMode
    primary_error_metric: PrimaryErrorMetric
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.forecast_id, "forecast_id"),
            (self.security_id, "security_id"),
            (self.target_variable, "target_variable"),
            (self.horizon_label, "horizon_label"),
            (self.unit, "unit"),
            (self.confidence_rationale, "confidence_rationale"),
            (self.model_family, "model_family"),
            (self.dependency_cluster_id, "dependency_cluster_id"),
        ):
            _require_text(value, field)
        for value, field in (
            (self.registered_at, "registered_at"),
            (self.ledger_recorded_at, "ledger_recorded_at"),
            (self.forecast_origin, "forecast_origin"),
            (self.information_cutoff, "information_cutoff"),
        ):
            _require_aware(value, field)
        if self.information_cutoff > self.registered_at:
            raise ValueError("information_cutoff cannot occur after registered_at")
        if self.registered_at > self.ledger_recorded_at:
            raise ValueError("ledger_recorded_at cannot precede original registration")
        if self.registered_at > self.forecast_origin:
            raise ValueError("forecast must be registered no later than forecast_origin")
        if self.registration_mode is ForecastRegistrationMode.NATIVE_PROSPECTIVE:
            if self.ledger_recorded_at > self.forecast_origin:
                raise ValueError("native ledger registration cannot occur after forecast_origin")
        if self.target_date <= self.forecast_origin.date():
            raise ValueError("forecast target_date must be after forecast_origin")
        _require_finite(self.forecast_value, "forecast_value")
        _validate_range(self)
        if not math.isfinite(self.direction_flat_tolerance):
            raise ValueError("direction_flat_tolerance must be finite")
        if self.direction_flat_tolerance < 0:
            raise ValueError("direction_flat_tolerance must be non-negative")
        if self.direction is None:
            if self.direction_reference_value is not None:
                raise ValueError("direction_reference_value requires a direction forecast")
        else:
            if self.direction_reference_value is None:
                raise ValueError("direction forecast requires direction_reference_value")
            _require_finite(
                self.direction_reference_value,
                "direction_reference_value",
            )
        _validate_text_refs(self.driver_refs, "driver_refs")
        _validate_text_refs(self.regime_tags, "regime_tags")
        _validate_sha_refs(self.baseline_refs, "baseline_refs")
        _validate_sha_refs(self.source_evidence_ids, "source_evidence_ids")
        if not self.source_evidence_ids:
            raise ValueError("forecast registration requires source_evidence_ids")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")

    @property
    def target_key(self) -> tuple[str, str, date, str]:
        return (
            self.security_id,
            self.target_variable,
            self.target_date,
            self.unit,
        )

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": FORECAST_LEDGER_SCHEMA_VERSION,
            "forecast_id": self.forecast_id,
            "registered_at": self.registered_at.isoformat(),
            "ledger_recorded_at": self.ledger_recorded_at.isoformat(),
            "forecast_origin": self.forecast_origin.isoformat(),
            "information_cutoff": self.information_cutoff.isoformat(),
            "security_id": self.security_id,
            "target_variable": self.target_variable,
            "target_date": self.target_date.isoformat(),
            "horizon_label": self.horizon_label,
            "forecast_value": float(self.forecast_value),
            "unit": self.unit,
            "range_lower": self.range_lower,
            "range_upper": self.range_upper,
            "direction": self.direction.value if self.direction else None,
            "direction_reference_value": self.direction_reference_value,
            "direction_flat_tolerance": self.direction_flat_tolerance,
            "confidence": self.confidence.value,
            "confidence_rationale": self.confidence_rationale,
            "forecaster_kind": self.forecaster_kind.value,
            "model_family": self.model_family,
            "driver_refs": list(self.driver_refs),
            "regime_tags": list(self.regime_tags),
            "decision_relevance": self.decision_relevance.value,
            "difficulty": self.difficulty.value,
            "baseline_refs": list(self.baseline_refs),
            "dependency_cluster_id": self.dependency_cluster_id,
            "source_evidence_ids": list(self.source_evidence_ids),
            "registration_mode": self.registration_mode.value,
            "primary_error_metric": self.primary_error_metric.value,
            "evaluation_rule_version": EVALUATION_RULE_VERSION,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "outcome_observed": False,
            "evaluation_run": False,
            "composite_forecast_score_enabled": False,
            "order_api_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class ForecastOutcomeSnapshot:
    """One target-level actual that can score every comparable forecast registration."""

    captured_at: datetime
    outcome_observed_at: datetime
    security_id: str
    target_variable: str
    target_date: date
    actual_value: float
    unit: str
    source_evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _require_aware(self.outcome_observed_at, "outcome_observed_at")
        if self.captured_at < self.outcome_observed_at:
            raise ValueError("outcome capture cannot precede source observation")
        if self.outcome_observed_at.date() < self.target_date:
            raise ValueError("outcome cannot be observed before target_date")
        _require_text(self.security_id, "security_id")
        _require_text(self.target_variable, "target_variable")
        _require_text(self.unit, "unit")
        _require_finite(self.actual_value, "actual_value")
        _validate_sha_refs(self.source_evidence_ids, "source_evidence_ids")
        if not self.source_evidence_ids:
            raise ValueError("forecast outcome requires source_evidence_ids")

    @property
    def target_key(self) -> tuple[str, str, date, str]:
        return (
            self.security_id,
            self.target_variable,
            self.target_date,
            self.unit,
        )

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": FORECAST_LEDGER_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "outcome_observed_at": self.outcome_observed_at.isoformat(),
            "security_id": self.security_id,
            "target_variable": self.target_variable,
            "target_date": self.target_date.isoformat(),
            "actual_value": float(self.actual_value),
            "unit": self.unit,
            "source_evidence_ids": list(self.source_evidence_ids),
            "forecast_registration_specific": False,
            "order_api_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class ForecastAccuracyDiagnostics:
    signed_error: float
    absolute_error: float
    squared_error: float
    absolute_percentage_error: float | None
    direction_correct: bool | None
    inside_predeclared_range: bool | None

    def __post_init__(self) -> None:
        for value, field in (
            (self.signed_error, "signed_error"),
            (self.absolute_error, "absolute_error"),
            (self.squared_error, "squared_error"),
        ):
            _require_finite(value, field)
        if self.absolute_error < 0 or self.squared_error < 0:
            raise ValueError("absolute and squared errors must be non-negative")
        if self.absolute_percentage_error is not None:
            _require_finite(
                self.absolute_percentage_error,
                "absolute_percentage_error",
            )
            if self.absolute_percentage_error < 0:
                raise ValueError("absolute_percentage_error must be non-negative")

    def payload(self) -> dict[str, object]:
        return {
            "signed_error": self.signed_error,
            "absolute_error": self.absolute_error,
            "squared_error": self.squared_error,
            "absolute_percentage_error": self.absolute_percentage_error,
            "direction_correct": self.direction_correct,
            "inside_predeclared_range": self.inside_predeclared_range,
        }


@dataclass(frozen=True)
class ForecastEvaluationSnapshot:
    """Immutable evaluation created only after registration and outcome snapshots exist."""

    registration_snapshot_id: str
    outcome_snapshot_id: str
    evaluated_at: datetime
    forecast_value: float
    actual_value: float
    unit: str
    primary_error_metric: PrimaryErrorMetric
    primary_error_value: float
    accuracy: ForecastAccuracyDiagnostics
    calibration: DiagnosticAvailability
    decision_relevance: OrdinalAssessment
    information_gain: DiagnosticAvailability
    difficulty: OrdinalAssessment
    baseline_evaluation_refs: tuple[str, ...]
    absolute_error_advantage_vs_baseline: float | None

    def __post_init__(self) -> None:
        _validate_sha(self.registration_snapshot_id, "registration_snapshot_id")
        _validate_sha(self.outcome_snapshot_id, "outcome_snapshot_id")
        _require_aware(self.evaluated_at, "evaluated_at")
        _require_finite(self.forecast_value, "forecast_value")
        _require_finite(self.actual_value, "actual_value")
        _require_text(self.unit, "unit")
        _require_finite(self.primary_error_value, "primary_error_value")
        if self.primary_error_value < 0:
            raise ValueError("primary_error_value must be non-negative")
        _validate_sha_refs(self.baseline_evaluation_refs, "baseline_evaluation_refs")
        if self.absolute_error_advantage_vs_baseline is None:
            if self.baseline_evaluation_refs:
                raise ValueError(
                    "baseline evaluation refs require an explicit absolute-error advantage"
                )
            if self.information_gain is DiagnosticAvailability.OBSERVED:
                raise ValueError("observed information gain requires a baseline evaluation")
        else:
            _require_finite(
                self.absolute_error_advantage_vs_baseline,
                "absolute_error_advantage_vs_baseline",
            )
            if not self.baseline_evaluation_refs:
                raise ValueError("baseline advantage requires baseline_evaluation_refs")
            if self.information_gain is not DiagnosticAvailability.OBSERVED:
                raise ValueError("baseline advantage requires observed information gain")
        if self.calibration is DiagnosticAvailability.OBSERVED:
            raise ValueError("single-forecast evaluation cannot claim observed calibration")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": FORECAST_LEDGER_SCHEMA_VERSION,
            "registration_snapshot_id": self.registration_snapshot_id,
            "outcome_snapshot_id": self.outcome_snapshot_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "forecast_value": self.forecast_value,
            "actual_value": self.actual_value,
            "unit": self.unit,
            "primary_error_metric": self.primary_error_metric.value,
            "primary_error_value": self.primary_error_value,
            "accuracy": self.accuracy.payload(),
            "calibration": self.calibration.value,
            "decision_relevance": self.decision_relevance.value,
            "information_gain": self.information_gain.value,
            "difficulty": self.difficulty.value,
            "baseline_evaluation_refs": list(self.baseline_evaluation_refs),
            "absolute_error_advantage_vs_baseline": (
                self.absolute_error_advantage_vs_baseline
            ),
            "performance_vector_dimensions": [
                "accuracy",
                "calibration",
                "decision_relevance",
                "information_gain",
                "difficulty",
            ],
            "composite_forecast_score_enabled": False,
            "composite_forecast_score": None,
            "registration_mutated": False,
            "outcome_mutated": False,
            "order_api_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class ForecastDependencySummary:
    raw_forecast_count: int
    independent_dependency_cluster_count: int
    cluster_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if self.raw_forecast_count <= 0:
            raise ValueError("raw_forecast_count must be positive")
        if self.independent_dependency_cluster_count <= 0:
            raise ValueError("independent_dependency_cluster_count must be positive")
        if self.independent_dependency_cluster_count > self.raw_forecast_count:
            raise ValueError("dependency-cluster count cannot exceed raw forecast count")
        if len(self.cluster_counts) != self.independent_dependency_cluster_count:
            raise ValueError("cluster_counts must represent each dependency cluster exactly once")

    def payload(self) -> dict[str, object]:
        return {
            "raw_forecast_count": self.raw_forecast_count,
            "independent_dependency_cluster_count": (
                self.independent_dependency_cluster_count
            ),
            "cluster_counts": [
                {"dependency_cluster_id": cluster, "forecast_count": count}
                for cluster, count in self.cluster_counts
            ],
            "statistical_effective_sample_size_claimed": False,
        }


def build_forecast_registration(
    *,
    guardrails: DecisionSystemV21Guardrails | None = None,
    **values: object,
) -> ForecastRegistrationSnapshot:
    """Build a registration bound to the active v2.1 guardrail evidence."""

    active = guardrails or load_decision_system_v21_guardrails()
    if not active.forecast_preregistration_required_for_decision_relevant_forecast:
        raise ValueError("active guardrails do not require forecast preregistration")
    if not active.forecast_registration_and_outcome_snapshots_separate:
        raise ValueError("active guardrails do not require separate forecast outcomes")
    if not active.forecast_dependency_cluster_required:
        raise ValueError("active guardrails do not require dependency clusters")
    values_with_guardrail = dict(values)
    supplied_guardrail = values_with_guardrail.pop("guardrail_evidence_id", None)
    if supplied_guardrail is not None and supplied_guardrail != active.evidence_id:
        raise ValueError("supplied guardrail evidence does not match active v2.1 policy")
    return ForecastRegistrationSnapshot(
        **values_with_guardrail,  # type: ignore[arg-type]
        guardrail_evidence_id=active.evidence_id,
    )


def build_forecast_outcome(
    registration: ForecastRegistrationSnapshot,
    *,
    captured_at: datetime,
    outcome_observed_at: datetime,
    actual_value: float,
    source_evidence_ids: tuple[str, ...],
) -> ForecastOutcomeSnapshot:
    """Build a target-level actual without mutating the registration snapshot."""

    return ForecastOutcomeSnapshot(
        captured_at=captured_at,
        outcome_observed_at=outcome_observed_at,
        security_id=registration.security_id,
        target_variable=registration.target_variable,
        target_date=registration.target_date,
        actual_value=actual_value,
        unit=registration.unit,
        source_evidence_ids=source_evidence_ids,
    )


def build_forecast_evaluation(
    registration: ForecastRegistrationSnapshot,
    outcome: ForecastOutcomeSnapshot,
    *,
    evaluated_at: datetime,
    baseline_evaluation: ForecastEvaluationSnapshot | None = None,
) -> ForecastEvaluationSnapshot:
    """Evaluate one numeric point forecast using only its preregistered rule."""

    if outcome.target_key != registration.target_key:
        raise ValueError("outcome target identity differs from forecast registration")
    _require_aware(evaluated_at, "evaluated_at")
    if evaluated_at < outcome.captured_at:
        raise ValueError("forecast evaluation cannot precede outcome capture")

    signed = float(registration.forecast_value) - float(outcome.actual_value)
    absolute = abs(signed)
    squared = signed * signed
    percentage = (
        absolute / abs(float(outcome.actual_value))
        if float(outcome.actual_value) != 0.0
        else None
    )
    direction_correct = _direction_correct(registration, float(outcome.actual_value))
    inside_range = _inside_range(registration, float(outcome.actual_value))
    accuracy = ForecastAccuracyDiagnostics(
        signed_error=signed,
        absolute_error=absolute,
        squared_error=squared,
        absolute_percentage_error=percentage,
        direction_correct=direction_correct,
        inside_predeclared_range=inside_range,
    )
    primary_value = _primary_error_value(
        registration.primary_error_metric,
        accuracy,
    )

    baseline_refs: tuple[str, ...] = ()
    advantage: float | None = None
    information_gain = DiagnosticAvailability.NOT_EVALUATED_WITHOUT_BASELINE
    if baseline_evaluation is not None:
        if baseline_evaluation.outcome_snapshot_id != outcome.snapshot_id:
            raise ValueError("baseline evaluation must use the same target outcome snapshot")
        if baseline_evaluation.registration_snapshot_id not in registration.baseline_refs:
            raise ValueError("baseline evaluation is not declared in registration.baseline_refs")
        baseline_refs = (baseline_evaluation.snapshot_id,)
        advantage = baseline_evaluation.accuracy.absolute_error - absolute
        information_gain = DiagnosticAvailability.OBSERVED

    return ForecastEvaluationSnapshot(
        registration_snapshot_id=registration.snapshot_id,
        outcome_snapshot_id=outcome.snapshot_id,
        evaluated_at=evaluated_at,
        forecast_value=float(registration.forecast_value),
        actual_value=float(outcome.actual_value),
        unit=registration.unit,
        primary_error_metric=registration.primary_error_metric,
        primary_error_value=primary_value,
        accuracy=accuracy,
        calibration=DiagnosticAvailability.NOT_ESTIMABLE_SINGLE_FORECAST,
        decision_relevance=registration.decision_relevance,
        information_gain=information_gain,
        difficulty=registration.difficulty,
        baseline_evaluation_refs=baseline_refs,
        absolute_error_advantage_vs_baseline=advantage,
    )


def summarize_forecast_dependencies(
    registrations: tuple[ForecastRegistrationSnapshot, ...],
) -> ForecastDependencySummary:
    """Report raw records and independent driver clusters without inventing statistical ESS."""

    if not registrations:
        raise ValueError("dependency summary requires at least one forecast registration")
    counts: dict[str, int] = {}
    for registration in registrations:
        cluster = registration.dependency_cluster_id
        counts[cluster] = counts.get(cluster, 0) + 1
    ordered = tuple(sorted(counts.items()))
    return ForecastDependencySummary(
        raw_forecast_count=len(registrations),
        independent_dependency_cluster_count=len(ordered),
        cluster_counts=ordered,
    )


def persist_forecast_registration(
    snapshot: ForecastRegistrationSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        snapshot_id=snapshot.snapshot_id,
        captured_at=snapshot.ledger_recorded_at,
        payload=snapshot.payload_without_id(),
        output_root=output_root,
        object_type="registration",
        manifest_extra={
            "forecast_id": snapshot.forecast_id,
            "registration_mode": snapshot.registration_mode.value,
            "dependency_cluster_id": snapshot.dependency_cluster_id,
            "guardrail_evidence_id": snapshot.guardrail_evidence_id,
            "outcome_observed": False,
            "evaluation_run": False,
        },
    )


def persist_forecast_outcome(
    snapshot: ForecastOutcomeSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        snapshot_id=snapshot.snapshot_id,
        captured_at=snapshot.captured_at,
        payload=snapshot.payload_without_id(),
        output_root=output_root,
        object_type="outcome",
        manifest_extra={
            "security_id": snapshot.security_id,
            "target_variable": snapshot.target_variable,
            "target_date": snapshot.target_date.isoformat(),
            "forecast_registration_specific": False,
        },
    )


def persist_forecast_evaluation(
    snapshot: ForecastEvaluationSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        snapshot_id=snapshot.snapshot_id,
        captured_at=snapshot.evaluated_at,
        payload=snapshot.payload_without_id(),
        output_root=output_root,
        object_type="evaluation",
        manifest_extra={
            "registration_snapshot_id": snapshot.registration_snapshot_id,
            "outcome_snapshot_id": snapshot.outcome_snapshot_id,
            "composite_forecast_score_enabled": False,
        },
    )


def _persist_snapshot(
    *,
    snapshot_id: str,
    captured_at: datetime,
    payload: dict[str, object],
    output_root: str | Path,
    object_type: str,
    manifest_extra: dict[str, object],
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
            filename = f"forecast_{object_type}.json"
            manifest = {
                "schema_version": FORECAST_LEDGER_SCHEMA_VERSION,
                "object_type": object_type,
                "snapshot_id": snapshot_id,
                "captured_at": captured_at.isoformat(),
                "immutable": True,
                "order_api_enabled": False,
                "files": [filename],
                **manifest_extra,
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
                "schema_version": FORECAST_LEDGER_SCHEMA_VERSION,
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


def _validate_range(registration: ForecastRegistrationSnapshot) -> None:
    lower = registration.range_lower
    upper = registration.range_upper
    if (lower is None) != (upper is None):
        raise ValueError("forecast range requires both lower and upper values")
    if lower is None or upper is None:
        return
    _require_finite(lower, "range_lower")
    _require_finite(upper, "range_upper")
    if upper < lower:
        raise ValueError("range_upper cannot be below range_lower")
    if not lower <= registration.forecast_value <= upper:
        raise ValueError("point forecast must lie inside its predeclared range")


def _direction_correct(
    registration: ForecastRegistrationSnapshot,
    actual_value: float,
) -> bool | None:
    if registration.direction is None or registration.direction_reference_value is None:
        return None
    delta = actual_value - registration.direction_reference_value
    tolerance = registration.direction_flat_tolerance
    actual_direction = (
        ForecastDirection.UP
        if delta > tolerance
        else ForecastDirection.DOWN
        if delta < -tolerance
        else ForecastDirection.FLAT
    )
    return actual_direction is registration.direction


def _inside_range(
    registration: ForecastRegistrationSnapshot,
    actual_value: float,
) -> bool | None:
    if registration.range_lower is None or registration.range_upper is None:
        return None
    return registration.range_lower <= actual_value <= registration.range_upper


def _primary_error_value(
    metric: PrimaryErrorMetric,
    accuracy: ForecastAccuracyDiagnostics,
) -> float:
    if metric is PrimaryErrorMetric.ABSOLUTE_ERROR:
        return accuracy.absolute_error
    if metric is PrimaryErrorMetric.SQUARED_ERROR:
        return accuracy.squared_error
    if accuracy.absolute_percentage_error is None:
        raise ValueError("absolute percentage error is undefined when actual value is zero")
    return accuracy.absolute_percentage_error


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_finite(value: float, field: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite")


def _validate_text_refs(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha_refs(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _validate_sha(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


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
    "DiagnosticAvailability",
    "ForecastAccuracyDiagnostics",
    "ForecastDependencySummary",
    "ForecastDirection",
    "ForecastEvaluationSnapshot",
    "ForecastOutcomeSnapshot",
    "ForecastRegistrationMode",
    "ForecastRegistrationSnapshot",
    "ForecasterKind",
    "OrdinalAssessment",
    "PrimaryErrorMetric",
    "build_forecast_evaluation",
    "build_forecast_outcome",
    "build_forecast_registration",
    "persist_forecast_evaluation",
    "persist_forecast_outcome",
    "persist_forecast_registration",
    "summarize_forecast_dependencies",
]
