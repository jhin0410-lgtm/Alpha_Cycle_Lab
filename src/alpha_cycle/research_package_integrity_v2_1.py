"""Integrity helpers for persisted Decision System v2.1 research-package assembly."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.decision_thesis_v2 import (
    InvestmentThesisSnapshot,
    ThesisStatus,
)
from alpha_cycle.intelligence.decision_view_v2_1 import (
    DecisionExpectationGapSnapshot,
    DecisionViewSnapshot,
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
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingReadinessSnapshot
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
    if root.exists() and lexical != resolved:
        raise ResearchPackageIntegrityError(
            "artifact_root cannot traverse a symlinked path component"
        )
    return resolved


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
) -> bool:
    """Bind a Decision View to the exact parallel forecast identity in the tournament."""

    tournament = underwriting.forecast_tournament
    snapshot_ids = tuple(tournament.forecast_snapshot_ids)
    forecast_ids = tuple(tournament.forecast_ids)
    if len(snapshot_ids) != len(forecast_ids):
        return False
    selected_pair = (view.selected_forecast_snapshot_id, view.selected_forecast_id)
    tournament_pairs = tuple(zip(snapshot_ids, forecast_ids, strict=True))
    return bool(
        tournament.comparable
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
    """Reject symlink/path escapes for every repository touched by assembler publication."""

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


def _gap_observations_match_view(
    view: DecisionViewSnapshot,
    gap: DecisionExpectationGapSnapshot,
) -> bool:
    for observation in gap.consensus_gaps:
        if observation.observed_at > gap.captured_at:
            return False
        if observation.unit != view.unit:
            return False
        if not _numbers_match(observation.decision_value, view.selected_forecast_value):
            return False
        expected_absolute = observation.decision_value - observation.consensus_value
        if not _numbers_match(observation.absolute_gap, expected_absolute):
            return False
        expected_relative = (
            None
            if observation.consensus_value == 0
            else expected_absolute / abs(observation.consensus_value)
        )
        if expected_relative is None:
            if observation.relative_gap is not None:
                return False
        elif observation.relative_gap is None or not _numbers_match(
            observation.relative_gap,
            expected_relative,
        ):
            return False

    if gap.price_implied_gaps:
        decision_value_krw = _to_krw(view.selected_forecast_value, view.unit)
        if decision_value_krw is None:
            return False
        for observation in gap.price_implied_gaps:
            if not _numbers_match(observation.decision_value_krw, decision_value_krw):
                return False
            expected_absolute = observation.decision_value_krw - observation.implied_value_krw
            if not _numbers_match(observation.absolute_gap_krw, expected_absolute):
                return False
            expected_relative = expected_absolute / observation.implied_value_krw
            if not _numbers_match(observation.relative_gap, expected_relative):
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
