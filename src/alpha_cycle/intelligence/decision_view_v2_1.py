"""Preregistered internal Decision View and numeric expectation-gap contracts for v2.1.

A Decision View may not be selected after inspecting a forecast tournament. The selection rule
pins a forecaster identity before forecast values are registered. The resulting internal view
is then compared separately with certified market consensus and conditional price-implied
requirements without averaging providers or valuation reference points.
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
from alpha_cycle.intelligence.expectation_state import (
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
)
from alpha_cycle.intelligence.forecast_ledger import (
    ForecasterKind,
    ForecastRegistrationSnapshot,
)
from alpha_cycle.intelligence.price_implied_requirement import (
    PriceImpliedRequirementSnapshot,
    PriceImpliedRequirementStatus,
)
from alpha_cycle.intelligence.underwriter_v2_1 import assess_forecast_tournament

DECISION_VIEW_SCHEMA_VERSION = 1


class DecisionViewSelectionMethod(StrEnum):
    PINNED_FORECASTER_IDENTITY = "pinned_forecaster_identity"


@dataclass(frozen=True)
class DecisionViewSelectionRuleSnapshot:
    """Selection rule registered before any candidate forecast value is registered."""

    rule_id: str
    registered_at: datetime
    security_id: str
    target_variable: str
    target_date: date
    unit: str
    selection_method: DecisionViewSelectionMethod
    selected_forecaster_kind: ForecasterKind
    selected_model_family: str
    rationale: str
    source_evidence_ids: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        for value, field in (
            (self.rule_id, "rule_id"),
            (self.security_id, "security_id"),
            (self.target_variable, "target_variable"),
            (self.unit, "unit"),
            (self.selected_model_family, "selected_model_family"),
            (self.rationale, "rationale"),
        ):
            _require_text(value, field)
        _require_aware(self.registered_at, "registered_at")
        if self.target_date <= self.registered_at.date():
            raise ValueError("decision-view target_date must be after rule registration")
        if self.selection_method is not DecisionViewSelectionMethod.PINNED_FORECASTER_IDENTITY:
            raise ValueError("unsupported Decision View selection method")
        _validate_sha_tuple(self.source_evidence_ids, "source_evidence_ids")
        if not self.source_evidence_ids:
            raise ValueError("Decision View selection rule requires source_evidence_ids")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": DECISION_VIEW_SCHEMA_VERSION,
            "rule_id": self.rule_id,
            "registered_at": self.registered_at.isoformat(),
            "security_id": self.security_id,
            "target_variable": self.target_variable,
            "target_date": self.target_date.isoformat(),
            "unit": self.unit,
            "selection_method": self.selection_method.value,
            "selected_forecaster_kind": self.selected_forecaster_kind.value,
            "selected_model_family": self.selected_model_family,
            "rationale": self.rationale,
            "source_evidence_ids": list(self.source_evidence_ids),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "forecast_value_inspection_allowed_before_rule_registration": False,
            "most_bullish_forecast_selection_enabled": False,
            "automatic_ensemble_weighting_enabled": False,
        }


@dataclass(frozen=True)
class DecisionViewSnapshot:
    """One internal forward view selected by the preregistered identity rule."""

    captured_at: datetime
    evaluation_date: date
    selection_rule_snapshot_id: str
    security_id: str
    target_variable: str
    target_date: date
    unit: str
    selected_forecast_snapshot_id: str
    selected_forecast_id: str
    selected_forecaster_kind: ForecasterKind
    selected_model_family: str
    selected_forecast_value: float
    forecast_origin: datetime
    information_cutoff: datetime
    tournament_forecast_snapshot_ids: tuple[str, ...]
    tournament_dependency_overlap: bool
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _validate_sha(self.selection_rule_snapshot_id, "selection_rule_snapshot_id")
        _require_text(self.security_id, "security_id")
        _require_text(self.target_variable, "target_variable")
        _require_text(self.unit, "unit")
        _validate_sha(self.selected_forecast_snapshot_id, "selected_forecast_snapshot_id")
        _require_text(self.selected_forecast_id, "selected_forecast_id")
        _require_text(self.selected_model_family, "selected_model_family")
        _require_finite(self.selected_forecast_value, "selected_forecast_value")
        _require_aware(self.forecast_origin, "forecast_origin")
        _require_aware(self.information_cutoff, "information_cutoff")
        _validate_sha_tuple(
            self.tournament_forecast_snapshot_ids,
            "tournament_forecast_snapshot_ids",
        )
        if self.selected_forecast_snapshot_id not in self.tournament_forecast_snapshot_ids:
            raise ValueError("selected forecast must belong to the forecast tournament")
        if self.target_date <= self.evaluation_date:
            raise ValueError("Decision View target must remain forward of evaluation_date")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": DECISION_VIEW_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "selection_rule_snapshot_id": self.selection_rule_snapshot_id,
            "security_id": self.security_id,
            "target_variable": self.target_variable,
            "target_date": self.target_date.isoformat(),
            "unit": self.unit,
            "selected_forecast_snapshot_id": self.selected_forecast_snapshot_id,
            "selected_forecast_id": self.selected_forecast_id,
            "selected_forecaster_kind": self.selected_forecaster_kind.value,
            "selected_model_family": self.selected_model_family,
            "selected_forecast_value": self.selected_forecast_value,
            "forecast_origin": self.forecast_origin.isoformat(),
            "information_cutoff": self.information_cutoff.isoformat(),
            "tournament_forecast_snapshot_ids": list(
                self.tournament_forecast_snapshot_ids
            ),
            "tournament_dependency_overlap": self.tournament_dependency_overlap,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "ex_post_forecast_value_selection_enabled": False,
            "automatic_ensemble_weighting_enabled": False,
            "market_consensus_claimed": False,
            "target_price_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class ConsensusGapObservation:
    provider_id: str
    source_evidence_id: str
    observed_at: datetime
    decision_value: float
    consensus_value: float
    unit: str
    absolute_gap: float
    relative_gap: float | None

    def __post_init__(self) -> None:
        _require_text(self.provider_id, "provider_id")
        _validate_sha(self.source_evidence_id, "source_evidence_id")
        _require_aware(self.observed_at, "observed_at")
        _require_text(self.unit, "unit")
        for value, field in (
            (self.decision_value, "decision_value"),
            (self.consensus_value, "consensus_value"),
            (self.absolute_gap, "absolute_gap"),
        ):
            _require_finite(value, field)
        if self.relative_gap is not None:
            _require_finite(self.relative_gap, "relative_gap")

    def payload(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "source_evidence_id": self.source_evidence_id,
            "observed_at": self.observed_at.isoformat(),
            "decision_value": self.decision_value,
            "consensus_value": self.consensus_value,
            "unit": self.unit,
            "absolute_gap": self.absolute_gap,
            "relative_gap": self.relative_gap,
        }


@dataclass(frozen=True)
class PriceImpliedGapObservation:
    reference_id: str
    reference_kind: str
    reference_multiple: float
    decision_value_krw: float
    implied_value_krw: float
    absolute_gap_krw: float
    relative_gap: float

    def __post_init__(self) -> None:
        _require_text(self.reference_id, "reference_id")
        _require_text(self.reference_kind, "reference_kind")
        for value, field in (
            (self.reference_multiple, "reference_multiple"),
            (self.decision_value_krw, "decision_value_krw"),
            (self.implied_value_krw, "implied_value_krw"),
            (self.absolute_gap_krw, "absolute_gap_krw"),
            (self.relative_gap, "relative_gap"),
        ):
            _require_finite(value, field)
        if self.reference_multiple <= 0 or self.implied_value_krw <= 0:
            raise ValueError("price-implied gap requires positive reference/value")

    def payload(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "reference_kind": self.reference_kind,
            "reference_multiple": self.reference_multiple,
            "decision_value_krw": self.decision_value_krw,
            "implied_value_krw": self.implied_value_krw,
            "absolute_gap_krw": self.absolute_gap_krw,
            "relative_gap": self.relative_gap,
            "market_expectation_claimed": False,
        }


@dataclass(frozen=True)
class DecisionExpectationGapSnapshot:
    """Provider/reference-preserving gap between our frozen view and external price bars."""

    captured_at: datetime
    evaluation_date: date
    decision_view_snapshot_id: str
    expectation_state_snapshot_id: str
    price_implied_requirement_snapshot_id: str | None
    security_id: str
    target_variable: str
    target_date: date
    unit: str
    consensus_gaps: tuple[ConsensusGapObservation, ...]
    price_implied_gaps: tuple[PriceImpliedGapObservation, ...]
    flags: tuple[str, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _validate_sha(self.decision_view_snapshot_id, "decision_view_snapshot_id")
        _validate_sha(self.expectation_state_snapshot_id, "expectation_state_snapshot_id")
        if self.price_implied_requirement_snapshot_id is not None:
            _validate_sha(
                self.price_implied_requirement_snapshot_id,
                "price_implied_requirement_snapshot_id",
            )
        _require_text(self.security_id, "security_id")
        _require_text(self.target_variable, "target_variable")
        _require_text(self.unit, "unit")
        if not self.consensus_gaps:
            raise ValueError("Decision expectation gap requires certified consensus evidence")
        provider_ids = tuple(item.provider_id for item in self.consensus_gaps)
        if len(set(provider_ids)) != len(provider_ids):
            raise ValueError("Decision expectation gap contains duplicate consensus providers")
        reference_ids = tuple(item.reference_id for item in self.price_implied_gaps)
        if len(set(reference_ids)) != len(reference_ids):
            raise ValueError("Decision expectation gap contains duplicate price references")
        _validate_text_tuple(self.flags, "flags")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        consensus = sorted(self.consensus_gaps, key=lambda item: item.provider_id)
        price = sorted(self.price_implied_gaps, key=lambda item: item.reference_id)
        return {
            "schema_version": DECISION_VIEW_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "decision_view_snapshot_id": self.decision_view_snapshot_id,
            "expectation_state_snapshot_id": self.expectation_state_snapshot_id,
            "price_implied_requirement_snapshot_id": (
                self.price_implied_requirement_snapshot_id
            ),
            "security_id": self.security_id,
            "target_variable": self.target_variable,
            "target_date": self.target_date.isoformat(),
            "unit": self.unit,
            "consensus_gaps": [item.payload() for item in consensus],
            "price_implied_gaps": [item.payload() for item in price],
            "flags": list(self.flags),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "consensus_provider_aggregation_enabled": False,
            "price_reference_aggregation_enabled": False,
            "price_implied_market_expectation_claimed": False,
            "decision_score_enabled": False,
            "target_price_enabled": False,
            "automatic_execution_enabled": False,
        }


def build_decision_view_selection_rule(
    *,
    rule_id: str,
    registered_at: datetime,
    security_id: str,
    target_variable: str,
    target_date: date,
    unit: str,
    selected_forecaster_kind: ForecasterKind,
    selected_model_family: str,
    rationale: str,
    source_evidence_ids: tuple[str, ...],
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> DecisionViewSelectionRuleSnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    return DecisionViewSelectionRuleSnapshot(
        rule_id=rule_id,
        registered_at=registered_at,
        security_id=security_id,
        target_variable=target_variable,
        target_date=target_date,
        unit=unit,
        selection_method=DecisionViewSelectionMethod.PINNED_FORECASTER_IDENTITY,
        selected_forecaster_kind=selected_forecaster_kind,
        selected_model_family=selected_model_family,
        rationale=rationale,
        source_evidence_ids=source_evidence_ids,
        guardrail_evidence_id=active.evidence_id,
    )


def build_decision_view(
    rule: DecisionViewSelectionRuleSnapshot,
    forecasts: tuple[ForecastRegistrationSnapshot, ...],
    *,
    captured_at: datetime,
    evaluation_date: date,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> DecisionViewSnapshot:
    """Select the pinned forecaster only after proving the rule predates all registrations."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if rule.guardrail_evidence_id != active.evidence_id:
        raise ValueError("Decision View selection rule guardrail evidence mismatch")
    tournament = assess_forecast_tournament(
        forecasts,
        thesis_security_id=rule.security_id,
        evaluation_date=evaluation_date,
        guardrails=active,
    )
    if not tournament.comparable:
        raise ValueError(
            "Decision View requires a comparable forecast tournament: "
            + ",".join(tournament.blockers)
        )
    for forecast in forecasts:
        if forecast.target_variable != rule.target_variable:
            raise ValueError("forecast target_variable differs from Decision View rule")
        if forecast.target_date != rule.target_date:
            raise ValueError("forecast target_date differs from Decision View rule")
        if forecast.unit != rule.unit:
            raise ValueError("forecast unit differs from Decision View rule")
        if rule.registered_at > forecast.registered_at:
            raise ValueError("Decision View rule must be registered before forecast values")
        if forecast.ledger_recorded_at > captured_at:
            raise ValueError("Decision View cannot precede forecast ledger recording")
    matches = tuple(
        forecast
        for forecast in forecasts
        if forecast.forecaster_kind is rule.selected_forecaster_kind
        and forecast.model_family == rule.selected_model_family
    )
    if len(matches) != 1:
        raise ValueError("Decision View rule must resolve to exactly one tournament forecast")
    selected = matches[0]
    return DecisionViewSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        selection_rule_snapshot_id=rule.snapshot_id,
        security_id=rule.security_id,
        target_variable=rule.target_variable,
        target_date=rule.target_date,
        unit=rule.unit,
        selected_forecast_snapshot_id=selected.snapshot_id,
        selected_forecast_id=selected.forecast_id,
        selected_forecaster_kind=selected.forecaster_kind,
        selected_model_family=selected.model_family,
        selected_forecast_value=float(selected.forecast_value),
        forecast_origin=selected.forecast_origin,
        information_cutoff=selected.information_cutoff,
        tournament_forecast_snapshot_ids=tuple(
            sorted(forecast.snapshot_id for forecast in forecasts)
        ),
        tournament_dependency_overlap=(
            "forecast_dependency_overlap" in tournament.flags
        ),
        guardrail_evidence_id=active.evidence_id,
    )


