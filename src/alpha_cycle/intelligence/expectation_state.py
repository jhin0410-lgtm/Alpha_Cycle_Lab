"""Certified point-in-time expectation states for decision-system v2.

This module is deliberately provider agnostic.  A numeric forward value can enter an
ExpectationStateSnapshot only after the existing expectation-semantics contract says the
level is usable.  A value may be labelled market consensus only when that stronger claim is
independently certified.  Revision arithmetic is enabled only when two comparable snapshots
exist and the revision-specific semantic gates also pass.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.expectation_gap_contract import (
    ExpectationReadiness,
    ExpectationSemantics,
    evaluate_expectation_readiness,
)

KOREA_TZ = ZoneInfo("Asia/Seoul")
EXPECTATION_STATE_SCHEMA_VERSION = 1


class ExpectationKind(StrEnum):
    """Economic identity of an externally observed forward expectation."""

    MARKET_CONSENSUS = "market_consensus"
    SINGLE_BROKER = "single_broker"
    MANAGEMENT_GUIDANCE = "management_guidance"
    PROVIDER_DEFINED_ESTIMATE = "provider_defined_estimate"


class ExpectationMetric(StrEnum):
    REVENUE = "revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_INCOME = "operating_income"
    NET_INCOME = "net_income"
    EPS = "eps"
    EBITDA = "ebitda"
    FREE_CASH_FLOW = "free_cash_flow"


@dataclass(frozen=True)
class CertifiedExpectationObservation:
    """One numeric forward expectation whose level semantics pass the trust contract."""

    security_id: str
    metric: ExpectationMetric
    target_period: str
    target_period_end: date
    expectation_kind: ExpectationKind
    value: float
    unit: str
    observed_at: datetime
    source_evidence_id: str
    semantics: ExpectationSemantics
    market_consensus_certified: bool = False
    producer_identity: str | None = None
    aggregation_method: str | None = None
    sample_count: int | None = None
    dispersion: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.security_id, "security_id")
        _require_text(self.target_period, "target_period")
        _require_text(self.unit, "unit")
        _validate_sha(self.source_evidence_id, "source_evidence_id")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
            raise ValueError("expectation value must be numeric")
        if not math.isfinite(float(self.value)):
            raise ValueError("expectation value must be finite")
        if self.sample_count is not None and self.sample_count <= 0:
            raise ValueError("sample_count must be positive when supplied")
        if self.dispersion is not None:
            if not math.isfinite(self.dispersion) or self.dispersion < 0:
                raise ValueError("dispersion must be finite and non-negative")
        if self.producer_identity is not None:
            _require_text(self.producer_identity, "producer_identity")
        if self.aggregation_method is not None:
            _require_text(self.aggregation_method, "aggregation_method")
        if self.semantics.provider_id.strip() == "":
            raise ValueError("expectation semantics require provider_id")
        readiness = evaluate_expectation_readiness(self.semantics)
        if not readiness.numeric_level_enabled:
            raise ValueError(
                "numeric expectation level is blocked: " + ",".join(readiness.level_blockers)
            )
        if self.expectation_kind is ExpectationKind.MARKET_CONSENSUS:
            if not self.market_consensus_certified:
                raise ValueError("market_consensus label requires independent certification")
            if self.aggregation_method is None:
                raise ValueError("market_consensus requires an aggregation_method")
        elif self.market_consensus_certified:
            raise ValueError("market_consensus_certified cannot be true for a non-consensus kind")
        if (
            self.expectation_kind is ExpectationKind.SINGLE_BROKER
            and self.producer_identity is None
        ):
            raise ValueError("single_broker expectation requires producer_identity")

    @property
    def provider_id(self) -> str:
        return self.semantics.provider_id

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.provider_id,
            self.security_id,
            self.metric.value,
            self.target_period,
            self.expectation_kind.value,
        )

    @property
    def level_readiness(self) -> ExpectationReadiness:
        return evaluate_expectation_readiness(self.semantics)

    def payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "security_id": self.security_id,
            "metric": self.metric.value,
            "target_period": self.target_period,
            "target_period_end": self.target_period_end.isoformat(),
            "expectation_kind": self.expectation_kind.value,
            "value": float(self.value),
            "unit": self.unit,
            "observed_at": self.observed_at.isoformat(),
            "source_evidence_id": self.source_evidence_id,
            "market_consensus_certified": self.market_consensus_certified,
            "producer_identity": self.producer_identity,
            "aggregation_method": self.aggregation_method,
            "sample_count": self.sample_count,
            "dispersion": self.dispersion,
            "semantics": _semantics_payload(self.semantics),
        }


@dataclass(frozen=True)
class ExpectationStateSnapshot:
    """Content-addressed cross-provider expectation state at one decision timestamp."""

    captured_at: datetime
    evaluation_date: date
    observations: tuple[CertifiedExpectationObservation, ...]
    source_snapshot_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if not self.observations:
            raise ValueError("ExpectationStateSnapshot requires at least one observation")
        for source_id in self.source_snapshot_ids:
            _validate_sha(source_id, "source_snapshot_id")
        if len(set(self.source_snapshot_ids)) != len(self.source_snapshot_ids):
            raise ValueError("source_snapshot_ids cannot contain duplicates")
        keys = [observation.key for observation in self.observations]
        if len(set(keys)) != len(keys):
            raise ValueError("ExpectationStateSnapshot contains duplicate observation keys")
        for observation in self.observations:
            if observation.observed_at > self.captured_at:
                raise ValueError("expectation observation cannot occur after snapshot capture")
            if observation.observed_at.astimezone(KOREA_TZ).date() > self.evaluation_date:
                raise ValueError("expectation observation is after the evaluation date")
            if observation.target_period_end < self.evaluation_date:
                raise ValueError(
                    "certified forward expectation target must not already be historical"
                )
        _validate_text_tuple(self.warnings, "warnings")

    def payload_without_id(self) -> dict[str, object]:
        ordered = sorted(self.observations, key=lambda item: item.key)
        return {
            "schema_version": EXPECTATION_STATE_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "observations": [item.payload() for item in ordered],
            "source_snapshot_ids": sorted(self.source_snapshot_ids),
            "warnings": list(self.warnings),
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class ExpectationRevisionObservation:
    """Arithmetic change between two separately frozen comparable expectation states."""

    provider_id: str
    security_id: str
    metric: ExpectationMetric
    target_period: str
    expectation_kind: ExpectationKind
    unit: str
    prior_snapshot_id: str
    current_snapshot_id: str
    prior_observed_at: datetime
    current_observed_at: datetime
    prior_value: float
    current_value: float
    absolute_change: float
    relative_change: float | None
    revision_readiness: ExpectationReadiness

    def __post_init__(self) -> None:
        _validate_sha(self.prior_snapshot_id, "prior_snapshot_id")
        _validate_sha(self.current_snapshot_id, "current_snapshot_id")
        if self.current_observed_at <= self.prior_observed_at:
            raise ValueError("current expectation observation must be later than prior observation")
        if not self.revision_readiness.numeric_revision_enabled:
            raise ValueError("revision observation requires certified numeric revision readiness")

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.provider_id,
            self.security_id,
            self.metric.value,
            self.target_period,
            self.expectation_kind.value,
        )

    def payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "security_id": self.security_id,
            "metric": self.metric.value,
            "target_period": self.target_period,
            "expectation_kind": self.expectation_kind.value,
            "unit": self.unit,
            "prior_snapshot_id": self.prior_snapshot_id,
            "current_snapshot_id": self.current_snapshot_id,
            "prior_observed_at": self.prior_observed_at.isoformat(),
            "current_observed_at": self.current_observed_at.isoformat(),
            "prior_value": self.prior_value,
            "current_value": self.current_value,
            "absolute_change": self.absolute_change,
            "relative_change": self.relative_change,
            "revision_blockers": list(self.revision_readiness.revision_blockers),
            "numeric_revision_enabled": self.revision_readiness.numeric_revision_enabled,
        }


def build_expectation_revisions(
    prior: ExpectationStateSnapshot,
    current: ExpectationStateSnapshot,
) -> tuple[ExpectationRevisionObservation, ...]:
    """Build only revisions whose static and cross-snapshot semantics are certified."""

    if current.captured_at <= prior.captured_at:
        raise ValueError("current expectation state must be captured after prior state")
    prior_lookup = {item.key: item for item in prior.observations}
    revisions: list[ExpectationRevisionObservation] = []
    for current_item in current.observations:
        prior_item = prior_lookup.get(current_item.key)
        if prior_item is None:
            continue
        if current_item.unit != prior_item.unit:
            raise ValueError(f"expectation unit drift for key: {current_item.key}")
        if current_item.target_period_end != prior_item.target_period_end:
            raise ValueError(f"expectation target-period-end drift for key: {current_item.key}")
        _validate_revision_semantics_compatibility(prior_item, current_item)
        semantics = replace(
            current_item.semantics,
            comparable_prior_snapshot_available=True,
            numeric_evidence_available=True,
        )
        readiness = evaluate_expectation_readiness(semantics)
        if not readiness.numeric_revision_enabled:
            continue
        absolute = float(current_item.value) - float(prior_item.value)
        relative = (
            absolute / abs(float(prior_item.value)) if float(prior_item.value) != 0.0 else None
        )
        revisions.append(
            ExpectationRevisionObservation(
                provider_id=current_item.provider_id,
                security_id=current_item.security_id,
                metric=current_item.metric,
                target_period=current_item.target_period,
                expectation_kind=current_item.expectation_kind,
                unit=current_item.unit,
                prior_snapshot_id=prior.snapshot_id,
                current_snapshot_id=current.snapshot_id,
                prior_observed_at=prior_item.observed_at,
                current_observed_at=current_item.observed_at,
                prior_value=float(prior_item.value),
                current_value=float(current_item.value),
                absolute_change=absolute,
                relative_change=relative,
                revision_readiness=readiness,
            )
        )
    return tuple(sorted(revisions, key=lambda item: item.key))


def persist_expectation_state(
    snapshot: ExpectationStateSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    """Persist a content-addressed immutable expectation-state directory."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    pointer = root / "latest_expectation_state.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot.snapshot_id:
            raise ValueError("existing expectation-state directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            payload = snapshot.payload_without_id()
            manifest = {
                "schema_version": EXPECTATION_STATE_SCHEMA_VERSION,
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "evaluation_date": snapshot.evaluation_date.isoformat(),
                "observation_count": len(snapshot.observations),
                "providers": sorted({item.provider_id for item in snapshot.observations}),
                "consensus_observation_count": sum(
                    item.expectation_kind is ExpectationKind.MARKET_CONSENSUS
                    for item in snapshot.observations
                ),
                "source_snapshot_ids": list(snapshot.source_snapshot_ids),
                "warnings": list(snapshot.warnings),
                "order_api_enabled": False,
                "files": ["expectations.json"],
            }
            (temporary / "expectations.json").write_text(
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
    pointer_payload = {
        "schema_version": EXPECTATION_STATE_SCHEMA_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_path": str(directory),
    }
    pointer.write_text(
        json.dumps(pointer_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return pointer


def _validate_revision_semantics_compatibility(
    prior: CertifiedExpectationObservation,
    current: CertifiedExpectationObservation,
) -> None:
    fields = (
        "provider_id",
        "source_scope",
        "provider_semantics_certified",
        "target_period_semantics_certified",
        "metric_semantics_certified",
        "aggregation_semantics_certified",
        "provider_vintage_certified",
        "comparable_snapshot_scope_certified",
        "revision_calculation_certified",
    )
    for field in fields:
        if getattr(prior.semantics, field) != getattr(current.semantics, field):
            raise ValueError(f"expectation semantic drift prevents revision: {field}")
    if prior.market_consensus_certified != current.market_consensus_certified:
        raise ValueError("market-consensus certification drift prevents revision")
    if prior.aggregation_method != current.aggregation_method:
        raise ValueError("aggregation-method drift prevents revision")
    if prior.producer_identity != current.producer_identity:
        raise ValueError("producer-identity drift prevents revision")


def _semantics_payload(value: ExpectationSemantics) -> dict[str, object]:
    return {
        "provider_id": value.provider_id,
        "provider_semantics_certified": value.provider_semantics_certified,
        "target_period_semantics_certified": value.target_period_semantics_certified,
        "metric_semantics_certified": value.metric_semantics_certified,
        "aggregation_semantics_certified": value.aggregation_semantics_certified,
        "observation_timestamp_certified": value.observation_timestamp_certified,
        "provider_vintage_certified": value.provider_vintage_certified,
        "comparable_prior_snapshot_available": value.comparable_prior_snapshot_available,
        "comparable_snapshot_scope_certified": value.comparable_snapshot_scope_certified,
        "revision_calculation_certified": value.revision_calculation_certified,
        "numeric_evidence_available": value.numeric_evidence_available,
        "source_scope": value.source_scope,
    }


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): value for key, value in cast(dict[object, object], payload).items()}


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


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
    "CertifiedExpectationObservation",
    "ExpectationKind",
    "ExpectationMetric",
    "ExpectationRevisionObservation",
    "ExpectationStateSnapshot",
    "build_expectation_revisions",
    "persist_expectation_state",
]
