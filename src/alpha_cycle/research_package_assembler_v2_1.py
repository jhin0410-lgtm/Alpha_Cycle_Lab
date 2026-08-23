"""Fail-closed persisted research-package assembly for Decision System v2.1.

This module does not create research evidence. It reconstructs already-persisted typed objects,
checks their PIT/request bindings, and delegates research logic to the existing
`run_research_round` orchestrator only after a complete package exists.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    persist_opportunity_candidate,
    persist_opportunity_set,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundArtifacts,
    ResearchRoundBlocker,
    ResearchSecurityPackage,
    persist_research_round,
    run_research_round,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    AnalysisRequestSnapshot,
    ResearchRoundRunSnapshot,
    ResearchRunKind,
    ResearchRunLedgerSnapshot,
    bind_orchestrated_run,
    build_pre_orchestration_blocked_run,
    build_research_run_ledger,
    persist_research_run,
    persist_research_run_ledger,
)
from alpha_cycle.investment_thesis_repository_v2_1 import (
    InvestmentThesisRepositoryError,
    build_investment_thesis_repository_index,
)
from alpha_cycle.research_component_repository_v2_1 import (
    ResearchComponentRepositoryError,
    ResearchComponentRepositoryIndex,
    build_research_component_repository_index,
)
from alpha_cycle.research_ledger_write_lock_v2_1 import (
    exclusive_research_ledger_write_lock,
)
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_package_integrity_v2_1 import (
    decision_view_matches_underwriting_tournament,
    package_integrity_blocker_codes,
    require_trusted_artifact_root,
    validate_existing_opportunity_artifacts,
    validate_persisted_opportunity_candidate,
    validate_persisted_opportunity_set,
    validate_preflight_selection_timing,
    validate_publication_layout,
    validate_thesis_repository_layout,
)
from alpha_cycle.research_preflight_state_v2_1 import (
    CurrentResearchThesisPreflightState,
    ResearchPreflightStateError,
    ResearchThesisPreflightStateSnapshot,
    load_current_research_thesis_preflight_states,
    validate_preflight_state_request_binding,
)


@dataclass(frozen=True)
class ResearchPackageAssemblyReceipt:
    request: AnalysisRequestSnapshot
    thesis_preflight: ResearchThesisPreflightStateSnapshot
    packages: tuple[ResearchSecurityPackage, ...]
    blockers: tuple[ResearchRoundBlocker, ...]
    orchestrated: ResearchRoundArtifacts | None
    run: ResearchRoundRunSnapshot | None
    ledger: ResearchRunLedgerSnapshot
    research_round_path: Path | None
    run_path: Path | None
    ledger_path: Path | None
    changed_history: bool

    @property
    def full_package_ready(self) -> bool:
        return not self.blockers and len(self.packages) == len(self.request.security_ids)

    def payload(self) -> dict[str, object]:
        return {
            "request_id": self.request.request_id,
            "request_snapshot_id": self.request.snapshot_id,
            "research_cutoff_at": self.thesis_preflight.research_cutoff_at.isoformat(),
            "package_security_ids": [item.security_id for item in self.packages],
            "blockers": [item.payload() for item in self.blockers],
            "full_package_ready": self.full_package_ready,
            "orchestrator_executed": self.orchestrated is not None,
            "research_round_snapshot_id": (
                self.orchestrated.snapshot.snapshot_id
                if self.orchestrated is not None
                else None
            ),
            "run_snapshot_id": self.run.snapshot_id if self.run is not None else None,
            "ledger_snapshot_id": self.ledger.snapshot_id,
            "research_round_path": (
                str(self.research_round_path)
                if self.research_round_path is not None
                else None
            ),
            "run_path": str(self.run_path) if self.run_path is not None else None,
            "ledger_path": (
                str(self.ledger_path) if self.ledger_path is not None else None
            ),
            "changed_history": self.changed_history,
            "investment_conclusion_created": False,
            "target_price_enabled": False,
            "optimal_position_size_enabled": False,
            "portfolio_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }


def assemble_and_run_research_package(
    *,
    request_id: str,
    round_id: str,
    run_id: str,
    processed_at: datetime,
    artifact_root: str | Path,
) -> ResearchPackageAssemblyReceipt:
    """Assemble one complete persisted package per request security and run if complete."""

    _require_aware(processed_at, "processed_at")
    root = Path(artifact_root)
    require_trusted_artifact_root(root)
    with exclusive_research_ledger_write_lock(root):
        observatory = load_latest_observatory_state(root)
        if observatory is None:
            raise ValueError(
                "no Research Run Ledger exists; record an analysis request first"
            )
        ledger = observatory.ledger
        request = _find_request(ledger, request_id)
        _require_canonical_request_security_ids(request)
        if processed_at <= ledger.built_at:
            raise ValueError("processed_at must be later than the latest ledger built_at")
        if processed_at < request.requested_at:
            raise ValueError("processed_at cannot precede the analysis request")
        if any(item.run_id == run_id for item in ledger.runs):
            raise ValueError(f"run_id already exists in the latest ledger: {run_id}")
        if any(
            item.request_snapshot_id == request.snapshot_id
            and item.kind is ResearchRunKind.ORCHESTRATED
            for item in ledger.runs
        ):
            raise ValueError("analysis request already has an orchestrated run")

        current_preflight = _current_ready_preflight(
            root,
            request,
            processed_at=processed_at,
        )
        preflight = current_preflight.state
        cutoff = preflight.research_cutoff_at
        if cutoff > processed_at:
            raise ValueError(
                "current thesis preflight cutoff cannot be after processing time"
            )
        active = load_decision_system_v21_guardrails()
        if request.guardrail_evidence_id != active.evidence_id:
            raise ValueError("analysis request guardrail evidence is no longer active")

        try:
            validate_thesis_repository_layout(root)
            thesis_index = build_investment_thesis_repository_index(
                root,
                as_of=cutoff,
            )
            component_index = build_research_component_repository_index(
                root,
                as_of=cutoff,
            )
        except (
            InvestmentThesisRepositoryError,
            ResearchComponentRepositoryError,
        ) as exc:
            raise ValueError(
                "persisted research-package repository failed validation"
            ) from exc

        packages: list[ResearchSecurityPackage] = []
        blockers: list[ResearchRoundBlocker] = []
        resolved_thesis_ids: list[str] = []
        for security_id in request.security_ids:
            thesis = thesis_index.find_latest(
                security_id=security_id,
                horizon_trading_days=request.horizon_trading_days,
            )
            if thesis is None:
                _block(
                    blockers,
                    "thesis",
                    "investment_thesis_snapshot_missing",
                    security_id,
                )
                continue
            resolved_thesis_ids.append(thesis.snapshot_id)
            package = _assemble_security_package(
                security_id,
                thesis=thesis,
                request=request,
                component_index=component_index,
                guardrail_evidence_id=active.evidence_id,
                artifact_root=root,
                blockers=blockers,
            )
            if package is not None:
                packages.append(package)

        if tuple(resolved_thesis_ids) != preflight.thesis_snapshot_ids:
            raise ValueError(
                "current thesis preflight no longer matches PIT-selected thesis snapshots"
            )
        if len(request.security_ids) < 2:
            _block(
                blockers,
                "research_package",
                "cross_sectional_package_requires_two_securities",
                None,
            )

        blockers_tuple = tuple(blockers)
        packages_tuple = tuple(packages)
        if blockers_tuple:
            next_ledger, run_path, ledger_path, changed = _record_package_blockers(
                request=request,
                run_id=run_id,
                processed_at=processed_at,
                preflight_selected_at=current_preflight.selected_at,
                blockers=blockers_tuple,
                ledger=ledger,
                root=root,
            )
            recorded_run = (
                next_ledger.runs[-1]
                if changed
                else _matching_package_blocked_run(
                    ledger,
                    request.snapshot_id,
                    blockers_tuple,
                )
            )
            return ResearchPackageAssemblyReceipt(
                request=request,
                thesis_preflight=preflight,
                packages=packages_tuple,
                blockers=blockers_tuple,
                orchestrated=None,
                run=recorded_run,
                ledger=next_ledger,
                research_round_path=None,
                run_path=run_path,
                ledger_path=ledger_path,
                changed_history=changed,
            )

        if len(packages_tuple) != len(request.security_ids):
            raise ValueError("package coverage mismatch without structured blockers")
        artifacts = run_research_round(
            packages_tuple,
            round_id=round_id,
            mode=request.mode,
            captured_at=cutoff,
            evaluation_date=request.evaluation_date,
            horizon_trading_days=request.horizon_trading_days,
            guardrails=active,
        )
        _validate_downstream_artifact_bindings(artifacts)
        run = bind_orchestrated_run(
            request,
            artifacts.snapshot,
            run_id=run_id,
            started_at=processed_at,
            completed_at=processed_at,
        )
        next_ledger = build_research_run_ledger(
            ledger.requests,
            (*ledger.runs, run),
            built_at=processed_at,
        )
        round_path, run_path, ledger_path = _publish_orchestrated_artifacts(
            artifacts=artifacts,
            run=run,
            ledger=next_ledger,
            root=root,
        )
        return ResearchPackageAssemblyReceipt(
            request=request,
            thesis_preflight=preflight,
            packages=packages_tuple,
            blockers=(),
            orchestrated=artifacts,
            run=run,
            ledger=next_ledger,
            research_round_path=round_path,
            run_path=run_path,
            ledger_path=ledger_path,
            changed_history=True,
        )


def _assemble_security_package(
    security_id: str,
    *,
    thesis: InvestmentThesisSnapshot,
    request: AnalysisRequestSnapshot,
    component_index: ResearchComponentRepositoryIndex,
    guardrail_evidence_id: str,
    artifact_root: Path | None = None,
    blockers: list[ResearchRoundBlocker],
) -> ResearchSecurityPackage | None:
    underwriting = component_index.latest_underwriting(
        security_id,
        thesis_snapshot_id=thesis.snapshot_id,
        evaluation_date=request.evaluation_date,
        lane=request.requested_lane,
        guardrail_evidence_id=guardrail_evidence_id,
    )
    if underwriting is None:
        _block(
            blockers,
            "underwriter",
            "underwriting_snapshot_missing_or_incompatible",
            security_id,
        )
    payoff = component_index.latest_payoff(
        security_id,
        thesis_snapshot_id=thesis.snapshot_id,
        horizon_trading_days=request.horizon_trading_days,
        guardrail_evidence_id=guardrail_evidence_id,
    )
    if payoff is None:
        _block(
            blockers,
            "payoff_surface",
            "payoff_surface_missing_or_incompatible",
            security_id,
        )
    view = component_index.latest_decision_view(
        security_id,
        evaluation_date=request.evaluation_date,
        guardrail_evidence_id=guardrail_evidence_id,
    )
    if view is None:
        _block(
            blockers,
            "decision_view",
            "decision_view_missing_or_incompatible",
            security_id,
        )
    gap = None
    if view is not None:
        gap = component_index.latest_expectation_gap(
            security_id,
            decision_view_snapshot_id=view.snapshot_id,
            evaluation_date=request.evaluation_date,
            guardrail_evidence_id=guardrail_evidence_id,
        )
    if gap is None:
        _block(
            blockers,
            "expectation_gap",
            "expectation_gap_missing_or_incompatible",
            security_id,
        )

    for code in package_integrity_blocker_codes(thesis, underwriting, payoff, view, gap):
        _block(blockers, "research_package", code, security_id)

    if underwriting is not None and payoff is not None:
        if (
            underwriting.payoff_surface_snapshot_id is not None
            and underwriting.payoff_surface_snapshot_id != payoff.snapshot_id
        ):
            _block(
                blockers,
                "research_package",
                "underwriting_payoff_binding_mismatch",
                security_id,
            )
    if underwriting is not None and view is not None:
        if not decision_view_matches_underwriting_tournament(
            view, underwriting, artifact_root=artifact_root
        ):
            _block(
                blockers,
                "research_package",
                "underwriting_decision_view_tournament_binding_mismatch",
                security_id,
            )
    if underwriting is not None and gap is not None:
        if (
            underwriting.expectation_state_snapshot_id is not None
            and underwriting.expectation_state_snapshot_id
            != gap.expectation_state_snapshot_id
        ):
            _block(
                blockers,
                "research_package",
                "underwriting_expectation_binding_mismatch",
                security_id,
            )
        if (
            underwriting.price_implied_requirement_snapshot_id is not None
            and underwriting.price_implied_requirement_snapshot_id
            != gap.price_implied_requirement_snapshot_id
        ):
            _block(
                blockers,
                "research_package",
                "underwriting_price_implied_binding_mismatch",
                security_id,
            )
    if view is not None and gap is not None:
        if gap.captured_at < view.captured_at:
            _block(
                blockers,
                "research_package",
                "decision_gap_capture_order_mismatch",
                security_id,
            )
        if (
            gap.target_variable != view.target_variable
            or gap.target_date != view.target_date
            or gap.unit != view.unit
        ):
            _block(
                blockers,
                "research_package",
                "decision_gap_target_binding_mismatch",
                security_id,
            )

    if any(item.security_id == security_id for item in blockers):
        return None
    if underwriting is None or payoff is None or view is None or gap is None:
        return None
    return ResearchSecurityPackage(
        thesis=thesis,
        underwriting=underwriting,
        payoff_surface=payoff,
        decision_view=view,
        expectation_gap=gap,
    )


def _current_ready_preflight(
    root: Path,
    request: AnalysisRequestSnapshot,
    *,
    processed_at: datetime,
) -> CurrentResearchThesisPreflightState:
    try:
        current = load_current_research_thesis_preflight_states(root).get(
            request.snapshot_id
        )
    except ResearchPreflightStateError as exc:
        raise ValueError(
            "current thesis preflight state failed validation"
        ) from exc
    if current is None:
        raise ValueError(
            "analysis request has no current typed-thesis preflight state"
        )
    validate_preflight_selection_timing(current, processed_at=processed_at)
    try:
        validate_preflight_state_request_binding(current.state, request)
    except ResearchPreflightStateError as exc:
        raise ValueError(
            "current thesis preflight does not bind to analysis request"
        ) from exc
    if not current.state.ready_for_package_assembly:
        raise ValueError("typed-thesis preflight is not ready for package assembly")
    return current


def _record_package_blockers(
    *,
    request: AnalysisRequestSnapshot,
    run_id: str,
    processed_at: datetime,
    preflight_selected_at: datetime,
    blockers: tuple[ResearchRoundBlocker, ...],
    ledger: ResearchRunLedgerSnapshot,
    root: Path,
) -> tuple[ResearchRunLedgerSnapshot, Path | None, Path | None, bool]:
    prior = _matching_package_blocked_run(
        ledger,
        request.snapshot_id,
        blockers,
    )
    latest_request_run = _latest_request_run(ledger, request.snapshot_id)
    if (
        prior is not None
        and latest_request_run == prior
        and prior.completed_at >= preflight_selected_at
    ):
        return ledger, None, None, False
    run = build_pre_orchestration_blocked_run(
        request,
        run_id=run_id,
        started_at=processed_at,
        completed_at=processed_at,
        blockers=blockers,
        flags=("typed_research_package_assembler_blocked",),
    )
    next_ledger = build_research_run_ledger(
        ledger.requests,
        (*ledger.runs, run),
        built_at=processed_at,
    )
    _require_safe_run_ledger_publication(root, run=run, ledger=next_ledger)
    run_path = persist_research_run(run, output_root=root)
    try:
        ledger_path = persist_research_run_ledger(
            next_ledger,
            output_root=root,
        )
    except BaseException:
        run_path.unlink(missing_ok=True)
        raise
    return next_ledger, run_path, ledger_path, True


def _matching_package_blocked_run(
    ledger: ResearchRunLedgerSnapshot,
    request_snapshot_id: str,
    blockers: tuple[ResearchRoundBlocker, ...],
) -> ResearchRoundRunSnapshot | None:
    matching = tuple(
        item
        for item in ledger.runs
        if item.request_snapshot_id == request_snapshot_id
        and item.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
        and item.flags == ("typed_research_package_assembler_blocked",)
        and item.blockers == blockers
    )
    return matching[-1] if matching else None


def _latest_request_run(
    ledger: ResearchRunLedgerSnapshot,
    request_snapshot_id: str,
) -> ResearchRoundRunSnapshot | None:
    matching = tuple(
        item
        for item in ledger.runs
        if item.request_snapshot_id == request_snapshot_id
    )
    return matching[-1] if matching else None


def _validate_downstream_artifact_bindings(artifacts: ResearchRoundArtifacts) -> None:
    candidate_ids = tuple(item.snapshot_id for item in artifacts.opportunity_candidates)
    if candidate_ids != artifacts.snapshot.opportunity_candidate_snapshot_ids:
        raise ValueError("research round opportunity-candidate bindings are inconsistent")
    set_id = (
        artifacts.opportunity_set.snapshot_id
        if artifacts.opportunity_set is not None
        else None
    )
    if set_id != artifacts.snapshot.opportunity_set_snapshot_id:
        raise ValueError("research round opportunity-set binding is inconsistent")
    if (
        artifacts.expectation_overlay is not None
        or artifacts.snapshot.expectation_overlay_snapshot_id is not None
    ):
        raise ValueError(
            "typed research package assembler does not publish expectation overlays"
        )
    if (
        artifacts.prospective_registration is not None
        or artifacts.snapshot.prospective_registration_snapshot_id is not None
    ):
        raise ValueError(
            "typed research package assembler does not publish prospective registrations"
        )


def _publish_orchestrated_artifacts(
    *,
    artifacts: ResearchRoundArtifacts,
    run: ResearchRoundRunSnapshot,
    ledger: ResearchRunLedgerSnapshot,
    root: Path,
) -> tuple[Path, Path, Path]:
    validate_publication_layout(root, artifacts=artifacts, run=run, ledger=ledger)
    validate_existing_opportunity_artifacts(root, artifacts)

    candidate_root = root / "opportunity_candidate"
    candidate_pointer = candidate_root / "latest_opportunity_candidate.json"
    candidate_root_existed = candidate_root.exists()
    candidate_pointer_before = _optional_bytes(candidate_pointer)
    candidate_new_directories = tuple(
        directory
        for item in artifacts.opportunity_candidates
        if not (
            directory := _opportunity_snapshot_directory(
                root,
                object_name="opportunity_candidate",
                captured_at=item.captured_at,
                snapshot_id=item.snapshot_id,
            )
        ).exists()
    )

    set_root = root / "opportunity_set"
    set_pointer = set_root / "latest_opportunity_set.json"
    set_root_existed = set_root.exists()
    set_pointer_before = _optional_bytes(set_pointer)
    set_new_directories: tuple[Path, ...] = ()
    if artifacts.opportunity_set is not None:
        directory = _opportunity_snapshot_directory(
            root,
            object_name="opportunity_set",
            captured_at=artifacts.opportunity_set.captured_at,
            snapshot_id=artifacts.opportunity_set.snapshot_id,
        )
        if not directory.exists():
            set_new_directories = (directory,)

    round_path: Path | None = None
    run_path: Path | None = None
    try:
        for candidate in artifacts.opportunity_candidates:
            persist_opportunity_candidate(candidate, output_root=root)
            validate_persisted_opportunity_candidate(
                root,
                candidate,
                require_pointer=True,
            )
        if artifacts.opportunity_set is not None:
            persist_opportunity_set(artifacts.opportunity_set, output_root=root)
            validate_persisted_opportunity_set(
                root,
                artifacts.opportunity_set,
                require_pointer=True,
            )
        round_path = persist_research_round(artifacts.snapshot, output_root=root)
        run_path = persist_research_run(run, output_root=root)
        ledger_path = persist_research_run_ledger(ledger, output_root=root)
        return round_path, run_path, ledger_path
    except BaseException as exc:
        cleanup_errors: list[BaseException] = []
        for path in (run_path, round_path):
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except BaseException as cleanup_exc:
                cleanup_errors.append(cleanup_exc)
        _rollback_opportunity_repository(
            root=candidate_root,
            pointer=candidate_pointer,
            pointer_before=candidate_pointer_before,
            root_existed=candidate_root_existed,
            new_directories=candidate_new_directories,
            cleanup_errors=cleanup_errors,
        )
        _rollback_opportunity_repository(
            root=set_root,
            pointer=set_pointer,
            pointer_before=set_pointer_before,
            root_existed=set_root_existed,
            new_directories=set_new_directories,
            cleanup_errors=cleanup_errors,
        )
        if cleanup_errors:
            raise RuntimeError(
                "orchestrated research publication failed and rollback was incomplete"
            ) from cleanup_errors[0]
        raise exc


def _rollback_opportunity_repository(
    *,
    root: Path,
    pointer: Path,
    pointer_before: bytes | None,
    root_existed: bool,
    new_directories: tuple[Path, ...],
    cleanup_errors: list[BaseException],
) -> None:
    for directory in reversed(new_directories):
        try:
            if directory.is_symlink():
                cleanup_errors.append(
                    RuntimeError(f"rollback refused symlinked snapshot directory: {directory}")
                )
                continue
            if directory.exists():
                shutil.rmtree(directory)
        except BaseException as exc:
            cleanup_errors.append(exc)
    try:
        if pointer_before is None:
            pointer.unlink(missing_ok=True)
        else:
            if pointer.is_symlink():
                pointer.unlink(missing_ok=True)
            pointer.parent.mkdir(parents=True, exist_ok=True)
            temporary = pointer.with_name(f".{pointer.name}.rollback")
            if temporary.is_symlink() or temporary.exists():
                temporary.unlink(missing_ok=True)
            temporary.write_bytes(pointer_before)
            temporary.replace(pointer)
    except BaseException as exc:
        cleanup_errors.append(exc)
    if not root_existed:
        try:
            root.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            if root.exists() and not any(root.iterdir()):
                cleanup_errors.append(
                    RuntimeError(f"failed to remove empty rollback directory: {root}")
                )


def _require_safe_run_ledger_publication(
    root: Path,
    *,
    run: ResearchRoundRunSnapshot,
    ledger: ResearchRunLedgerSnapshot,
) -> None:
    resolved_root = require_trusted_artifact_root(root)
    for directory_name, snapshot_id, label in (
        ("research_round_run_v2_1", run.snapshot_id, "research run"),
        ("research_run_ledger_v2_1", ledger.snapshot_id, "research ledger"),
    ):
        repository = root / directory_name
        if repository.is_symlink():
            raise ValueError(f"{label} repository cannot be a symlink")
        if repository.exists():
            if not repository.is_dir() or repository.resolve().parent != resolved_root:
                raise ValueError(f"{label} repository escapes artifact_root")
        path = repository / f"{snapshot_id}.json"
        if path.is_symlink():
            raise ValueError(f"{label} artifact cannot be a symlink")


def _opportunity_snapshot_directory(
    root: Path,
    *,
    object_name: str,
    captured_at: datetime,
    snapshot_id: str,
) -> Path:
    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return root / object_name / f"{timestamp}__{snapshot_id[:12]}"


def _optional_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError(f"cannot read symlinked publication pointer: {path}")
    return path.read_bytes() if path.exists() else None


def _require_canonical_request_security_ids(request: AnalysisRequestSnapshot) -> None:
    canonical = tuple(item.strip() for item in request.security_ids)
    if canonical != request.security_ids:
        raise ValueError(
            "analysis request contains legacy non-canonical security ids; re-record request"
        )


def _find_request(
    ledger: ResearchRunLedgerSnapshot,
    request_id: str,
) -> AnalysisRequestSnapshot:
    matches = tuple(item for item in ledger.requests if item.request_id == request_id)
    if len(matches) != 1:
        raise ValueError(
            f"request_id must resolve exactly once in latest ledger: {request_id}"
        )
    return matches[0]


def _block(
    blockers: list[ResearchRoundBlocker],
    component: str,
    code: str,
    security_id: str | None,
) -> None:
    value = ResearchRoundBlocker(
        component=component,
        code=code,
        detail=code.replace("_", " "),
        security_id=security_id,
    )
    if value not in blockers:
        blockers.append(value)


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


__all__ = ["ResearchPackageAssemblyReceipt", "assemble_and_run_research_package"]
