"""Trusted persisted repositories for Decision System v2.1 research-package components.

Persistence writers for underwriting, payoff, and Decision View artifacts predate the end-to-end
package assembler. This read-side module verifies complete payload identity, manifests, directory
identity, latest pointers, typed reconstruction, and the PIT cutoff before returning components to
the existing research-round orchestrator.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast

from alpha_cycle.intelligence.decision_view_v2_1 import (
    ConsensusGapObservation,
    DecisionExpectationGapSnapshot,
    DecisionViewSnapshot,
    PriceImpliedGapObservation,
)
from alpha_cycle.intelligence.forecast_ledger import ForecasterKind
from alpha_cycle.intelligence.payoff_surface import (
    PayoffScenario,
    PayoffSurfaceSnapshot,
    ScenarioLabel,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    ForecastTournamentAssessment,
    UnderwritingLane,
    UnderwritingReadiness,
    UnderwritingReadinessSnapshot,
)

_COMPONENT_SCHEMA_VERSION = 1


class ResearchComponentRepositoryError(ValueError):
    """Raised when a persisted research component fails trust-boundary validation."""


class _Component(Protocol):
    @property
    def captured_at(self) -> datetime: ...

    @property
    def security_id(self) -> str: ...

    @property
    def snapshot_id(self) -> str: ...


@dataclass(frozen=True)
class _ArtifactRef:
    snapshot_id: str
    captured_at: datetime
    directory: Path


@dataclass(frozen=True)
class ResearchComponentRepositoryIndex:
    """One validated PIT scan of every package component repository."""

    as_of: datetime
    underwriting_by_security: dict[str, tuple[UnderwritingReadinessSnapshot, ...]]
    payoff_by_security: dict[str, tuple[PayoffSurfaceSnapshot, ...]]
    decision_view_by_security: dict[str, tuple[DecisionViewSnapshot, ...]]
    expectation_gap_by_security: dict[str, tuple[DecisionExpectationGapSnapshot, ...]]

    def latest_underwriting(
        self,
        security_id: str,
        *,
        thesis_snapshot_id: str,
        evaluation_date: date,
        lane: UnderwritingLane,
        guardrail_evidence_id: str,
    ) -> UnderwritingReadinessSnapshot | None:
        return _latest_unique(
            self.underwriting_by_security.get(security_id, ()),
            predicate=lambda item: (
                item.thesis_snapshot_id == thesis_snapshot_id
                and item.evaluation_date == evaluation_date
                and item.lane is lane
                and item.guardrail_evidence_id == guardrail_evidence_id
            ),
            component="underwriting_readiness",
        )

    def latest_payoff(
        self,
        security_id: str,
        *,
        thesis_snapshot_id: str,
        horizon_trading_days: int,
        guardrail_evidence_id: str,
    ) -> PayoffSurfaceSnapshot | None:
        return _latest_unique(
            self.payoff_by_security.get(security_id, ()),
            predicate=lambda item: (
                item.thesis_snapshot_id == thesis_snapshot_id
                and item.horizon_trading_days == horizon_trading_days
                and item.guardrail_evidence_id == guardrail_evidence_id
            ),
            component="payoff_surface",
        )

    def latest_decision_view(
        self,
        security_id: str,
        *,
        evaluation_date: date,
        guardrail_evidence_id: str,
    ) -> DecisionViewSnapshot | None:
        return _latest_unique(
            self.decision_view_by_security.get(security_id, ()),
            predicate=lambda item: (
                item.evaluation_date == evaluation_date
                and item.guardrail_evidence_id == guardrail_evidence_id
            ),
            component="decision_view",
        )

    def latest_expectation_gap(
        self,
        security_id: str,
        *,
        decision_view_snapshot_id: str,
        evaluation_date: date,
        guardrail_evidence_id: str,
    ) -> DecisionExpectationGapSnapshot | None:
        return _latest_unique(
            self.expectation_gap_by_security.get(security_id, ()),
            predicate=lambda item: (
                item.decision_view_snapshot_id == decision_view_snapshot_id
                and item.evaluation_date == evaluation_date
                and item.guardrail_evidence_id == guardrail_evidence_id
            ),
            component="decision_expectation_gap",
        )


def build_research_component_repository_index(
    artifact_root: str | Path,
    *,
    as_of: datetime,
) -> ResearchComponentRepositoryIndex:
    """Scan each persisted component directory exactly once for one PIT cutoff."""

    _require_aware(as_of, "as_of")
    root = Path(artifact_root)
    underwriting = _scan_repository(
        root / "underwriting_readiness",
        object_name="underwriting_readiness",
        parser=_parse_underwriting_readiness,
        manifest_validator=_validate_underwriting_manifest,
        pointer_name="latest_underwriting_readiness.json",
        as_of=as_of,
    )
    payoff = _scan_repository(
        root / "payoff_surface",
        object_name="payoff_surface",
        parser=_parse_payoff_surface,
        manifest_validator=_validate_payoff_manifest,
        pointer_name="latest_payoff_surface.json",
        as_of=as_of,
    )
    views = _scan_repository(
        root / "decision_view",
        object_name="decision_view",
        parser=_parse_decision_view,
        manifest_validator=_validate_decision_manifest,
        pointer_name="latest_decision_view.json",
        as_of=as_of,
    )
    gaps = _scan_repository(
        root / "decision_expectation_gap",
        object_name="decision_expectation_gap",
        parser=_parse_expectation_gap,
        manifest_validator=_validate_decision_manifest,
        pointer_name="latest_decision_expectation_gap.json",
        as_of=as_of,
    )
    return ResearchComponentRepositoryIndex(
        as_of=as_of,
        underwriting_by_security=_group_by_security(underwriting),
        payoff_by_security=_group_by_security(payoff),
        decision_view_by_security=_group_by_security(views),
        expectation_gap_by_security=_group_by_security(gaps),
    )


def _scan_repository[T: _Component](
    root: Path,
    *,
    object_name: str,
    parser: Callable[[dict[str, Any]], T],
    manifest_validator: Callable[[dict[str, Any], T], None],
    pointer_name: str,
    as_of: datetime,
) -> tuple[T, ...]:
    if not root.exists():
        return ()
    if root.is_symlink():
        raise ResearchComponentRepositoryError(
            f"{object_name} repository root cannot be a symlink"
        )
    resolved_root = root.resolve()
    loaded: list[T] = []
    by_id: dict[str, _ArtifactRef] = {}
    directories = sorted(
        path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    for directory in directories:
        if directory.is_symlink():
            raise ResearchComponentRepositoryError(
                f"{object_name} snapshot directory cannot be a symlink"
            )
        resolved_directory = directory.resolve()
        if resolved_directory.parent != resolved_root:
            raise ResearchComponentRepositoryError(
                f"{object_name} snapshot directory escapes repository root"
            )
        manifest_path = directory / "manifest.json"
        payload_path = directory / f"{object_name}.json"
        _require_repository_child_file(
            manifest_path,
            directory=resolved_directory,
            object_name=object_name,
        )
        _require_repository_child_file(
            payload_path,
            directory=resolved_directory,
            object_name=object_name,
        )
        manifest = _load_object(manifest_path)
        payload = _load_object(payload_path)
        if _required_int(manifest, "schema_version") != _COMPONENT_SCHEMA_VERSION:
            raise ResearchComponentRepositoryError(
                f"unsupported {object_name} manifest schema"
            )
        declared = _required_text(manifest, "snapshot_id")
        if _sha(payload) != declared:
            raise ResearchComponentRepositoryError(
                f"{object_name} snapshot_id does not match complete persisted payload"
            )
        snapshot = parser(payload)
        if snapshot.snapshot_id != declared:
            raise ResearchComponentRepositoryError(
                f"{object_name} typed reconstruction changed snapshot identity"
            )
        manifest_validator(manifest, snapshot)
        utc_prefix = snapshot.captured_at.astimezone(UTC).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        if directory.name != f"{utc_prefix}__{declared[:12]}":
            raise ResearchComponentRepositoryError(
                f"{object_name} directory identity mismatch"
            )
        prior = by_id.get(declared)
        if prior is not None and prior.directory != directory:
            raise ResearchComponentRepositoryError(
                f"duplicate {object_name} snapshot_id"
            )
        by_id[declared] = _ArtifactRef(
            snapshot_id=declared,
            captured_at=snapshot.captured_at,
            directory=resolved_directory,
        )
        if snapshot.captured_at <= as_of:
            loaded.append(snapshot)

    pointer_path = root / pointer_name
    if pointer_path.exists():
        _require_repository_child_file(
            pointer_path,
            directory=resolved_root,
            object_name=object_name,
        )
        _validate_pointer(
            pointer_path,
            root=resolved_root,
            object_name=object_name,
            by_id=by_id,
        )
    return tuple(loaded)


def _require_repository_child_file(
    path: Path,
    *,
    directory: Path,
    object_name: str,
) -> None:
    if path.is_symlink():
        raise ResearchComponentRepositoryError(
            f"{object_name} repository file cannot be a symlink: {path.name}"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ResearchComponentRepositoryError(
            f"cannot resolve {object_name} repository file: {path}"
        ) from exc
    if resolved.parent != directory:
        raise ResearchComponentRepositoryError(
            f"{object_name} repository file escapes snapshot directory"
        )


def _validate_pointer(
    path: Path,
    *,
    root: Path,
    object_name: str,
    by_id: dict[str, _ArtifactRef],
) -> None:
    payload = _load_object(path)
    expected = {"schema_version", "snapshot_id", "snapshot_path"}
    if object_name != "payoff_surface":
        expected.add("object_type")
    if set(payload) != expected:
        raise ResearchComponentRepositoryError(
            f"{object_name} latest pointer fields are not canonical"
        )
    if _required_int(payload, "schema_version") != _COMPONENT_SCHEMA_VERSION:
        raise ResearchComponentRepositoryError(
            f"unsupported {object_name} pointer schema"
        )
    if (
        "object_type" in payload
        and _required_text(payload, "object_type") != object_name
    ):
        raise ResearchComponentRepositoryError(
            f"{object_name} pointer object_type mismatch"
        )
    snapshot_id = _required_text(payload, "snapshot_id")
    artifact = by_id.get(snapshot_id)
    if artifact is None:
        raise ResearchComponentRepositoryError(
            f"{object_name} pointer references missing snapshot"
        )
    pointer_target = Path(_required_text(payload, "snapshot_path"))
    if not pointer_target.is_absolute():
        pointer_target = (Path.cwd() / pointer_target).resolve()
    resolved_target = pointer_target.resolve()
    if resolved_target != artifact.directory:
        raise ResearchComponentRepositoryError(
            f"{object_name} pointer path disagrees with snapshot"
        )
    if resolved_target.parent != root:
        raise ResearchComponentRepositoryError(
            f"{object_name} pointer escapes repository root"
        )


def _validate_underwriting_manifest(
    manifest: dict[str, Any],
    value: UnderwritingReadinessSnapshot,
) -> None:
    expected = {
        "schema_version",
        "object_type",
        "snapshot_id",
        "captured_at",
        "immutable",
        "files",
        "thesis_snapshot_id",
        "security_id",
        "lane",
        "readiness",
        "investability_decision_enabled",
        "automatic_execution_enabled",
    }
    _require_exact_keys(manifest, expected, "underwriting_readiness manifest")
    checks = (
        (
            _required_text(manifest, "object_type") == "underwriting_readiness",
            "object_type",
        ),
        (
            _required_text(manifest, "captured_at") == value.captured_at.isoformat(),
            "captured_at",
        ),
        (_required_bool(manifest, "immutable") is True, "immutable"),
        (
            _required_list(manifest, "files") == ["underwriting_readiness.json"],
            "files",
        ),
        (
            _required_text(manifest, "thesis_snapshot_id")
            == value.thesis_snapshot_id,
            "thesis",
        ),
        (
            _required_text(manifest, "security_id") == value.security_id,
            "security",
        ),
        (_required_text(manifest, "lane") == value.lane.value, "lane"),
        (
            _required_text(manifest, "readiness") == value.readiness.value,
            "readiness",
        ),
        (
            _required_bool(manifest, "investability_decision_enabled") is False,
            "investability",
        ),
        (
            _required_bool(manifest, "automatic_execution_enabled") is False,
            "execution",
        ),
    )
    _require_checks(checks, "underwriting_readiness manifest")


def _validate_payoff_manifest(
    manifest: dict[str, Any],
    value: PayoffSurfaceSnapshot,
) -> None:
    expected = {
        "schema_version",
        "snapshot_id",
        "captured_at",
        "thesis_snapshot_id",
        "security_id",
        "horizon_trading_days",
        "scenario_count",
        "guardrail_evidence_id",
        "probabilities_calibrated",
        "expected_value_calculated",
        "target_price_enabled",
        "optimal_position_size_enabled",
        "order_api_enabled",
        "files",
    }
    _require_exact_keys(manifest, expected, "payoff_surface manifest")
    checks = (
        (
            _required_text(manifest, "captured_at") == value.captured_at.isoformat(),
            "captured_at",
        ),
        (
            _required_text(manifest, "thesis_snapshot_id")
            == value.thesis_snapshot_id,
            "thesis",
        ),
        (
            _required_text(manifest, "security_id") == value.security_id,
            "security",
        ),
        (
            _required_int(manifest, "horizon_trading_days")
            == value.horizon_trading_days,
            "horizon",
        ),
        (
            _required_int(manifest, "scenario_count") == len(value.scenarios),
            "scenario_count",
        ),
        (
            _required_text(manifest, "guardrail_evidence_id")
            == value.guardrail_evidence_id,
            "guardrail",
        ),
        (_required_list(manifest, "files") == ["payoff_surface.json"], "files"),
        (
            _required_bool(manifest, "probabilities_calibrated") is False,
            "probabilities",
        ),
        (
            _required_bool(manifest, "expected_value_calculated") is False,
            "expected_value",
        ),
        (_required_bool(manifest, "target_price_enabled") is False, "target_price"),
        (
            _required_bool(manifest, "optimal_position_size_enabled") is False,
            "position_size",
        ),
        (_required_bool(manifest, "order_api_enabled") is False, "order_api"),
    )
    _require_checks(checks, "payoff_surface manifest")


def _validate_decision_manifest(manifest: dict[str, Any], value: _Component) -> None:
    expected = {
        "schema_version",
        "object_type",
        "snapshot_id",
        "captured_at",
        "immutable",
        "files",
        "decision_score_enabled",
        "target_price_enabled",
        "automatic_execution_enabled",
    }
    _require_exact_keys(manifest, expected, "decision manifest")
    object_name = (
        "decision_expectation_gap"
        if isinstance(value, DecisionExpectationGapSnapshot)
        else "decision_view"
    )
    checks = (
        (_required_text(manifest, "object_type") == object_name, "object_type"),
        (
            _required_text(manifest, "captured_at") == value.captured_at.isoformat(),
            "captured_at",
        ),
        (_required_bool(manifest, "immutable") is True, "immutable"),
        (
            _required_list(manifest, "files") == [f"{object_name}.json"],
            "files",
        ),
        (
            _required_bool(manifest, "decision_score_enabled") is False,
            "decision_score",
        ),
        (_required_bool(manifest, "target_price_enabled") is False, "target_price"),
        (
            _required_bool(manifest, "automatic_execution_enabled") is False,
            "execution",
        ),
    )
    _require_checks(checks, "decision manifest")


def _parse_underwriting_readiness(
    payload: dict[str, Any],
) -> UnderwritingReadinessSnapshot:
    _require_payload_schema(payload, "underwriting_readiness")
    tournament = _object(payload.get("forecast_tournament"), "forecast_tournament")
    target_date_raw = tournament.get("target_date")
    forecast_origin_raw = tournament.get("forecast_origin")
    cutoff_raw = tournament.get("information_cutoff")
    assessment = ForecastTournamentAssessment(
        comparable=_required_bool(tournament, "comparable"),
        forecast_snapshot_ids=_text_tuple(tournament, "forecast_snapshot_ids"),
        forecast_ids=_text_tuple(tournament, "forecast_ids"),
        security_id=_optional_text(tournament, "security_id"),
        target_variable=_optional_text(tournament, "target_variable"),
        target_date=(
            None
            if target_date_raw is None
            else _date(_text(target_date_raw, "target_date"), "target_date")
        ),
        unit=_optional_text(tournament, "unit"),
        forecast_origin=(
            None
            if forecast_origin_raw is None
            else _datetime(
                _text(forecast_origin_raw, "forecast_origin"),
                "forecast_origin",
            )
        ),
        information_cutoff=(
            None
            if cutoff_raw is None
            else _datetime(
                _text(cutoff_raw, "information_cutoff"),
                "information_cutoff",
            )
        ),
        primary_error_metric=_optional_text(tournament, "primary_error_metric"),
        distinct_forecaster_count=_required_int(
            tournament,
            "distinct_forecaster_count",
        ),
        dependency_cluster_count=_required_int(
            tournament,
            "dependency_cluster_count",
        ),
        blockers=_text_tuple(tournament, "blockers"),
        flags=_text_tuple(tournament, "flags"),
    )
    value = UnderwritingReadinessSnapshot(
        captured_at=_datetime(
            _required_text(payload, "captured_at"),
            "captured_at",
        ),
        evaluation_date=_date(
            _required_text(payload, "evaluation_date"),
            "evaluation_date",
        ),
        thesis_snapshot_id=_required_text(payload, "thesis_snapshot_id"),
        security_id=_required_text(payload, "security_id"),
        lane=_enum(UnderwritingLane, payload, "lane"),
        readiness=_enum(UnderwritingReadiness, payload, "readiness"),
        guardrail_evidence_id=_required_text(payload, "guardrail_evidence_id"),
        context_snapshot_id=_required_text(payload, "context_snapshot_id"),
        causal_graph_snapshot_id=_optional_text(payload, "causal_graph_snapshot_id"),
        forecast_tournament=assessment,
        expectation_state_snapshot_id=_optional_text(
            payload,
            "expectation_state_snapshot_id",
        ),
        forward_valuation_snapshot_id=_optional_text(
            payload,
            "forward_valuation_snapshot_id",
        ),
        price_implied_requirement_snapshot_id=_optional_text(
            payload,
            "price_implied_requirement_snapshot_id",
        ),
        payoff_surface_snapshot_id=_optional_text(
            payload,
            "payoff_surface_snapshot_id",
        ),
        epistemic_defense_snapshot_id=_optional_text(
            payload,
            "epistemic_defense_snapshot_id",
        ),
        required_elements_satisfied=_text_tuple(
            payload,
            "required_elements_satisfied",
        ),
        required_elements_missing=_text_tuple(
            payload,
            "required_elements_missing",
        ),
        blockers=_text_tuple(payload, "blockers"),
        flags=_text_tuple(payload, "flags"),
    )
    for field in (
        "investability_decision_enabled",
        "automatic_thesis_transition_enabled",
        "target_price_enabled",
        "optimal_position_size_enabled",
        "automatic_execution_enabled",
    ):
        if _required_bool(payload, field):
            raise ResearchComponentRepositoryError(
                f"underwriting safety flag {field} must be false"
            )
    return value


def _parse_payoff_surface(payload: dict[str, Any]) -> PayoffSurfaceSnapshot:
    _require_payload_schema(payload, "payoff_surface")
    scenarios = tuple(
        _parse_payoff_scenario(_object(item, "scenario"))
        for item in _required_list(payload, "scenarios")
    )
    value = PayoffSurfaceSnapshot(
        captured_at=_datetime(
            _required_text(payload, "captured_at"),
            "captured_at",
        ),
        thesis_snapshot_id=_required_text(payload, "thesis_snapshot_id"),
        security_id=_required_text(payload, "security_id"),
        horizon_trading_days=_required_int(payload, "horizon_trading_days"),
        scenarios=scenarios,
        source_snapshot_ids=_text_tuple(payload, "source_snapshot_ids"),
        guardrail_evidence_id=_required_text(payload, "guardrail_evidence_id"),
        warnings=_text_tuple(payload, "warnings"),
    )
    for field in (
        "probabilities_calibrated",
        "expected_value_calculated",
        "target_price_enabled",
        "optimal_position_size_enabled",
        "automatic_execution_enabled",
    ):
        if _required_bool(payload, field):
            raise ResearchComponentRepositoryError(
                f"payoff safety flag {field} must be false"
            )
    return value


def _parse_payoff_scenario(payload: dict[str, Any]) -> PayoffScenario:
    if payload.get("scenario_probability") is not None:
        raise ResearchComponentRepositoryError(
            "payoff scenario probability must remain null"
        )
    return PayoffScenario(
        scenario_id=_required_text(payload, "scenario_id"),
        label=_enum(ScenarioLabel, payload, "label"),
        horizon_trading_days=_required_int(payload, "horizon_trading_days"),
        trigger_conditions=_text_tuple(payload, "trigger_conditions"),
        fundamental_assumptions=_text_tuple(payload, "fundamental_assumptions"),
        catalyst_refs=_text_tuple(payload, "catalyst_refs"),
        source_evidence_ids=_text_tuple(payload, "source_evidence_ids"),
        return_lower=_number(payload, "return_lower"),
        return_upper=_number(payload, "return_upper"),
        thesis_break_conditions=_text_tuple(payload, "thesis_break_conditions"),
    )


def _parse_decision_view(payload: dict[str, Any]) -> DecisionViewSnapshot:
    _require_payload_schema(payload, "decision_view")
    value = DecisionViewSnapshot(
        captured_at=_datetime(
            _required_text(payload, "captured_at"),
            "captured_at",
        ),
        evaluation_date=_date(
            _required_text(payload, "evaluation_date"),
            "evaluation_date",
        ),
        selection_rule_snapshot_id=_required_text(
            payload,
            "selection_rule_snapshot_id",
        ),
        security_id=_required_text(payload, "security_id"),
        target_variable=_required_text(payload, "target_variable"),
        target_date=_date(_required_text(payload, "target_date"), "target_date"),
        unit=_required_text(payload, "unit"),
        selected_forecast_snapshot_id=_required_text(
            payload,
            "selected_forecast_snapshot_id",
        ),
        selected_forecast_id=_required_text(payload, "selected_forecast_id"),
        selected_forecaster_kind=_enum(
            ForecasterKind,
            payload,
            "selected_forecaster_kind",
        ),
        selected_model_family=_required_text(payload, "selected_model_family"),
        selected_forecast_value=_number(payload, "selected_forecast_value"),
        forecast_origin=_datetime(
            _required_text(payload, "forecast_origin"),
            "forecast_origin",
        ),
        information_cutoff=_datetime(
            _required_text(payload, "information_cutoff"),
            "information_cutoff",
        ),
        tournament_forecast_snapshot_ids=_text_tuple(
            payload,
            "tournament_forecast_snapshot_ids",
        ),
        tournament_dependency_overlap=_required_bool(
            payload,
            "tournament_dependency_overlap",
        ),
        guardrail_evidence_id=_required_text(payload, "guardrail_evidence_id"),
    )
    for field in (
        "ex_post_forecast_value_selection_enabled",
        "automatic_ensemble_weighting_enabled",
        "market_consensus_claimed",
        "target_price_enabled",
        "automatic_execution_enabled",
    ):
        if _required_bool(payload, field):
            raise ResearchComponentRepositoryError(
                f"decision-view safety flag {field} must be false"
            )
    return value


def _parse_expectation_gap(
    payload: dict[str, Any],
) -> DecisionExpectationGapSnapshot:
    _require_payload_schema(payload, "decision_expectation_gap")
    consensus = tuple(
        _parse_consensus_gap(_object(item, "consensus_gap"))
        for item in _required_list(payload, "consensus_gaps")
    )
    price = tuple(
        _parse_price_gap(_object(item, "price_gap"))
        for item in _required_list(payload, "price_implied_gaps")
    )
    value = DecisionExpectationGapSnapshot(
        captured_at=_datetime(
            _required_text(payload, "captured_at"),
            "captured_at",
        ),
        evaluation_date=_date(
            _required_text(payload, "evaluation_date"),
            "evaluation_date",
        ),
        decision_view_snapshot_id=_required_text(
            payload,
            "decision_view_snapshot_id",
        ),
        expectation_state_snapshot_id=_required_text(
            payload,
            "expectation_state_snapshot_id",
        ),
        price_implied_requirement_snapshot_id=_optional_text(
            payload,
            "price_implied_requirement_snapshot_id",
        ),
        security_id=_required_text(payload, "security_id"),
        target_variable=_required_text(payload, "target_variable"),
        target_date=_date(_required_text(payload, "target_date"), "target_date"),
        unit=_required_text(payload, "unit"),
        consensus_gaps=consensus,
        price_implied_gaps=price,
        flags=_text_tuple(payload, "flags"),
        guardrail_evidence_id=_required_text(payload, "guardrail_evidence_id"),
    )
    for field in (
        "consensus_provider_aggregation_enabled",
        "price_reference_aggregation_enabled",
        "price_implied_market_expectation_claimed",
        "decision_score_enabled",
        "target_price_enabled",
        "automatic_execution_enabled",
    ):
        if _required_bool(payload, field):
            raise ResearchComponentRepositoryError(
                f"expectation-gap safety flag {field} must be false"
            )
    return value


def _parse_consensus_gap(payload: dict[str, Any]) -> ConsensusGapObservation:
    return ConsensusGapObservation(
        provider_id=_required_text(payload, "provider_id"),
        source_evidence_id=_required_text(payload, "source_evidence_id"),
        observed_at=_datetime(
            _required_text(payload, "observed_at"),
            "observed_at",
        ),
        decision_value=_number(payload, "decision_value"),
        consensus_value=_number(payload, "consensus_value"),
        unit=_required_text(payload, "unit"),
        absolute_gap=_number(payload, "absolute_gap"),
        relative_gap=_optional_number(payload, "relative_gap"),
    )


def _parse_price_gap(payload: dict[str, Any]) -> PriceImpliedGapObservation:
    if _required_bool(payload, "market_expectation_claimed"):
        raise ResearchComponentRepositoryError(
            "price-implied gap cannot claim market expectation"
        )
    return PriceImpliedGapObservation(
        reference_id=_required_text(payload, "reference_id"),
        reference_kind=_required_text(payload, "reference_kind"),
        reference_multiple=_number(payload, "reference_multiple"),
        decision_value_krw=_number(payload, "decision_value_krw"),
        implied_value_krw=_number(payload, "implied_value_krw"),
        absolute_gap_krw=_number(payload, "absolute_gap_krw"),
        relative_gap=_number(payload, "relative_gap"),
    )


def _group_by_security[T: _Component](values: tuple[T, ...]) -> dict[str, tuple[T, ...]]:
    grouped: dict[str, list[T]] = defaultdict(list)
    for value in values:
        if not value.security_id.strip():
            raise ResearchComponentRepositoryError(
                "typed component lacks security_id"
            )
        grouped[value.security_id].append(value)
    return {
        key: tuple(
            sorted(
                items,
                key=lambda item: (item.captured_at, item.snapshot_id),
            )
        )
        for key, items in grouped.items()
    }


def _latest_unique[T: _Component](
    values: tuple[T, ...],
    *,
    predicate: Callable[[T], bool],
    component: str,
) -> T | None:
    candidates = tuple(item for item in values if predicate(item))
    if not candidates:
        return None
    latest_time = max(item.captured_at for item in candidates)
    latest = tuple(item for item in candidates if item.captured_at == latest_time)
    if len(latest) != 1:
        raise ResearchComponentRepositoryError(
            f"ambiguous latest {component} snapshots at one capture time"
        )
    return latest[0]


def _require_payload_schema(payload: dict[str, Any], component: str) -> None:
    if _required_int(payload, "schema_version") != _COMPONENT_SCHEMA_VERSION:
        raise ResearchComponentRepositoryError(
            f"unsupported {component} payload schema"
        )


def _require_checks(checks: tuple[tuple[bool, str], ...], label: str) -> None:
    for condition, field in checks:
        if not condition:
            raise ResearchComponentRepositoryError(f"{label} {field} mismatch")


def _require_exact_keys(
    payload: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    if set(payload) != expected:
        raise ResearchComponentRepositoryError(
            f"{label} fields are not canonical"
        )


def _load_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchComponentRepositoryError(
            f"cannot read JSON artifact: {path}"
        ) from exc
    return _object(raw, str(path))


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ResearchComponentRepositoryError(
            f"{field} must be a JSON object with string keys"
        )
    return cast(dict[str, Any], value)


def _required_list(payload: dict[str, Any], field: str) -> list[object]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ResearchComponentRepositoryError(f"{field} must be a JSON array")
    return cast(list[object], value)


def _required_text(payload: dict[str, Any], field: str) -> str:
    return _text(payload.get(field), field)


def _optional_text(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    return _text(value, field)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchComponentRepositoryError(f"{field} must be non-empty text")
    return value


def _required_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ResearchComponentRepositoryError(f"{field} must be an integer")
    return value


def _required_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ResearchComponentRepositoryError(f"{field} must be boolean")
    return value


def _text_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    return tuple(_text(item, field) for item in _required_list(payload, field))


def _number(payload: dict[str, Any], field: str) -> float:
    value = payload.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ResearchComponentRepositoryError(f"{field} must be numeric")
    return float(value)


def _optional_number(payload: dict[str, Any], field: str) -> float | None:
    if payload.get(field) is None:
        return None
    return _number(payload, field)


def _datetime(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ResearchComponentRepositoryError(
            f"{field} must be ISO datetime"
        ) from exc
    _require_aware(result, field)
    return result


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ResearchComponentRepositoryError(f"{field} must be ISO date") from exc


def _enum[EnumT: StrEnum](
    enum_type: type[EnumT],
    payload: dict[str, Any],
    field: str,
) -> EnumT:
    raw = _required_text(payload, field)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise ResearchComponentRepositoryError(f"invalid {field}: {raw}") from exc


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


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
    "ResearchComponentRepositoryError",
    "ResearchComponentRepositoryIndex",
    "build_research_component_repository_index",
]
