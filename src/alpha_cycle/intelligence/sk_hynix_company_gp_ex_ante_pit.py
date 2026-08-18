"""Point-in-time feature bundle validation for SK hynix ex-ante GP research.

This module never loads company gross-profit targets. It only determines whether explicit
feature observations were provably available by the frozen forecast origin.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    ExAnteFeatureFrontier,
    ExAnteFeatureSpec,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    FrozenCompanyGPExAnteProtocol,
)


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _valid_sha(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _aware_datetime(value: str, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return result


def _object(path: Path, label: str) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return {str(key): value for key, value in cast(dict[object, object], raw).items()}


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


@dataclass(frozen=True)
class PointInTimeFeatureObservation:
    period_id: str
    feature_id: str
    value: float
    provenance_class: str
    source_available_at: datetime
    source_bytes_sha256: str
    source_evidence_id: str
    source_version_identity: str
    direct_source_fact: bool
    deterministic_transform: bool
    target_metric_in_payload: bool = False
    captured_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.period_id or not self.feature_id:
            raise ValueError("PIT feature period_id and feature_id are required")
        if not math.isfinite(self.value):
            raise ValueError("PIT feature value must be finite")
        if self.source_available_at.tzinfo is None or self.source_available_at.utcoffset() is None:
            raise ValueError("PIT feature source_available_at must be timezone-aware")
        if self.captured_at is not None and (
            self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None
        ):
            raise ValueError("PIT feature captured_at must be timezone-aware")
        if not _valid_sha(self.source_bytes_sha256) or not _valid_sha(
            self.source_evidence_id
        ):
            raise ValueError("PIT feature source hashes must be SHA-256")
        if not self.source_version_identity.strip():
            raise ValueError("PIT feature source_version_identity is required")
        if self.direct_source_fact == self.deterministic_transform:
            raise ValueError(
                "PIT feature must be exactly one of direct source fact or deterministic transform"
            )
        if self.provenance_class == "prospective_snapshot" and self.captured_at is None:
            raise ValueError("Prospective PIT snapshot requires captured_at")


@dataclass(frozen=True)
class PointInTimeFeatureBundle:
    evidence_id: str
    created_at: datetime
    observations: tuple[PointInTimeFeatureObservation, ...]
    target_values_included: bool = False

    def __post_init__(self) -> None:
        if not _valid_sha(self.evidence_id):
            raise ValueError("PIT feature bundle evidence id must be SHA-256")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("PIT feature bundle created_at must be timezone-aware")
        if self.target_values_included:
            raise ValueError("PIT feature bundle cannot include target values")
        keys = [(item.period_id, item.feature_id) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("PIT feature bundle contains duplicate period/feature keys")


@dataclass(frozen=True)
class PITObservationAudit:
    period_id: str
    feature_id: str
    forecast_origin: datetime
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PITPeriodCoverage:
    period_id: str
    forecast_origin: datetime
    eligible_feature_count: int
    rejected_feature_count: int
    eligible_feature_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExAntePITAuditResult:
    protocol_evidence_id: str
    frontier_evidence_id: str
    bundle_evidence_id: str
    observation_count: int
    eligible_observation_count: int
    rejected_observation_count: int
    all_observations_point_in_time_eligible: bool
    observation_audits: tuple[PITObservationAudit, ...]
    development_period_coverage: tuple[PITPeriodCoverage, ...]
    periods_with_any_eligible_feature: int
    final_feature_set_frozen: bool = False
    target_join_allowed: bool = False
    estimator_fit_allowed: bool = False
    first_pit_backtest_run: bool = False
    q3_target_read: bool = False
    q3_source_outcome_loaded: bool = False
    numeric_forward_forecast_enabled: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.protocol_evidence_id,
            self.frontier_evidence_id,
            self.bundle_evidence_id,
        ):
            if not _valid_sha(value):
                raise ValueError("PIT audit evidence ids must be SHA-256")
        if self.observation_count != (
            self.eligible_observation_count + self.rejected_observation_count
        ):
            raise ValueError("PIT audit observation counts do not reconcile")
        if self.all_observations_point_in_time_eligible != (
            self.rejected_observation_count == 0
        ):
            raise ValueError("PIT audit eligibility flag is inconsistent")
        if any(
            (
                self.final_feature_set_frozen,
                self.target_join_allowed,
                self.estimator_fit_allowed,
                self.first_pit_backtest_run,
                self.q3_target_read,
                self.q3_source_outcome_loaded,
                self.numeric_forward_forecast_enabled,
            )
        ):
            raise ValueError("PIT audit exceeded ex-ante foundation trust boundary")


def _observation_payload(observation: PointInTimeFeatureObservation) -> dict[str, object]:
    payload = asdict(observation)
    payload["source_available_at"] = observation.source_available_at.isoformat()
    payload["captured_at"] = (
        observation.captured_at.isoformat() if observation.captured_at is not None else None
    )
    return payload


def load_point_in_time_feature_bundle(path: str | Path) -> PointInTimeFeatureBundle:
    root = _object(Path(path), "PIT feature bundle")
    if root.get("schema_version") != 1:
        raise ValueError("PIT feature bundle schema is invalid")
    if root.get("status") != "skhynix_ex_ante_pit_feature_bundle_locked":
        raise ValueError("PIT feature bundle status is invalid")
    raw_bundle = _mapping(root.get("bundle"), "PIT feature bundle body")
    raw_observations = raw_bundle.get("observations")
    if not isinstance(raw_observations, list):
        raise ValueError("PIT feature bundle observations must be an array")
    observations: list[PointInTimeFeatureObservation] = []
    for raw_item in raw_observations:
        item = _mapping(raw_item, "PIT feature observation")
        captured_raw = item.get("captured_at")
        captured_at = (
            None
            if captured_raw in {None, ""}
            else _aware_datetime(str(captured_raw), "captured_at")
        )
        observations.append(
            PointInTimeFeatureObservation(
                period_id=str(item.get("period_id", "")),
                feature_id=str(item.get("feature_id", "")),
                value=float(str(item.get("value", "nan"))),
                provenance_class=str(item.get("provenance_class", "")),
                source_available_at=_aware_datetime(
                    str(item.get("source_available_at", "")),
                    "source_available_at",
                ),
                source_bytes_sha256=str(item.get("source_bytes_sha256", "")),
                source_evidence_id=str(item.get("source_evidence_id", "")),
                source_version_identity=str(item.get("source_version_identity", "")),
                direct_source_fact=item.get("direct_source_fact") is True,
                deterministic_transform=item.get("deterministic_transform") is True,
                target_metric_in_payload=item.get("target_metric_in_payload") is True,
                captured_at=captured_at,
            )
        )
    created_at = _aware_datetime(str(raw_bundle.get("created_at", "")), "created_at")
    target_values_included = raw_bundle.get("target_values_included") is True
    stable = {
        "created_at": created_at.isoformat(),
        "observations": [_observation_payload(item) for item in observations],
        "target_values_included": target_values_included,
    }
    expected = _sha(stable)
    evidence_id = str(raw_bundle.get("evidence_id", ""))
    if expected != evidence_id:
        raise ValueError("PIT feature bundle evidence hash mismatch")
    return PointInTimeFeatureBundle(
        evidence_id=evidence_id,
        created_at=created_at,
        observations=tuple(observations),
        target_values_included=target_values_included,
    )


def _audit_observation(
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    feature: ExAnteFeatureSpec | None,
    observation: PointInTimeFeatureObservation,
) -> PITObservationAudit:
    origin = protocol.origin_for(observation.period_id)
    reasons: list[str] = []
    if feature is None:
        reasons.append("feature_not_in_frozen_frontier")
    else:
        if observation.provenance_class not in feature.acceptable_provenance_classes:
            reasons.append("provenance_class_not_allowed_for_feature")
        if observation.feature_id in frontier.forbidden_features:
            reasons.append("feature_explicitly_forbidden")
    if observation.source_available_at > origin:
        reasons.append("source_available_after_forecast_origin")
    if observation.target_metric_in_payload:
        reasons.append("target_metric_present_in_feature_payload")
    if observation.provenance_class == "current_retrieval_only":
        reasons.append("current_retrieval_only_is_not_historical_pit_proof")
    if observation.provenance_class == "prospective_snapshot":
        assert observation.captured_at is not None
        if observation.captured_at > origin:
            reasons.append("prospective_snapshot_captured_after_forecast_origin")
        if observation.source_available_at > observation.captured_at:
            reasons.append("prospective_snapshot_precedes_source_availability")
    return PITObservationAudit(
        period_id=observation.period_id,
        feature_id=observation.feature_id,
        forecast_origin=origin,
        eligible=not reasons,
        reasons=tuple(reasons),
    )


def audit_point_in_time_feature_bundle(
    protocol: FrozenCompanyGPExAnteProtocol,
    frontier: ExAnteFeatureFrontier,
    bundle: PointInTimeFeatureBundle,
) -> ExAntePITAuditResult:
    """Audit feature timing without loading or joining any gross-profit target."""

    known_periods = set(protocol.development_periods)
    known_periods.update(protocol.contaminated_report_only_periods)
    known_periods.update({"2026Q3", "2026Q4"})
    feature_map = frontier.by_id()
    audits: list[PITObservationAudit] = []
    for observation in bundle.observations:
        if observation.period_id not in known_periods:
            raise ValueError(f"PIT feature uses unsupported period: {observation.period_id}")
        audits.append(
            _audit_observation(
                protocol,
                frontier,
                feature_map.get(observation.feature_id),
                observation,
            )
        )
    period_coverage: list[PITPeriodCoverage] = []
    for period_id in protocol.development_periods:
        period_audits = [item for item in audits if item.period_id == period_id]
        eligible = tuple(
            sorted(item.feature_id for item in period_audits if item.eligible)
        )
        rejected = sum(not item.eligible for item in period_audits)
        period_coverage.append(
            PITPeriodCoverage(
                period_id=period_id,
                forecast_origin=protocol.origin_for(period_id),
                eligible_feature_count=len(eligible),
                rejected_feature_count=rejected,
                eligible_feature_ids=eligible,
            )
        )
    eligible_count = sum(item.eligible for item in audits)
    rejected_count = len(audits) - eligible_count
    periods_with_features = sum(
        item.eligible_feature_count > 0 for item in period_coverage
    )
    return ExAntePITAuditResult(
        protocol_evidence_id=protocol.evidence_id,
        frontier_evidence_id=frontier.evidence_id,
        bundle_evidence_id=bundle.evidence_id,
        observation_count=len(audits),
        eligible_observation_count=eligible_count,
        rejected_observation_count=rejected_count,
        all_observations_point_in_time_eligible=rejected_count == 0,
        observation_audits=tuple(audits),
        development_period_coverage=tuple(period_coverage),
        periods_with_any_eligible_feature=periods_with_features,
    )


__all__ = [
    "ExAntePITAuditResult",
    "PITObservationAudit",
    "PITPeriodCoverage",
    "PointInTimeFeatureBundle",
    "PointInTimeFeatureObservation",
    "audit_point_in_time_feature_bundle",
    "load_point_in_time_feature_bundle",
]