def build_decision_expectation_gap(
    decision_view: DecisionViewSnapshot,
    expectations: ExpectationStateSnapshot,
    *,
    captured_at: datetime,
    evaluation_date: date,
    price_implied: PriceImpliedRequirementSnapshot | None = None,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> DecisionExpectationGapSnapshot:
    """Compare our view with each certified consensus and each conditional price reference."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if decision_view.guardrail_evidence_id != active.evidence_id:
        raise ValueError("Decision View guardrail evidence mismatch")
    if decision_view.evaluation_date != evaluation_date:
        raise ValueError("Decision View evaluation_date mismatch")
    if expectations.evaluation_date != evaluation_date:
        raise ValueError("expectation-state evaluation_date mismatch")
    if decision_view.captured_at > captured_at or expectations.captured_at > captured_at:
        raise ValueError("expectation-gap capture cannot precede source snapshots")
    try:
        metric = ExpectationMetric(decision_view.target_variable)
    except ValueError as exc:
        raise ValueError("Decision View target is not a certified expectation metric") from exc

    matching_consensus = tuple(
        item
        for item in expectations.observations
        if item.security_id == decision_view.security_id
        and item.metric is metric
        and item.target_period_end == decision_view.target_date
        and item.unit == decision_view.unit
        and item.expectation_kind is ExpectationKind.MARKET_CONSENSUS
        and item.market_consensus_certified
    )
    if not matching_consensus:
        raise ValueError("no certified market consensus matches the Decision View target")
    consensus_gaps = tuple(
        _consensus_gap(decision_view, item) for item in matching_consensus
    )

    price_gaps: tuple[PriceImpliedGapObservation, ...] = ()
    flags: list[str] = []
    price_snapshot_id: str | None = None
    if price_implied is None:
        flags.append("price_implied_comparison_not_supplied")
    else:
        if price_implied.evaluation_date != evaluation_date:
            raise ValueError("price-implied evaluation_date mismatch")
        if price_implied.security_id != decision_view.security_id:
            raise ValueError("price-implied security differs from Decision View")
        if price_implied.guardrail_evidence_id != active.evidence_id:
            raise ValueError("price-implied guardrail evidence mismatch")
        if price_implied.captured_at > captured_at:
            raise ValueError("expectation-gap capture cannot precede price-implied snapshot")
        price_snapshot_id = price_implied.snapshot_id
        matching_price = tuple(
            item
            for item in price_implied.observations
            if item.status is PriceImpliedRequirementStatus.AVAILABLE
            and item.implied_metric is metric
            and item.target_period_end == decision_view.target_date
            and item.implied_value_krw is not None
        )
        if matching_price:
            decision_krw = _to_krw(
                decision_view.selected_forecast_value,
                decision_view.unit,
            )
            price_gaps = tuple(
                _price_gap(decision_krw, item) for item in matching_price
            )
        else:
            flags.append("price_implied_metric_or_period_not_comparable")

    if decision_view.tournament_dependency_overlap:
        flags.append("decision_view_tournament_dependency_overlap")

    return DecisionExpectationGapSnapshot(
        captured_at=captured_at,
        evaluation_date=evaluation_date,
        decision_view_snapshot_id=decision_view.snapshot_id,
        expectation_state_snapshot_id=expectations.snapshot_id,
        price_implied_requirement_snapshot_id=price_snapshot_id,
        security_id=decision_view.security_id,
        target_variable=decision_view.target_variable,
        target_date=decision_view.target_date,
        unit=decision_view.unit,
        consensus_gaps=consensus_gaps,
        price_implied_gaps=price_gaps,
        flags=tuple(flags),
        guardrail_evidence_id=active.evidence_id,
    )


def persist_decision_view_selection_rule(
    snapshot: DecisionViewSelectionRuleSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        "decision_view_selection_rule",
        snapshot.snapshot_id,
        snapshot.registered_at,
        snapshot.payload_without_id(),
        output_root,
    )


def persist_decision_view(
    snapshot: DecisionViewSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        "decision_view",
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
    )


def persist_decision_expectation_gap(
    snapshot: DecisionExpectationGapSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist(
        "decision_expectation_gap",
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
    )


def _consensus_gap(decision_view: DecisionViewSnapshot, observation: object) -> ConsensusGapObservation:
    provider_id = str(getattr(observation, "provider_id"))
    source_evidence_id = str(getattr(observation, "source_evidence_id"))
    observed_at = cast(datetime, getattr(observation, "observed_at"))
    consensus_value = float(getattr(observation, "value"))
    absolute_gap = decision_view.selected_forecast_value - consensus_value
    relative_gap = (
        absolute_gap / abs(consensus_value) if consensus_value != 0 else None
    )
    return ConsensusGapObservation(
        provider_id=provider_id,
        source_evidence_id=source_evidence_id,
        observed_at=observed_at,
        decision_value=decision_view.selected_forecast_value,
        consensus_value=consensus_value,
        unit=decision_view.unit,
        absolute_gap=absolute_gap,
        relative_gap=relative_gap,
    )


def _price_gap(decision_value_krw: float, observation: object) -> PriceImpliedGapObservation:
    implied_value = float(cast(float, getattr(observation, "implied_value_krw")))
    absolute_gap = decision_value_krw - implied_value
    return PriceImpliedGapObservation(
        reference_id=str(getattr(observation, "reference_id")),
        reference_kind=str(getattr(observation, "reference_kind").value),
        reference_multiple=float(getattr(observation, "reference_multiple")),
        decision_value_krw=decision_value_krw,
        implied_value_krw=implied_value,
        absolute_gap_krw=absolute_gap,
        relative_gap=absolute_gap / implied_value,
    )


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
        raise ValueError(
            f"Decision View unit cannot be compared with price-implied KRW: {unit}"
        ) from exc
    result = float(value) * factor
    _require_finite(result, "decision_value_krw")
    return result


def _persist(
    object_name: str,
    snapshot_id: str,
    captured_at: datetime,
    payload: dict[str, object],
    output_root: str | Path,
) -> Path:
    root = Path(output_root) / object_name
    root.mkdir(parents=True, exist_ok=True)
    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot_id[:12]}"
    pointer = root / f"latest_{object_name}.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot_id:
            raise ValueError(f"existing {object_name} directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            manifest = {
                "schema_version": DECISION_VIEW_SCHEMA_VERSION,
                "object_type": object_name,
                "snapshot_id": snapshot_id,
                "captured_at": captured_at.isoformat(),
                "immutable": True,
                "files": [f"{object_name}.json"],
                "decision_score_enabled": False,
                "target_price_enabled": False,
                "automatic_execution_enabled": False,
            }
            (temporary / f"{object_name}.json").write_text(
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
                "schema_version": DECISION_VIEW_SCHEMA_VERSION,
                "object_type": object_name,
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
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _validate_sha(value, field)
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
    "ConsensusGapObservation",
    "DecisionExpectationGapSnapshot",
    "DecisionViewSelectionMethod",
    "DecisionViewSelectionRuleSnapshot",
    "DecisionViewSnapshot",
    "PriceImpliedGapObservation",
    "build_decision_expectation_gap",
    "build_decision_view",
    "build_decision_view_selection_rule",
    "persist_decision_expectation_gap",
    "persist_decision_view",
    "persist_decision_view_selection_rule",
]
