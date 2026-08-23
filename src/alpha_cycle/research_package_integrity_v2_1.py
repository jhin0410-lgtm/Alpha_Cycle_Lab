"""Integrity helpers for persisted Decision System v2.1 research-package assembly."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import (
    InvestmentThesisSnapshot,
    ThesisStatus,
)
from alpha_cycle.intelligence.decision_view_v2_1 import (
    DecisionExpectationGapSnapshot,
    DecisionViewSnapshot,
)
from alpha_cycle.intelligence.forecast_ledger import (
    FORECAST_LEDGER_SCHEMA_VERSION,
    ForecastRegistrationMode,
)
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OPPORTUNITY_SET_SCHEMA_VERSION,
    OpportunityCandidateSnapshot,
    OpportunitySetSnapshot,
)
from alpha_cycle.intelligence.payoff_surface import PayoffSurfaceSnapshot
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundArtifacts
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    ResearchRoundRunSnapshot,
    ResearchRunLedgerSnapshot,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    SUPPLEMENTAL_DEEP_ELEMENTS,
    UnderwritingLane,
    UnderwritingReadiness,
    UnderwritingReadinessSnapshot,
)
from alpha_cycle.investment_thesis_repository_v2_1 import InvestmentThesisRepositoryError
from alpha_cycle.research_preflight_state_v2_1 import CurrentResearchThesisPreflightState

_TERMINAL_THESIS_STATUSES = frozenset(
    {ThesisStatus.INVALIDATED, ThesisStatus.REPLACED, ThesisStatus.CLOSED}
)
_PUBLICATION_REPOSITORIES = (
    "opportunity_candidate",
    "opportunity_set",
    "research_round_v2_1",
    "research_round_run_v2_1",
    "research_run_ledger_v2_1",
)
_READY_UNDERWRITING_STATES = frozenset(
    {
        UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW,
        UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
        UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS,
    }
)
_KST = ZoneInfo("Asia/Seoul")


class ResearchPackageIntegrityError(ValueError):
    """Raised when persisted package inputs or publication paths fail closed validation."""


def require_trusted_artifact_root(root: Path) -> Path:
    """Reject symlinked/non-directory artifact roots and return the resolved root."""

    if root.is_symlink():
        raise ResearchPackageIntegrityError("artifact_root cannot be a symlink")
    if root.exists() and not root.is_dir():
        raise ResearchPackageIntegrityError("artifact_root must be a directory")
    lexical = Path(os.path.abspath(root))
    resolved = root.resolve()
    if lexical != resolved:
        raise ResearchPackageIntegrityError(
            "artifact_root cannot traverse a symlinked path component"
        )
    _validate_source_ledger_repository(root, resolved_root=resolved)
    return resolved


def _validate_source_ledger_repository(root: Path, *, resolved_root: Path) -> None:
    repository = root / "research_run_ledger_v2_1"
    if repository.is_symlink():
        raise ResearchPackageIntegrityError(
            "research_run_ledger_v2_1 repository cannot be a symlink"
        )
    if not repository.exists():
        return
    if not repository.is_dir():
        raise ResearchPackageIntegrityError(
            "research_run_ledger_v2_1 repository must be a directory"
        )
    resolved_repository = repository.resolve()
    if resolved_repository.parent != resolved_root:
        raise ResearchPackageIntegrityError(
            "research_run_ledger_v2_1 repository escapes artifact_root"
        )
    for path in sorted(repository.glob("*.json")):
        if path.is_symlink():
            raise ResearchPackageIntegrityError(
                "research run ledger artifact cannot be a symlink"
            )
        if not path.is_file():
            raise ResearchPackageIntegrityError(
                "research run ledger artifact must be a regular file"
            )
        try:
            resolved_path = path.resolve(strict=True)
        except OSError as exc:
            raise ResearchPackageIntegrityError(
                f"cannot resolve research run ledger artifact: {path}"
            ) from exc
        if resolved_path.parent != resolved_repository:
            raise ResearchPackageIntegrityError(
                "research run ledger artifact escapes repository root"
            )


def validate_thesis_repository_layout(root: Path) -> None:
    """Ensure the thesis repository cannot escape artifact_root through symlinks."""

    resolved_root = require_trusted_artifact_root(root)
    repository = root / "investment_thesis_v2_1"
    if repository.is_symlink():
        raise InvestmentThesisRepositoryError(
            "investment thesis repository root cannot be a symlink"
        )
    if not repository.exists():
        return
    if not repository.is_dir():
        raise InvestmentThesisRepositoryError(
            "investment thesis repository must be a directory"
        )
    resolved_repository = repository.resolve()
    if resolved_repository.parent != resolved_root:
        raise InvestmentThesisRepositoryError(
            "investment thesis repository escapes artifact_root"
        )
    for path in sorted(repository.glob("*.json")):
        if path.is_symlink():
            raise InvestmentThesisRepositoryError(
                "investment thesis artifact cannot be a symlink"
            )
        if not path.is_file():
            raise InvestmentThesisRepositoryError(
                "investment thesis artifact must be a regular file"
            )
        try:
            resolved_path = path.resolve(strict=True)
        except OSError as exc:
            raise InvestmentThesisRepositoryError(
                f"cannot resolve investment thesis artifact: {path}"
            ) from exc
        if resolved_path.parent != resolved_repository:
            raise InvestmentThesisRepositoryError(
                "investment thesis artifact escapes repository root"
            )


def validate_preflight_selection_timing(
    current: CurrentResearchThesisPreflightState,
    *,
    processed_at: datetime,
) -> None:
    """Require the mutable selection event to bracket its PIT cutoff and processing time."""

    if current.selected_at > processed_at:
        raise ResearchPackageIntegrityError(
            "current thesis preflight selected_at cannot be after processing time"
        )
    if current.selected_at < current.state.research_cutoff_at:
        raise ResearchPackageIntegrityError(
            "current thesis preflight selected_at cannot precede research cutoff"
        )


def decision_view_matches_underwriting_tournament(
    view: DecisionViewSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    *,
    artifact_root: str | Path | None = None,
) -> bool:
    """Bind a Decision View to a genuine persisted forecast tournament identity."""

    tournament = underwriting.forecast_tournament
    snapshot_ids = tuple(tournament.forecast_snapshot_ids)
    forecast_ids = tuple(tournament.forecast_ids)
    if len(snapshot_ids) != len(forecast_ids) or len(snapshot_ids) < 2:
        return False
    if len(set(snapshot_ids)) != len(snapshot_ids):
        return False
    if len(set(forecast_ids)) != len(forecast_ids):
        return False
    if not (2 <= tournament.distinct_forecaster_count <= len(snapshot_ids)):
        return False
    if not (1 <= tournament.dependency_cluster_count <= len(snapshot_ids)):
        return False
    if tournament.primary_error_metric is None:
        return False
    if tournament.information_cutoff is None or tournament.forecast_origin is None:
        return False
    if tournament.target_date is None:
        return False
    if tournament.information_cutoff > tournament.forecast_origin:
        return False
    if tournament.forecast_origin.date() >= tournament.target_date:
        return False
    if tournament.information_cutoff > view.captured_at:
        return False
    if view.information_cutoff > view.forecast_origin:
        return False
    if view.information_cutoff > view.captured_at:
        return False
    if view.forecast_origin.date() >= view.target_date:
        return False
    selected_pair = (view.selected_forecast_snapshot_id, view.selected_forecast_id)
    tournament_pairs = tuple(zip(snapshot_ids, forecast_ids, strict=True))
    base_match = bool(
        tournament.comparable
        and not tournament.blockers
        and tournament.security_id == view.security_id
        and tournament.target_variable == view.target_variable
        and tournament.target_date == view.target_date
        and tournament.unit == view.unit
        and tournament.forecast_origin == view.forecast_origin
        and tournament.information_cutoff == view.information_cutoff
        and tuple(sorted(snapshot_ids))
        == tuple(sorted(view.tournament_forecast_snapshot_ids))
        and selected_pair in tournament_pairs
    )
    if not base_match:
        return False
    if artifact_root is None:
        return True
    return _persisted_tournament_registrations_match(
        Path(artifact_root),
        view=view,
        underwriting=underwriting,
        snapshot_ids=snapshot_ids,
        forecast_ids=forecast_ids,
    )


def _persisted_tournament_registrations_match(
    root: Path,
    *,
    view: DecisionViewSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    snapshot_ids: tuple[str, ...],
    forecast_ids: tuple[str, ...],
) -> bool:
    registrations = _load_persisted_forecast_registrations(root, snapshot_ids)
    if len(registrations) != len(snapshot_ids):
        return False
    descriptors: set[tuple[str, str]] = set()
    clusters: set[str] = set()
    tournament = underwriting.forecast_tournament
    for payload, expected_snapshot_id, expected_forecast_id in zip(
        registrations,
        snapshot_ids,
        forecast_ids,
        strict=True,
    ):
        if _sha(payload) != expected_snapshot_id:
            return False
        if payload.get("forecast_id") != expected_forecast_id:
            return False
        if payload.get("security_id") != view.security_id:
            return False
        if payload.get("target_variable") != view.target_variable:
            return False
        if payload.get("target_date") != view.target_date.isoformat():
            return False
        if payload.get("unit") != view.unit:
            return False
        if payload.get("primary_error_metric") != tournament.primary_error_metric:
            return False
        if payload.get("guardrail_evidence_id") != underwriting.guardrail_evidence_id:
            return False
        try:
            information_cutoff = _payload_datetime(payload, "information_cutoff")
            registered_at = _payload_datetime(payload, "registered_at")
            ledger_recorded_at = _payload_datetime(payload, "ledger_recorded_at")
            forecast_origin = _payload_datetime(payload, "forecast_origin")
            target_date = date.fromisoformat(str(payload.get("target_date")))
        except (TypeError, ValueError):
            return False
        if not (
            information_cutoff <= registered_at <= ledger_recorded_at
            and registered_at <= forecast_origin
            and information_cutoff == view.information_cutoff
            and forecast_origin == view.forecast_origin
            and target_date == view.target_date
            and forecast_origin.date() < target_date
            and ledger_recorded_at <= view.captured_at
        ):
            return False
        if (
            payload.get("registration_mode")
            == ForecastRegistrationMode.NATIVE_PROSPECTIVE.value
            and ledger_recorded_at > forecast_origin
        ):
            return False
        forecaster_kind = payload.get("forecaster_kind")
        model_family = payload.get("model_family")
        dependency_cluster = payload.get("dependency_cluster_id")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (forecaster_kind, model_family, dependency_cluster)
        ):
            return False
        descriptors.add((str(forecaster_kind), str(model_family)))
        clusters.add(str(dependency_cluster))

    if len(descriptors) < 2:
        return False
    if len(descriptors) != tournament.distinct_forecaster_count:
        return False
    if len(clusters) != tournament.dependency_cluster_count:
        return False
    dependency_overlap = len(clusters) < len(registrations)
    if view.tournament_dependency_overlap is not dependency_overlap:
        return False
    expected_tournament_flags = (
        ("forecast_dependency_overlap",) if dependency_overlap else ()
    )
    if tuple(tournament.flags) != expected_tournament_flags:
        return False

    try:
        selected_index = snapshot_ids.index(view.selected_forecast_snapshot_id)
    except ValueError:
        return False
    selected = registrations[selected_index]
    if selected.get("forecast_id") != view.selected_forecast_id:
        return False
    if selected.get("forecaster_kind") != view.selected_forecaster_kind.value:
        return False
    if selected.get("model_family") != view.selected_model_family:
        return False
    selected_value = selected.get("forecast_value")
    if not isinstance(selected_value, (int, float)) or isinstance(selected_value, bool):
        return False
    return _numbers_match(float(selected_value), view.selected_forecast_value)


def _load_persisted_forecast_registrations(
    root: Path,
    snapshot_ids: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    resolved_root = require_trusted_artifact_root(root)
    repository = root / "registration"
    _require_safe_repository(
        repository,
        resolved_root=resolved_root,
        label="forecast registration",
    )
    if not repository.exists():
        return ()
    loaded: list[dict[str, object]] = []
    for snapshot_id in snapshot_ids:
        matches = tuple(
            path
            for path in repository.iterdir()
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name.endswith(f"__{snapshot_id[:12]}")
        )
        if len(matches) != 1:
            return ()
        directory = matches[0]
        _require_safe_directory_slot(
            directory,
            repository,
            "forecast registration",
        )
        payload_path = directory / "forecast_registration.json"
        manifest_path = directory / "manifest.json"
        _require_safe_file_slot(
            payload_path,
            directory,
            "forecast registration payload",
        )
        _require_safe_file_slot(
            manifest_path,
            directory,
            "forecast registration manifest",
        )
        payload = _load_json_object(payload_path)
        manifest = _load_json_object(manifest_path)
        if _sha(payload) != snapshot_id:
            return ()
        try:
            ledger_recorded_at = _payload_datetime(payload, "ledger_recorded_at")
        except ValueError:
            return ()
        expected_directory = (
            ledger_recorded_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            + f"__{snapshot_id[:12]}"
        )
        if directory.name != expected_directory:
            return ()
        expected_manifest = {
            "schema_version": FORECAST_LEDGER_SCHEMA_VERSION,
            "object_type": "registration",
            "snapshot_id": snapshot_id,
            "captured_at": ledger_recorded_at.isoformat(),
            "immutable": True,
            "order_api_enabled": False,
            "files": ["forecast_registration.json"],
            "forecast_id": payload.get("forecast_id"),
            "registration_mode": payload.get("registration_mode"),
            "dependency_cluster_id": payload.get("dependency_cluster_id"),
            "guardrail_evidence_id": payload.get("guardrail_evidence_id"),
            "outcome_observed": False,
            "evaluation_run": False,
        }
        if manifest != expected_manifest:
            return ()
        loaded.append(payload)
    return tuple(loaded)


def _payload_datetime(payload: dict[str, object], field: str) -> datetime:
    raw = payload.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} must be non-empty text")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value


def package_integrity_blocker_codes(
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot | None,
    payoff: PayoffSurfaceSnapshot | None,
    view: DecisionViewSnapshot | None,
    gap: DecisionExpectationGapSnapshot | None,
) -> tuple[str, ...]:
    """Return deterministic fail-closed blockers for persisted-only builder bypasses."""

    blockers: list[str] = []
    if thesis.status in _TERMINAL_THESIS_STATUSES:
        blockers.append("terminal_thesis_status")
    if payoff is not None and payoff.captured_at < thesis.captured_at:
        blockers.append("thesis_payoff_capture_order_mismatch")
    if underwriting is not None and underwriting.captured_at < thesis.captured_at:
        blockers.append("thesis_underwriting_capture_order_mismatch")
    if underwriting is not None and not _underwriting_ready_contract_is_valid(
        thesis, underwriting, payoff
    ):
        blockers.append("underwriting_ready_evidence_contract_mismatch")
    if (
        underwriting is not None
        and payoff is not None
        and underwriting.payoff_surface_snapshot_id == payoff.snapshot_id
        and underwriting.captured_at < payoff.captured_at
    ):
        blockers.append("payoff_underwriting_capture_order_mismatch")
    if view is not None and gap is not None and not _gap_observations_match_view(view, gap):
        blockers.append("decision_gap_observation_binding_mismatch")
    return tuple(blockers)


def validate_publication_layout(
    root: Path,
    *,
    artifacts: ResearchRoundArtifacts,
    run: ResearchRoundRunSnapshot,
    ledger: ResearchRunLedgerSnapshot,
) -> None:
    """Reject symlink/path escapes and destructive deterministic-file collisions."""

    resolved_root = require_trusted_artifact_root(root)
    repositories: dict[str, Path] = {}
    for name in _PUBLICATION_REPOSITORIES:
        repository = root / name
        _require_safe_repository(repository, resolved_root=resolved_root, label=name)
        repositories[name] = repository

    candidate_root = repositories["opportunity_candidate"]
    set_root = repositories["opportunity_set"]
    for candidate in artifacts.opportunity_candidates:
        directory = _opportunity_snapshot_directory(
            root,
            object_name="opportunity_candidate",
            captured_at=candidate.captured_at,
            snapshot_id=candidate.snapshot_id,
        )
        _require_safe_directory_slot(directory, candidate_root, "opportunity candidate")
        _require_safe_temporary_slot(directory, candidate_root, "opportunity candidate")
    if artifacts.opportunity_set is not None:
        directory = _opportunity_snapshot_directory(
            root,
            object_name="opportunity_set",
            captured_at=artifacts.opportunity_set.captured_at,
            snapshot_id=artifacts.opportunity_set.snapshot_id,
        )
        _require_safe_directory_slot(directory, set_root, "opportunity set")
        _require_safe_temporary_slot(directory, set_root, "opportunity set")

    candidate_pointer = candidate_root / "latest_opportunity_candidate.json"
    set_pointer = set_root / "latest_opportunity_set.json"
    _require_safe_file_slot(candidate_pointer, candidate_root, "opportunity candidate pointer")
    _require_safe_file_slot(set_pointer, set_root, "opportunity set pointer")
    _require_safe_file_slot(
        candidate_pointer.with_name(f".{candidate_pointer.name}.rollback"),
        candidate_root,
        "opportunity candidate rollback pointer",
    )
    _require_safe_file_slot(
        set_pointer.with_name(f".{set_pointer.name}.rollback"),
        set_root,
        "opportunity set rollback pointer",
    )

    final_paths = (
        (
            repositories["research_round_v2_1"] / f"{artifacts.snapshot.snapshot_id}.json",
            repositories["research_round_v2_1"],
            "research round artifact",
        ),
        (
            repositories["research_round_run_v2_1"] / f"{run.snapshot_id}.json",
            repositories["research_round_run_v2_1"],
            "research run artifact",
        ),
        (
            repositories["research_run_ledger_v2_1"] / f"{ledger.snapshot_id}.json",
            repositories["research_run_ledger_v2_1"],
            "research ledger artifact",
        ),
    )
    for path, repository, label in final_paths:
        _require_safe_file_slot(path, repository, label)
        if path.exists():
            raise ResearchPackageIntegrityError(
                f"{label} already exists; refusing destructive publication collision"
            )


def validate_existing_opportunity_artifacts(
    root: Path,
    artifacts: ResearchRoundArtifacts,
) -> None:
    """Fully validate deterministic opportunity artifacts before writers may reuse them."""

    for candidate in artifacts.opportunity_candidates:
        directory = _opportunity_snapshot_directory(
            root,
            object_name="opportunity_candidate",
            captured_at=candidate.captured_at,
            snapshot_id=candidate.snapshot_id,
        )
        if directory.exists() or directory.is_symlink():
            validate_persisted_opportunity_candidate(root, candidate, require_pointer=False)
    if artifacts.opportunity_set is not None:
        directory = _opportunity_snapshot_directory(
            root,
            object_name="opportunity_set",
            captured_at=artifacts.opportunity_set.captured_at,
            snapshot_id=artifacts.opportunity_set.snapshot_id,
        )
        if directory.exists() or directory.is_symlink():
            validate_persisted_opportunity_set(
                root,
                artifacts.opportunity_set,
                require_pointer=False,
            )


def validate_persisted_opportunity_candidate(
    root: Path,
    snapshot: OpportunityCandidateSnapshot,
    *,
    require_pointer: bool,
) -> None:
    _validate_persisted_opportunity_snapshot(
        root,
        object_name="opportunity_candidate",
        snapshot=snapshot,
        require_pointer=require_pointer,
    )


def validate_persisted_opportunity_set(
    root: Path,
    snapshot: OpportunitySetSnapshot,
    *,
    require_pointer: bool,
) -> None:
    _validate_persisted_opportunity_snapshot(
        root,
        object_name="opportunity_set",
        snapshot=snapshot,
        require_pointer=require_pointer,
    )


def _underwriting_ready_contract_is_valid(
    thesis: InvestmentThesisSnapshot,
    underwriting: UnderwritingReadinessSnapshot,
    payoff: PayoffSurfaceSnapshot | None,
) -> bool:
    if underwriting.readiness not in _READY_UNDERWRITING_STATES:
        return True
    active = load_decision_system_v21_guardrails()
    if underwriting.lane is UnderwritingLane.FAST:
        if underwriting.readiness is not UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW:
            return False
        required = tuple(active.fast_lane_required_elements)
        return bool(
            tuple(underwriting.required_elements_satisfied) == required
            and not underwriting.required_elements_missing
            and not underwriting.blockers
        )
    if underwriting.lane is not UnderwritingLane.DEEP:
        return False
    required = tuple(active.deep_lane_required_elements) + SUPPLEMENTAL_DEEP_ELEMENTS
    if tuple(underwriting.required_elements_satisfied) != required:
        return False
    if underwriting.required_elements_missing or underwriting.blockers:
        return False
    if underwriting.flags:
        if underwriting.readiness is not UnderwritingReadiness.DEEP_LANE_READY_WITH_EPISTEMIC_FLAGS:
            return False
    elif underwriting.readiness is not UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW:
        return False
    required_snapshot_ids = (
        underwriting.causal_graph_snapshot_id,
        underwriting.expectation_state_snapshot_id,
        underwriting.forward_valuation_snapshot_id,
        underwriting.price_implied_requirement_snapshot_id,
        underwriting.payoff_surface_snapshot_id,
        underwriting.epistemic_defense_snapshot_id,
    )
    if any(value is None for value in required_snapshot_ids):
        return False
    if payoff is None or underwriting.payoff_surface_snapshot_id != payoff.snapshot_id:
        return False
    if not thesis.catalysts or not thesis.kill_conditions:
        return False
    if not thesis.opportunity_set_refs or not thesis.portfolio_overlap:
        return False
    if not underwriting.forecast_tournament.comparable:
        return False
    if not set(underwriting.forecast_tournament.flags).issubset(set(underwriting.flags)):
        return False
    return True


def _gap_observations_match_view(
    view: DecisionViewSnapshot,
    gap: DecisionExpectationGapSnapshot,
) -> bool:
    for consensus_observation in gap.consensus_gaps:
        if consensus_observation.observed_at > gap.captured_at:
            return False
        if consensus_observation.observed_at.astimezone(_KST).date() > gap.evaluation_date:
            return False
        if consensus_observation.unit != view.unit:
            return False
        if not _numbers_match(
            consensus_observation.decision_value,
            view.selected_forecast_value,
        ):
            return False
        expected_absolute = (
            consensus_observation.decision_value - consensus_observation.consensus_value
        )
        if not _numbers_match(consensus_observation.absolute_gap, expected_absolute):
            return False
        expected_relative = (
            None
            if consensus_observation.consensus_value == 0
            else expected_absolute / abs(consensus_observation.consensus_value)
        )
        if expected_relative is None:
            if consensus_observation.relative_gap is not None:
                return False
        elif consensus_observation.relative_gap is None or not _numbers_match(
            consensus_observation.relative_gap,
            expected_relative,
        ):
            return False

    if gap.price_implied_gaps:
        decision_value_krw = _to_krw(view.selected_forecast_value, view.unit)
        if decision_value_krw is None:
            return False
        for price_observation in gap.price_implied_gaps:
            if not _numbers_match(
                price_observation.decision_value_krw,
                decision_value_krw,
            ):
                return False
            expected_absolute = (
                price_observation.decision_value_krw - price_observation.implied_value_krw
            )
            if not _numbers_match(price_observation.absolute_gap_krw, expected_absolute):
                return False
            expected_relative = expected_absolute / price_observation.implied_value_krw
            if not _numbers_match(price_observation.relative_gap, expected_relative):
                return False
    return True


def _to_krw(value: float, unit: str) -> float | None:
    factors = {
        "KRW": 1.0,
        "KRW_thousand": 1_000.0,
        "KRW_million": 1_000_000.0,
        "KRW_billion": 1_000_000_000.0,
        "KRW_trillion": 1_000_000_000_000.0,
    }
    factor = factors.get(unit)
    if factor is None:
        return None
    result = float(value) * factor
    return result if math.isfinite(result) else None


def _numbers_match(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-9)


def _require_safe_repository(path: Path, *, resolved_root: Path, label: str) -> None:
    if path.is_symlink():
        raise ResearchPackageIntegrityError(f"{label} repository cannot be a symlink")
    if not path.exists():
        return
    if not path.is_dir():
        raise ResearchPackageIntegrityError(f"{label} repository must be a directory")
    if path.resolve().parent != resolved_root:
        raise ResearchPackageIntegrityError(f"{label} repository escapes artifact_root")


def _require_safe_directory_slot(path: Path, repository: Path, label: str) -> None:
    if path.is_symlink():
        raise ResearchPackageIntegrityError(f"{label} snapshot directory cannot be a symlink")
    if not path.exists():
        return
    if not path.is_dir():
        raise ResearchPackageIntegrityError(f"{label} snapshot path must be a directory")
    if path.resolve().parent != repository.resolve():
        raise ResearchPackageIntegrityError(f"{label} snapshot directory escapes repository")


def _require_safe_temporary_slot(path: Path, repository: Path, label: str) -> None:
    temporary = repository / f".{path.name}.tmp"
    if temporary.is_symlink():
        raise ResearchPackageIntegrityError(f"{label} temporary path cannot be a symlink")


def _require_safe_file_slot(path: Path, repository: Path, label: str) -> None:
    if path.is_symlink():
        raise ResearchPackageIntegrityError(f"{label} cannot be a symlink")
    if not path.exists():
        return
    if not path.is_file():
        raise ResearchPackageIntegrityError(f"{label} must be a regular file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ResearchPackageIntegrityError(f"cannot resolve {label}") from exc
    if resolved.parent != repository.resolve():
        raise ResearchPackageIntegrityError(f"{label} escapes repository")


def _validate_persisted_opportunity_snapshot(
    root: Path,
    *,
    object_name: str,
    snapshot: OpportunityCandidateSnapshot | OpportunitySetSnapshot,
    require_pointer: bool,
) -> None:
    repository = root / object_name
    resolved_root = require_trusted_artifact_root(root)
    _require_safe_repository(repository, resolved_root=resolved_root, label=object_name)
    directory = _opportunity_snapshot_directory(
        root,
        object_name=object_name,
        captured_at=snapshot.captured_at,
        snapshot_id=snapshot.snapshot_id,
    )
    _require_safe_directory_slot(directory, repository, object_name)
    if not directory.exists():
        raise ResearchPackageIntegrityError(f"missing persisted {object_name} snapshot")

    payload_path = directory / f"{object_name}.json"
    manifest_path = directory / "manifest.json"
    _require_safe_file_slot(payload_path, directory, f"{object_name} payload")
    _require_safe_file_slot(manifest_path, directory, f"{object_name} manifest")
    payload = _load_json_object(payload_path)
    manifest = _load_json_object(manifest_path)
    expected_payload = snapshot.payload_without_id()
    if payload != expected_payload:
        raise ResearchPackageIntegrityError(
            f"persisted {object_name} payload disagrees with generated snapshot"
        )
    if _sha(payload) != snapshot.snapshot_id:
        raise ResearchPackageIntegrityError(
            f"persisted {object_name} payload content address mismatch"
        )
    expected_manifest = _expected_opportunity_manifest(object_name, snapshot)
    if manifest != expected_manifest:
        raise ResearchPackageIntegrityError(
            f"persisted {object_name} manifest is not canonical"
        )

    if require_pointer:
        pointer = repository / f"latest_{object_name}.json"
        _require_safe_file_slot(pointer, repository, f"{object_name} pointer")
        pointer_payload = _load_json_object(pointer)
        if set(pointer_payload) != {
            "schema_version",
            "object_type",
            "snapshot_id",
            "snapshot_path",
        }:
            raise ResearchPackageIntegrityError(
                f"persisted {object_name} pointer fields are not canonical"
            )
        if pointer_payload.get("schema_version") != OPPORTUNITY_SET_SCHEMA_VERSION:
            raise ResearchPackageIntegrityError(
                f"persisted {object_name} pointer schema mismatch"
            )
        if pointer_payload.get("object_type") != object_name:
            raise ResearchPackageIntegrityError(
                f"persisted {object_name} pointer object type mismatch"
            )
        if pointer_payload.get("snapshot_id") != snapshot.snapshot_id:
            raise ResearchPackageIntegrityError(
                f"persisted {object_name} pointer snapshot mismatch"
            )
        raw_target = pointer_payload.get("snapshot_path")
        if not isinstance(raw_target, str) or not raw_target.strip():
            raise ResearchPackageIntegrityError(
                f"persisted {object_name} pointer path must be non-empty text"
            )
        pointer_target = Path(raw_target)
        resolved_target = (
            pointer_target.resolve()
            if pointer_target.is_absolute()
            else (repository.resolve() / pointer_target.name).resolve()
        )
        if resolved_target != directory.resolve():
            raise ResearchPackageIntegrityError(
                f"persisted {object_name} pointer path mismatch"
            )


def _expected_opportunity_manifest(
    object_name: str,
    snapshot: OpportunityCandidateSnapshot | OpportunitySetSnapshot,
) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
        "object_type": object_name,
        "snapshot_id": snapshot.snapshot_id,
        "captured_at": snapshot.captured_at.isoformat(),
        "immutable": True,
        "files": [f"{object_name}.json"],
    }
    if isinstance(snapshot, OpportunityCandidateSnapshot):
        base.update(
            {
                "security_id": snapshot.security_id,
                "research_class": snapshot.research_class.value,
                "capital_allocation_comparable": snapshot.capital_allocation_comparable,
            }
        )
        return base
    base.update(
        {
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "horizon_trading_days": snapshot.horizon_trading_days,
            "candidate_count": len(snapshot.candidates),
            "comparable_candidate_count": len(snapshot.comparable_security_ids),
            "pareto_frontier_security_ids": list(snapshot.pareto_frontier_security_ids),
            "unique_pareto_leader_security_id": snapshot.unique_pareto_leader_security_id,
            "capital_allocation_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }
    )
    return base


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchPackageIntegrityError(f"cannot read persisted JSON: {path}") from exc
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise ResearchPackageIntegrityError(f"persisted JSON object required: {path}")
    return cast(dict[str, object], raw)


def _opportunity_snapshot_directory(
    root: Path,
    *,
    object_name: str,
    captured_at: datetime,
    snapshot_id: str,
) -> Path:
    from datetime import UTC

    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return root / object_name / f"{timestamp}__{snapshot_id[:12]}"


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
    "ResearchPackageIntegrityError",
    "decision_view_matches_underwriting_tournament",
    "package_integrity_blocker_codes",
    "require_trusted_artifact_root",
    "validate_existing_opportunity_artifacts",
    "validate_persisted_opportunity_candidate",
    "validate_persisted_opportunity_set",
    "validate_preflight_selection_timing",
    "validate_publication_layout",
    "validate_thesis_repository_layout",
]
