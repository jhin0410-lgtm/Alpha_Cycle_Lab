"""Fail-closed persisted research-package assembly for Decision System v2.1.

This module does not create research evidence. It reconstructs already-persisted typed objects,
checks their PIT/request bindings, and delegates research logic to the existing
`run_research_round` orchestrator only after a complete package exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OPPORTUNITY_SET_SCHEMA_VERSION,
    OpportunityCandidateSnapshot,
    OpportunitySetSnapshot,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundArtifacts,
    ResearchRoundBlocker,
    ResearchSecurityPackage,
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
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.investment_thesis_repository_v2_1 import (
    InvestmentThesisRepositoryError,
    InvestmentThesisRepositoryIndex,
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
from alpha_cycle.research_package_canonical_evidence_v2_1 import (
    decision_gap_bound_sources_are_canonical,
    underwriting_bound_evidence_is_valid,
)
from alpha_cycle.research_package_integrity_v2_1 import (
    ResearchPackageIntegrityError,
    decision_view_has_valid_persisted_selection,
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
from alpha_cycle.research_package_source_revalidation_v2_1 import (
    ResearchPackageSourceRevalidationError,
)
from alpha_cycle.research_preflight_state_v2_1 import (
    CurrentResearchThesisPreflightState,
    ResearchPreflightStateError,
    ResearchThesisPreflightStateSnapshot,
    load_current_research_thesis_preflight_states,
    validate_preflight_state_request_binding,
)


@dataclass(frozen=True)
class _OwnedOpportunityPublication:
    root: Path
    directory: Path
    directory_created: bool
    root_created: bool
    pointer: Path
    pointer_before: bytes | None
    pointer_after: bytes
    pointer_inode: int
    pointer_mtime_ns: int
    pointer_size: int
    repository_fd: int | None = None


@dataclass(frozen=True)
class _OwnedFilePublication:
    path: Path
    inode: int
    mtime_ns: int
    size: int
    sha256: str
    repository_fd: int | None = None
    file_name: str | None = None


@dataclass
class _PinnedRepository:
    public_path: Path
    io_path: Path
    fd: int | None
    device: int
    inode: int


@dataclass
class _PinnedPublicationRoot:
    public_root: Path
    io_root: Path
    fd: int | None
    device: int
    inode: int
    repositories: list[_PinnedRepository]


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
                self.orchestrated.snapshot.snapshot_id if self.orchestrated is not None else None
            ),
            "run_snapshot_id": self.run.snapshot_id if self.run is not None else None,
            "ledger_snapshot_id": self.ledger.snapshot_id,
            "research_round_path": (
                str(self.research_round_path) if self.research_round_path is not None else None
            ),
            "run_path": str(self.run_path) if self.run_path is not None else None,
            "ledger_path": (str(self.ledger_path) if self.ledger_path is not None else None),
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
            raise ValueError("no Research Run Ledger exists; record an analysis request first")
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
            raise ValueError("current thesis preflight cutoff cannot be after processing time")
        active = load_decision_system_v21_guardrails()
        if request.guardrail_evidence_id != active.evidence_id:
            raise ValueError("analysis request guardrail evidence is no longer active")

        blockers: list[ResearchRoundBlocker] = []
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
        ):
            _block(
                blockers,
                "research_package_repository",
                "persisted_research_package_repository_validation_failed",
                None,
            )
            blockers_tuple = tuple(blockers)
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
                packages=(),
                blockers=blockers_tuple,
                orchestrated=None,
                run=recorded_run,
                ledger=next_ledger,
                research_round_path=None,
                run_path=run_path,
                ledger_path=ledger_path,
                changed_history=changed,
            )

        packages: list[ResearchSecurityPackage] = []
        resolved_thesis_ids: list[str] = []
        for security_id in request.security_ids:
            thesis = _resolve_latest_thesis_for_package(
                thesis_index,
                security_id=security_id,
                horizon_trading_days=request.horizon_trading_days,
                blockers=blockers,
            )
            if thesis is None:
                if not any(
                    item.security_id == security_id and item.component == "thesis"
                    for item in blockers
                ):
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
            _block(
                blockers,
                "thesis",
                "preflight_thesis_identity_mismatch",
                None,
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


def _resolve_latest_thesis_for_package(
    thesis_index: InvestmentThesisRepositoryIndex,
    *,
    security_id: str,
    horizon_trading_days: int,
    blockers: list[ResearchRoundBlocker],
) -> InvestmentThesisSnapshot | None:
    try:
        thesis = thesis_index.find_latest(
            security_id=security_id,
            horizon_trading_days=horizon_trading_days,
        )
    except InvestmentThesisRepositoryError:
        _block(
            blockers,
            "thesis",
            "investment_thesis_lineage_invalid",
            security_id,
        )
        return None
    if thesis is None:
        _block(
            blockers,
            "thesis",
            "investment_thesis_snapshot_missing",
            security_id,
        )
    return thesis


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
    underwriting_selection_failed = False
    try:
        underwriting = component_index.latest_underwriting(
            security_id,
            thesis_snapshot_id=thesis.snapshot_id,
            evaluation_date=request.evaluation_date,
            lane=request.requested_lane,
            guardrail_evidence_id=guardrail_evidence_id,
        )
    except ResearchComponentRepositoryError:
        underwriting = None
        underwriting_selection_failed = True
        _block(
            blockers,
            "underwriter",
            "underwriting_snapshot_selection_ambiguous",
            security_id,
        )
    if underwriting is None and not underwriting_selection_failed:
        _block(
            blockers,
            "underwriter",
            "underwriting_snapshot_missing_or_incompatible",
            security_id,
        )

    payoff_selection_failed = False
    try:
        payoff = component_index.latest_payoff(
            security_id,
            thesis_snapshot_id=thesis.snapshot_id,
            horizon_trading_days=request.horizon_trading_days,
            guardrail_evidence_id=guardrail_evidence_id,
        )
    except ResearchComponentRepositoryError:
        payoff = None
        payoff_selection_failed = True
        _block(
            blockers,
            "payoff_surface",
            "payoff_surface_selection_ambiguous",
            security_id,
        )
    if payoff is None and not payoff_selection_failed:
        _block(
            blockers,
            "payoff_surface",
            "payoff_surface_missing_or_incompatible",
            security_id,
        )

    decision_view_selection_failed = False
    try:
        view = component_index.latest_decision_view(
            security_id,
            evaluation_date=request.evaluation_date,
            guardrail_evidence_id=guardrail_evidence_id,
        )
    except ResearchComponentRepositoryError:
        view = None
        decision_view_selection_failed = True
        _block(
            blockers,
            "decision_view",
            "decision_view_selection_ambiguous",
            security_id,
        )
    if view is None and not decision_view_selection_failed:
        _block(
            blockers,
            "decision_view",
            "decision_view_missing_or_incompatible",
            security_id,
        )

    gap = None
    expectation_gap_selection_failed = False
    if view is not None:
        try:
            gap = component_index.latest_expectation_gap(
                security_id,
                decision_view_snapshot_id=view.snapshot_id,
                evaluation_date=request.evaluation_date,
                guardrail_evidence_id=guardrail_evidence_id,
            )
        except ResearchComponentRepositoryError:
            expectation_gap_selection_failed = True
            _block(
                blockers,
                "expectation_gap",
                "expectation_gap_selection_ambiguous",
                security_id,
            )
    if gap is None and not expectation_gap_selection_failed:
        _block(
            blockers,
            "expectation_gap",
            "expectation_gap_missing_or_incompatible",
            security_id,
        )

    for code in package_integrity_blocker_codes(
        thesis,
        underwriting,
        payoff,
        view,
        gap,
        artifact_root=artifact_root,
    ):
        _block(blockers, "research_package", code, security_id)

    if underwriting is not None and artifact_root is not None:
        try:
            underwriting_evidence_valid = underwriting_bound_evidence_is_valid(
                artifact_root,
                thesis=thesis,
                underwriting=underwriting,
                payoff=payoff,
            )
        except (
            ResearchPackageSourceRevalidationError,
            OSError,
            TypeError,
            ValueError,
        ):
            underwriting_evidence_valid = False
        if not underwriting_evidence_valid:
            _block(
                blockers,
                "research_package",
                "underwriting_persisted_evidence_canonical_mismatch",
                security_id,
            )

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
    if view is not None and artifact_root is not None:
        try:
            persisted_selection_valid = decision_view_has_valid_persisted_selection(
                view,
                artifact_root=artifact_root,
            )
        except (ResearchPackageIntegrityError, OSError, TypeError, ValueError):
            persisted_selection_valid = False
        if not persisted_selection_valid:
            _block(
                blockers,
                "research_package",
                "decision_view_persisted_selection_invalid",
                security_id,
            )
    if underwriting is not None and view is not None and underwriting.lane is UnderwritingLane.DEEP:
        try:
            tournament_binding_valid = decision_view_matches_underwriting_tournament(
                view, underwriting, artifact_root=artifact_root
            )
        except (ResearchPackageIntegrityError, OSError, TypeError, ValueError):
            tournament_binding_valid = False
        if not tournament_binding_valid:
            _block(
                blockers,
                "research_package",
                "underwriting_decision_view_tournament_binding_mismatch",
                security_id,
            )
    if underwriting is not None and gap is not None:
        if (
            underwriting.expectation_state_snapshot_id is not None
            and underwriting.expectation_state_snapshot_id != gap.expectation_state_snapshot_id
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
        if artifact_root is not None:
            try:
                gap_sources_valid = decision_gap_bound_sources_are_canonical(
                    artifact_root,
                    view=view,
                    gap=gap,
                )
            except ResearchPackageSourceRevalidationError:
                gap_sources_valid = False
            if not gap_sources_valid:
                _block(
                    blockers,
                    "research_package",
                    "decision_gap_persisted_source_binding_mismatch",
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
        current = load_current_research_thesis_preflight_states(root).get(request.snapshot_id)
    except ResearchPreflightStateError as exc:
        raise ValueError("current thesis preflight state failed validation") from exc
    if current is None:
        raise ValueError("analysis request has no current typed-thesis preflight state")
    validate_preflight_selection_timing(current, processed_at=processed_at)
    try:
        validate_preflight_state_request_binding(current.state, request)
    except ResearchPreflightStateError as exc:
        raise ValueError("current thesis preflight does not bind to analysis request") from exc
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
    prior = _matching_package_blocked_run(ledger, request.snapshot_id, blockers)
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
    publication_root = _open_pinned_publication_root(root)
    owned_run: _OwnedFilePublication | None = None
    owned_ledger: _OwnedFilePublication | None = None
    try:
        run_repository = _pin_publication_repository(
            publication_root, "research_round_run_v2_1"
        )
        ledger_repository = _pin_publication_repository(
            publication_root, "research_run_ledger_v2_1"
        )
        if not _publication_namespace_is_current(publication_root):
            raise RuntimeError("blocked-run publication namespace changed before creation")
        run_path, owned_run = _persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_round_run_v2_1",
            repository_root=run_repository.io_path,
            repository_fd=run_repository.fd,
            snapshot_id=run.snapshot_id,
            payload_without_id=run.payload_without_id(),
        )
        ledger_path, owned_ledger = _persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_run_ledger_v2_1",
            repository_root=ledger_repository.io_path,
            repository_fd=ledger_repository.fd,
            snapshot_id=next_ledger.snapshot_id,
            payload_without_id=next_ledger.payload_without_id(),
        )
        if not _publication_namespace_is_current(publication_root):
            raise RuntimeError("blocked-run publication namespace changed before commit")
        return next_ledger, run_path, ledger_path, True
    except BaseException:
        for publication in (owned_ledger, owned_run):
            if publication is not None:
                try:
                    _unlink_owned_file_if_current(publication)
                except BaseException:
                    pass
        raise
    finally:
        _close_pinned_publication_root(publication_root)

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
        item for item in ledger.runs if item.request_snapshot_id == request_snapshot_id
    )
    return matching[-1] if matching else None


def _validate_downstream_artifact_bindings(artifacts: ResearchRoundArtifacts) -> None:
    candidate_ids = tuple(item.snapshot_id for item in artifacts.opportunity_candidates)
    if candidate_ids != artifacts.snapshot.opportunity_candidate_snapshot_ids:
        raise ValueError("research round opportunity-candidate bindings are inconsistent")
    set_id = (
        artifacts.opportunity_set.snapshot_id if artifacts.opportunity_set is not None else None
    )
    if set_id != artifacts.snapshot.opportunity_set_snapshot_id:
        raise ValueError("research round opportunity-set binding is inconsistent")
    if (
        artifacts.expectation_overlay is not None
        or artifacts.snapshot.expectation_overlay_snapshot_id is not None
    ):
        raise ValueError("typed research package assembler does not publish expectation overlays")
    if (
        artifacts.prospective_registration is not None
        or artifacts.snapshot.prospective_registration_snapshot_id is not None
    ):
        raise ValueError(
            "typed research package assembler does not publish prospective registrations"
        )


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _fd_directory_path(fd: int, fallback: Path) -> Path:
    for prefix in (Path("/proc/self/fd"), Path("/dev/fd")):
        candidate = prefix / str(fd)
        if candidate.exists():
            return candidate
    return fallback


def _open_pinned_publication_root(root: Path) -> _PinnedPublicationRoot:
    public_root = require_trusted_artifact_root(root)
    lexical = os.stat(public_root, follow_symlinks=False)
    if os.name == "nt":
        return _PinnedPublicationRoot(
            public_root=public_root,
            io_root=public_root,
            fd=None,
            device=lexical.st_dev,
            inode=lexical.st_ino,
            repositories=[],
        )
    fd = os.open(public_root, _directory_open_flags())
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino):
            raise ResearchPackageIntegrityError(
                "artifact_root changed while pinning publication namespace"
            )
        return _PinnedPublicationRoot(
            public_root=public_root,
            io_root=_fd_directory_path(fd, public_root),
            fd=fd,
            device=opened.st_dev,
            inode=opened.st_ino,
            repositories=[],
        )
    except BaseException:
        os.close(fd)
        raise


def _pin_publication_repository(
    publication_root: _PinnedPublicationRoot,
    repository_name: str,
) -> _PinnedRepository:
    if not repository_name or Path(repository_name).name != repository_name:
        raise ValueError("publication repository name must be one path component")
    public_path = publication_root.public_root / repository_name
    if publication_root.fd is None:
        public_path.mkdir(parents=False, exist_ok=True)
        if public_path.is_symlink() or not public_path.is_dir():
            raise ResearchPackageIntegrityError(
                f"publication repository must be a regular directory: {repository_name}"
            )
        stat = os.stat(public_path, follow_symlinks=False)
        repository = _PinnedRepository(
            public_path=public_path,
            io_path=public_path,
            fd=None,
            device=stat.st_dev,
            inode=stat.st_ino,
        )
        publication_root.repositories.append(repository)
        return repository
    try:
        os.mkdir(repository_name, 0o755, dir_fd=publication_root.fd)
    except FileExistsError:
        pass
    fd = os.open(repository_name, _directory_open_flags(), dir_fd=publication_root.fd)
    try:
        opened = os.fstat(fd)
        lexical = os.stat(public_path, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino):
            raise ResearchPackageIntegrityError(
                f"publication repository changed while pinning: {repository_name}"
            )
        repository = _PinnedRepository(
            public_path=public_path,
            io_path=_fd_directory_path(fd, public_path),
            fd=fd,
            device=opened.st_dev,
            inode=opened.st_ino,
        )
        publication_root.repositories.append(repository)
        return repository
    except BaseException:
        os.close(fd)
        raise


def _publication_namespace_is_current(
    publication_root: _PinnedPublicationRoot,
) -> bool:
    try:
        root_stat = os.stat(publication_root.public_root, follow_symlinks=False)
        if (root_stat.st_dev, root_stat.st_ino) != (
            publication_root.device,
            publication_root.inode,
        ):
            return False
        for repository in publication_root.repositories:
            stat = os.stat(repository.public_path, follow_symlinks=False)
            if (stat.st_dev, stat.st_ino) != (repository.device, repository.inode):
                return False
        return True
    except OSError:
        return False


def _close_pinned_publication_root(publication_root: _PinnedPublicationRoot) -> None:
    for repository in reversed(publication_root.repositories):
        if repository.fd is not None:
            os.close(repository.fd)
            repository.fd = None
    if publication_root.fd is not None:
        os.close(publication_root.fd)
        publication_root.fd = None


def _publish_orchestrated_artifacts(
    *,
    artifacts: ResearchRoundArtifacts,
    run: ResearchRoundRunSnapshot,
    ledger: ResearchRunLedgerSnapshot,
    root: Path,
) -> tuple[Path, Path, Path]:
    validate_publication_layout(root, artifacts=artifacts, run=run, ledger=ledger)
    validate_existing_opportunity_artifacts(root, artifacts)
    publication_root = _open_pinned_publication_root(root)
    opportunity_publications: list[_OwnedOpportunityPublication] = []
    owned_round: _OwnedFilePublication | None = None
    owned_run: _OwnedFilePublication | None = None
    owned_ledger: _OwnedFilePublication | None = None
    try:
        candidate_repository = _pin_publication_repository(
            publication_root, "opportunity_candidate"
        )
        set_repository = (
            _pin_publication_repository(publication_root, "opportunity_set")
            if artifacts.opportunity_set is not None
            else None
        )
        round_repository = _pin_publication_repository(
            publication_root, "research_round_v2_1"
        )
        run_repository = _pin_publication_repository(
            publication_root, "research_round_run_v2_1"
        )
        ledger_repository = _pin_publication_repository(
            publication_root, "research_run_ledger_v2_1"
        )
        if not _publication_namespace_is_current(publication_root):
            raise RuntimeError("publication namespace changed before artifact creation")

        for candidate in artifacts.opportunity_candidates:
            publication = _persist_owned_opportunity_snapshot(
                candidate,
                output_root=publication_root.public_root,
                repository_root=candidate_repository.io_path,
                repository_fd=candidate_repository.fd,
            )
            opportunity_publications.append(publication)
            if not _publication_namespace_is_current(publication_root):
                raise RuntimeError("opportunity repository changed during publication")
            validate_persisted_opportunity_candidate(
                publication_root.public_root,
                candidate,
                require_pointer=_pointer_version_is_current(publication),
            )
            if not _publication_namespace_is_current(publication_root):
                raise RuntimeError("opportunity repository changed during validation")
        if artifacts.opportunity_set is not None:
            if set_repository is None:
                raise RuntimeError("opportunity-set repository pin missing")
            publication = _persist_owned_opportunity_snapshot(
                artifacts.opportunity_set,
                output_root=publication_root.public_root,
                repository_root=set_repository.io_path,
                repository_fd=set_repository.fd,
            )
            opportunity_publications.append(publication)
            if not _publication_namespace_is_current(publication_root):
                raise RuntimeError("opportunity-set repository changed during publication")
            validate_persisted_opportunity_set(
                publication_root.public_root,
                artifacts.opportunity_set,
                require_pointer=_pointer_version_is_current(publication),
            )
            if not _publication_namespace_is_current(publication_root):
                raise RuntimeError("opportunity-set repository changed during validation")

        _, owned_round = _persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_round_v2_1",
            repository_root=round_repository.io_path,
            repository_fd=round_repository.fd,
            snapshot_id=artifacts.snapshot.snapshot_id,
            payload_without_id=artifacts.snapshot.payload_without_id(),
        )
        _, owned_run = _persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_round_run_v2_1",
            repository_root=run_repository.io_path,
            repository_fd=run_repository.fd,
            snapshot_id=run.snapshot_id,
            payload_without_id=run.payload_without_id(),
        )
        if not _owned_file_is_current(owned_round) or not _owned_file_is_current(owned_run):
            raise RuntimeError("round/run publication changed before ledger publication")
        _, owned_ledger = _persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_run_ledger_v2_1",
            repository_root=ledger_repository.io_path,
            repository_fd=ledger_repository.fd,
            snapshot_id=ledger.snapshot_id,
            payload_without_id=ledger.payload_without_id(),
        )
        if not _owned_file_is_current(owned_round) or not _owned_file_is_current(owned_run):
            raise RuntimeError("round/run publication changed during ledger publication")
        if not _publication_namespace_is_current(publication_root):
            raise RuntimeError("publication namespace changed before commit")
        return (
            publication_root.public_root
            / "research_round_v2_1"
            / f"{artifacts.snapshot.snapshot_id}.json",
            publication_root.public_root
            / "research_round_run_v2_1"
            / f"{run.snapshot_id}.json",
            publication_root.public_root
            / "research_run_ledger_v2_1"
            / f"{ledger.snapshot_id}.json",
        )
    except BaseException as exc:
        cleanup_errors: list[BaseException] = []
        for owned_file in (owned_ledger, owned_run, owned_round):
            if owned_file is None:
                continue
            try:
                _unlink_owned_file_if_current(owned_file)
            except BaseException as cleanup_exc:
                cleanup_errors.append(cleanup_exc)
        for publication in reversed(opportunity_publications):
            _rollback_owned_opportunity_publication(publication, cleanup_errors)
        if cleanup_errors:
            raise RuntimeError(
                "orchestrated research publication failed and rollback was incomplete"
            ) from cleanup_errors[0]
        raise exc
    finally:
        _close_pinned_publication_root(publication_root)

def _persist_owned_opportunity_snapshot(
    snapshot: OpportunityCandidateSnapshot | OpportunitySetSnapshot,
    *,
    output_root: Path,
    repository_root: Path | None = None,
    repository_fd: int | None = None,
) -> _OwnedOpportunityPublication:
    if isinstance(snapshot, OpportunityCandidateSnapshot):
        object_name = "opportunity_candidate"
        manifest_extra: dict[str, object] = {
            "security_id": snapshot.security_id,
            "research_class": snapshot.research_class.value,
            "capital_allocation_comparable": snapshot.capital_allocation_comparable,
        }
    else:
        object_name = "opportunity_set"
        manifest_extra = {
            "evaluation_date": snapshot.evaluation_date.isoformat(),
            "horizon_trading_days": snapshot.horizon_trading_days,
            "candidate_count": len(snapshot.candidates),
            "comparable_candidate_count": len(snapshot.comparable_security_ids),
            "pareto_frontier_security_ids": list(snapshot.pareto_frontier_security_ids),
            "unique_pareto_leader_security_id": snapshot.unique_pareto_leader_security_id,
            "capital_allocation_recommendation_enabled": False,
            "automatic_execution_enabled": False,
        }
    public_directory = _opportunity_snapshot_directory(
        output_root,
        object_name=object_name,
        captured_at=snapshot.captured_at,
        snapshot_id=snapshot.snapshot_id,
    )
    if repository_root is None:
        root = output_root / object_name
        root_created = not root.exists()
        root.mkdir(parents=True, exist_ok=True)
    else:
        root = repository_root
        root_created = False
    directory = root / public_directory.name
    directory_created = False
    if not directory.exists():
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{directory.name}.",
                suffix=".owned.tmp",
                dir=root,
            )
        )
        directory_fd: int | None = None
        owned_directory_identity: tuple[int, int] | None = None
        try:
            lexical = os.stat(temporary, follow_symlinks=False)
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            directory_fd = os.open(temporary, flags)
            opened = os.fstat(directory_fd)
            owned_directory_identity = (opened.st_dev, opened.st_ino)
            if (lexical.st_dev, lexical.st_ino) != owned_directory_identity:
                raise RuntimeError("opportunity temp directory changed before open")

            manifest = {
                "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
                "object_type": object_name,
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "immutable": True,
                "files": [f"{object_name}.json"],
                **manifest_extra,
            }
            _write_directory_relative_file(
                directory_fd,
                f"{object_name}.json",
                json.dumps(
                    snapshot.payload_without_id(),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8"),
            )
            _write_directory_relative_file(
                directory_fd,
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
            )
            os.fsync(directory_fd)
            current = os.stat(temporary, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != owned_directory_identity:
                raise RuntimeError("opportunity temp directory changed before publication")
            try:
                os.rename(temporary, directory)
                directory_created = True
            except OSError:
                if not directory.exists():
                    raise
            if directory_created:
                published = os.stat(directory, follow_symlinks=False)
                if (published.st_dev, published.st_ino) != owned_directory_identity:
                    raise RuntimeError("opportunity snapshot directory ownership changed")
        finally:
            if directory_fd is not None:
                os.close(directory_fd)
            # Never recursively delete an ambiguous temporary pathname.  An incomplete
            # unreferenced temp directory is safer than following a raced replacement.

    pointer_name = f"latest_{object_name}.json"
    pointer = output_root / object_name / pointer_name
    if repository_fd is not None:
        before_version = _read_regular_file_at(repository_fd, pointer_name)
        pointer_before = before_version[0] if before_version is not None else None
        pointer_before_identity = before_version[1] if before_version is not None else None
    else:
        pointer_before = _optional_bytes(pointer)
        pointer_before_identity = (
            _capture_file_identity(pointer) if pointer_before is not None else None
        )
    pointer_after = json.dumps(
        {
            "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
            "object_type": object_name,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_path": str(public_directory),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    pointer_published_by_this_call = False
    if repository_fd is not None:
        pointer_temp_fd, pointer_temp_identity = _write_owned_pointer_temp_at(
            repository_fd, pointer_name, pointer_after
        )
        try:
            if pointer_before is None:
                try:
                    _link_open_file_at(
                        pointer_temp_fd,
                        repository_fd,
                        pointer_name,
                    )
                    pointer_published_by_this_call = True
                except FileExistsError:
                    pointer_published_by_this_call = False
            elif pointer_before_identity is not None:
                pointer_published_by_this_call = _replace_pointer_if_version_matches_at(
                    repository_fd,
                    pointer_temp_fd,
                    pointer_name,
                    expected_bytes=pointer_before,
                    expected_identity=pointer_before_identity,
                )
        finally:
            os.close(pointer_temp_fd)
    else:
        pointer_temp = _write_owned_pointer_temp(root, pointer.name, pointer_after)
        pointer_temp_identity = _capture_file_identity(pointer_temp)
        try:
            if pointer_before is None:
                try:
                    os.link(pointer_temp, pointer)
                    pointer_published_by_this_call = True
                except FileExistsError:
                    pointer_published_by_this_call = False
            elif pointer_before_identity is not None:
                pointer_published_by_this_call = _replace_pointer_if_version_matches(
                    pointer_temp,
                    pointer,
                    expected_bytes=pointer_before,
                    expected_identity=pointer_before_identity,
                )
        finally:
            pointer_temp.unlink(missing_ok=True)
    if pointer_published_by_this_call:
        inode, mtime_ns, size = pointer_temp_identity
    else:
        inode = -1
        mtime_ns = -1
        size = -1
    return _OwnedOpportunityPublication(
        root=root,
        directory=directory,
        directory_created=directory_created,
        root_created=root_created,
        pointer=pointer,
        pointer_before=pointer_before,
        pointer_after=pointer_after,
        pointer_inode=inode,
        pointer_mtime_ns=mtime_ns,
        pointer_size=size,
        repository_fd=repository_fd,
    )



def _read_regular_file_at(
    directory_fd: int,
    name: str,
) -> tuple[bytes, tuple[int, int, int]] | None:
    if not name or Path(name).name != name:
        raise ValueError("repository-relative file name must be one path component")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"repository-relative file must be regular: {name}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            content = handle.read()
        return content, (opened.st_ino, opened.st_mtime_ns, opened.st_size)
    finally:
        if fd >= 0:
            os.close(fd)


def _write_owned_pointer_temp_at(
    directory_fd: int,
    pointer_name: str,
    content: bytes,
) -> tuple[int, tuple[int, int, int]]:
    if not pointer_name or Path(pointer_name).name != pointer_name:
        raise ValueError("pointer name must be one path component")
    temporary_flag = getattr(os, "O_TMPFILE", 0)
    if not temporary_flag:
        raise RuntimeError("descriptor-stable pointer publication is unavailable")
    flags = os.O_RDWR | temporary_flag
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(".", flags, 0o644, dir_fd=directory_fd)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o644)  # type: ignore[attr-defined]
        remaining = memoryview(content)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("could not write complete pointer temporary")
            remaining = remaining[written:]
        os.fsync(fd)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size != len(content):
            raise RuntimeError("pointer temporary failed descriptor validation")
        return fd, (opened.st_ino, opened.st_mtime_ns, opened.st_size)
    except BaseException:
        os.close(fd)
        raise


def _link_open_file_at(source_fd: int, directory_fd: int, destination: str) -> None:
    """Hard-link the inode held by ``source_fd`` without reopening a mutable pathname."""

    opened = os.fstat(source_fd)
    if not stat.S_ISREG(opened.st_mode):
        raise RuntimeError("pointer publication source descriptor is not regular")
    for descriptor_root in (Path("/proc/self/fd"), Path("/dev/fd")):
        descriptor_path = descriptor_root / str(source_fd)
        try:
            os.link(
                descriptor_path,
                destination,
                dst_dir_fd=directory_fd,
                follow_symlinks=True,
            )
            return
        except FileNotFoundError:
            continue
    raise RuntimeError("descriptor-stable pointer linking is unavailable")


def _new_publication_quarantine_at(directory_fd: int, name: str) -> str:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(64):
        quarantine = f".{name}.{secrets.token_hex(16)}.quarantine"
        try:
            fd = os.open(quarantine, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            continue
        os.close(fd)
        return quarantine
    raise RuntimeError("could not allocate publication quarantine")


def _restore_quarantined_file_if_absent_at(
    directory_fd: int,
    quarantine: str,
    destination: str,
) -> bool:
    try:
        os.link(
            quarantine,
            destination,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        return True
    except FileExistsError:
        return False


def _replace_pointer_if_version_matches_at(
    directory_fd: int,
    replacement_fd: int,
    pointer: str,
    *,
    expected_bytes: bytes,
    expected_identity: tuple[int, int, int],
) -> bool:
    quarantine = _new_publication_quarantine_at(directory_fd, pointer)
    preserve_quarantine = False
    try:
        try:
            os.replace(
                pointer,
                quarantine,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return False
        observed = _read_regular_file_at(directory_fd, quarantine)
        matches = bool(
            observed is not None
            and observed[1] == expected_identity
            and observed[0] == expected_bytes
        )
        if not matches:
            _restore_quarantined_file_if_absent_at(
                directory_fd, quarantine, pointer
            )
            return False
        try:
            _link_open_file_at(
                replacement_fd,
                directory_fd,
                pointer,
            )
        except FileExistsError:
            return False
        except BaseException as publication_error:
            try:
                restored = _restore_quarantined_file_if_absent_at(
                    directory_fd, quarantine, pointer
                )
            except BaseException as restore_error:
                preserve_quarantine = (
                    _read_regular_file_at(directory_fd, pointer) is None
                )
                raise publication_error from restore_error
            if not restored and _read_regular_file_at(directory_fd, pointer) is None:
                preserve_quarantine = True
            raise
        return True
    finally:
        if not preserve_quarantine:
            try:
                os.unlink(quarantine, dir_fd=directory_fd)
            except FileNotFoundError:
                pass


def _unlink_pointer_if_version_matches_at(
    directory_fd: int,
    pointer: str,
    *,
    expected_bytes: bytes,
    expected_identity: tuple[int, int, int],
) -> bool:
    quarantine = _new_publication_quarantine_at(directory_fd, pointer)
    try:
        try:
            os.replace(
                pointer,
                quarantine,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return False
        observed = _read_regular_file_at(directory_fd, quarantine)
        matches = bool(
            observed is not None
            and observed[1] == expected_identity
            and observed[0] == expected_bytes
        )
        if not matches:
            _restore_quarantined_file_if_absent_at(
                directory_fd, quarantine, pointer
            )
            return False
        return True
    finally:
        try:
            os.unlink(quarantine, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _unlink_owned_file_at(
    publication: _OwnedFilePublication,
) -> bool:
    if publication.repository_fd is None or publication.file_name is None:
        return False
    quarantine = _new_publication_quarantine_at(
        publication.repository_fd, publication.file_name
    )
    try:
        try:
            os.replace(
                publication.file_name,
                quarantine,
                src_dir_fd=publication.repository_fd,
                dst_dir_fd=publication.repository_fd,
            )
        except FileNotFoundError:
            return False
        observed = _read_regular_file_at(publication.repository_fd, quarantine)
        if observed is None:
            return False
        content, identity = observed
        matches = bool(
            identity
            == (publication.inode, publication.mtime_ns, publication.size)
            and hashlib.sha256(content).hexdigest() == publication.sha256
        )
        if not matches:
            _restore_quarantined_file_if_absent_at(
                publication.repository_fd,
                quarantine,
                publication.file_name,
            )
            return False
        return True
    finally:
        try:
            os.unlink(quarantine, dir_fd=publication.repository_fd)
        except FileNotFoundError:
            pass


def _write_directory_relative_file(directory_fd: int, name: str, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name, flags, 0o644, dir_fd=directory_fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if fd >= 0:
            os.close(fd)


def _write_owned_pointer_temp(root: Path, pointer_name: str, content: bytes) -> Path:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{pointer_name}.",
        suffix=".owned.tmp",
        dir=root,
    )
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o644)  # type: ignore[attr-defined]
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _replace_pointer_if_version_matches(
    replacement: Path,
    pointer: Path,
    *,
    expected_bytes: bytes,
    expected_identity: tuple[int, int, int],
) -> bool:
    """Conditionally publish after atomically quarantining the observed old pointer."""

    if pointer.is_symlink() or not pointer.exists():
        return False
    quarantine = _new_publication_quarantine(pointer)
    try:
        try:
            os.replace(pointer, quarantine)
        except FileNotFoundError:
            return False
        if quarantine.is_symlink() or not quarantine.is_file():
            return False
        matches = bool(
            _capture_file_identity(quarantine) == expected_identity
            and quarantine.read_bytes() == expected_bytes
        )
        if not matches:
            _restore_quarantined_file_if_absent(quarantine, pointer)
            return False
        try:
            os.link(replacement, pointer)
        except FileExistsError:
            # A concurrent publisher recreated the canonical name and wins.
            return False
        except BaseException:
            # Publication failed after we claimed the old pointer.  Preserve the
            # previously published state whenever no concurrent writer now owns it.
            _restore_quarantined_file_if_absent(quarantine, pointer)
            raise
        return True
    finally:
        quarantine.unlink(missing_ok=True)


def _new_publication_quarantine(path: Path) -> Path:
    fd, name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".quarantine",
        dir=path.parent,
    )
    os.close(fd)
    return Path(name)


def _restore_quarantined_file_if_absent(quarantine: Path, destination: Path) -> bool:
    if quarantine.is_symlink() or not quarantine.is_file():
        return False
    try:
        os.link(quarantine, destination)
        return True
    except FileExistsError:
        # A concurrent publisher owns the canonical name now.
        return False


def _unlink_pointer_if_version_matches(
    pointer: Path,
    *,
    expected_bytes: bytes,
    expected_identity: tuple[int, int, int],
) -> bool:
    """Delete only the exact pointer version atomically claimed by this rollback."""

    if pointer.is_symlink() or not pointer.exists():
        return False
    quarantine = _new_publication_quarantine(pointer)
    try:
        try:
            os.replace(pointer, quarantine)
        except FileNotFoundError:
            return False
        if quarantine.is_symlink() or not quarantine.is_file():
            return False
        matches = bool(
            _capture_file_identity(quarantine) == expected_identity
            and quarantine.read_bytes() == expected_bytes
        )
        if not matches:
            _restore_quarantined_file_if_absent(quarantine, pointer)
            return False
        # The owned version is now isolated at the quarantine pathname.  If a
        # concurrent publisher has recreated `pointer`, it is left untouched.
        return True
    finally:
        quarantine.unlink(missing_ok=True)


def _pointer_version_is_current(publication: _OwnedOpportunityPublication) -> bool:
    if publication.pointer_inode < 0:
        return False
    if publication.repository_fd is not None:
        try:
            observed = _read_regular_file_at(
                publication.repository_fd, publication.pointer.name
            )
            return bool(
                observed is not None
                and observed[1]
                == (
                    publication.pointer_inode,
                    publication.pointer_mtime_ns,
                    publication.pointer_size,
                )
                and observed[0] == publication.pointer_after
            )
        except OSError:
            return False
    if not publication.pointer.exists() or publication.pointer.is_symlink():
        return False
    try:
        stat_result = publication.pointer.stat()
        return bool(
            stat_result.st_ino == publication.pointer_inode
            and stat_result.st_mtime_ns == publication.pointer_mtime_ns
            and stat_result.st_size == publication.pointer_size
            and publication.pointer.read_bytes() == publication.pointer_after
        )
    except OSError:
        return False

def _rollback_owned_opportunity_publication(
    publication: _OwnedOpportunityPublication,
    cleanup_errors: list[BaseException],
) -> None:
    expected_identity = (
        publication.pointer_inode,
        publication.pointer_mtime_ns,
        publication.pointer_size,
    )
    if publication.pointer_inode < 0:
        return
    if publication.repository_fd is not None:
        try:
            if publication.pointer_before is not None:
                previous_temp_fd, _ = _write_owned_pointer_temp_at(
                    publication.repository_fd,
                    publication.pointer.name,
                    publication.pointer_before,
                )
                try:
                    _replace_pointer_if_version_matches_at(
                        publication.repository_fd,
                        previous_temp_fd,
                        publication.pointer.name,
                        expected_bytes=publication.pointer_after,
                        expected_identity=expected_identity,
                    )
                finally:
                    os.close(previous_temp_fd)
            else:
                _unlink_pointer_if_version_matches_at(
                    publication.repository_fd,
                    publication.pointer.name,
                    expected_bytes=publication.pointer_after,
                    expected_identity=expected_identity,
                )
        except BaseException as exc:
            cleanup_errors.append(exc)
        return
    if publication.pointer_before is not None:
        previous_temp_path = _write_owned_pointer_temp(
            publication.root,
            publication.pointer.name,
            publication.pointer_before,
        )
        try:
            _replace_pointer_if_version_matches(
                previous_temp_path,
                publication.pointer,
                expected_bytes=publication.pointer_after,
                expected_identity=expected_identity,
            )
        except BaseException as exc:
            cleanup_errors.append(exc)
        finally:
            previous_temp_path.unlink(missing_ok=True)
        return
    try:
        _unlink_pointer_if_version_matches(
            publication.pointer,
            expected_bytes=publication.pointer_after,
            expected_identity=expected_identity,
        )
    except BaseException as exc:
        cleanup_errors.append(exc)
    # Immutable content-addressed opportunity directories are intentionally preserved.

def _persist_owned_content_addressed_json(
    *,
    root: Path,
    repository_name: str,
    snapshot_id: str,
    payload_without_id: dict[str, object],
    repository_root: Path | None = None,
    repository_fd: int | None = None,
) -> tuple[Path, _OwnedFilePublication]:
    public_repository = root / repository_name
    repository = repository_root if repository_root is not None else public_repository
    if repository_root is None:
        repository.mkdir(parents=True, exist_ok=True)
    file_name = f"{snapshot_id}.json"
    public_path = public_repository / file_name
    io_path = repository / file_name
    payload = dict(payload_without_id)
    payload["snapshot_id"] = snapshot_id
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = -1
    owned_fd = -1
    created_inode: int | None = None
    publication: _OwnedFilePublication | None = None
    try:
        if repository_fd is not None:
            fd = os.open(file_name, flags, 0o644, dir_fd=repository_fd)
        else:
            fd = os.open(io_path, flags, 0o644)
        created = os.fstat(fd)
        created_inode = created.st_ino
        owned_fd = os.dup(fd)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            completed = os.fstat(handle.fileno())
        publication = _OwnedFilePublication(
            path=public_path,
            inode=completed.st_ino,
            mtime_ns=completed.st_mtime_ns,
            size=completed.st_size,
            sha256=hashlib.sha256(encoded).hexdigest(),
            repository_fd=repository_fd,
            file_name=file_name if repository_fd is not None else None,
        )
        if not _owned_file_is_current(publication):
            raise RuntimeError(f"publication path changed during creation: {public_path}")
        return public_path, publication
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            if publication is not None:
                _unlink_owned_file_if_current(publication)
            elif repository_fd is None and created_inode is not None:
                _unlink_file_if_inode_matches(io_path, created_inode)
        except BaseException:
            pass
        raise
    finally:
        if owned_fd >= 0:
            os.close(owned_fd)

def _unlink_file_if_inode_matches(path: Path, expected_inode: int) -> bool:
    if path.is_symlink() or not path.exists():
        return False
    quarantine = _new_publication_quarantine(path)
    try:
        try:
            os.replace(path, quarantine)
        except FileNotFoundError:
            return False
        if quarantine.is_symlink() or not quarantine.is_file():
            return False
        if quarantine.stat().st_ino != expected_inode:
            _restore_quarantined_file_if_absent(quarantine, path)
            return False
        return True
    finally:
        quarantine.unlink(missing_ok=True)


def _capture_file_identity(path: Path) -> tuple[int, int, int]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"publication path must be a regular file: {path}")
    stat = path.stat()
    return stat.st_ino, stat.st_mtime_ns, stat.st_size


def _capture_owned_file(path: Path) -> _OwnedFilePublication:
    inode, mtime_ns, size = _capture_file_identity(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return _OwnedFilePublication(
        path=path,
        inode=inode,
        mtime_ns=mtime_ns,
        size=size,
        sha256=digest,
    )


def _owned_file_is_current(publication: _OwnedFilePublication) -> bool:
    if publication.repository_fd is not None and publication.file_name is not None:
        try:
            observed = _read_regular_file_at(
                publication.repository_fd, publication.file_name
            )
            if observed is None:
                return False
            content, identity = observed
            return bool(
                identity == (publication.inode, publication.mtime_ns, publication.size)
                and hashlib.sha256(content).hexdigest() == publication.sha256
            )
        except OSError:
            return False
    path = publication.path
    if path.is_symlink() or not path.is_file():
        return False
    try:
        inode, mtime_ns, size = _capture_file_identity(path)
        if (
            inode != publication.inode
            or mtime_ns != publication.mtime_ns
            or size != publication.size
        ):
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == publication.sha256
    except OSError:
        return False

def _unlink_owned_file_if_current(publication: _OwnedFilePublication) -> bool:
    """Remove only the exact owned inode/version after atomically claiming its name."""
    if publication.repository_fd is not None and publication.file_name is not None:
        return _unlink_owned_file_at(publication)
    path = publication.path
    if path.is_symlink() or not path.exists():
        return False
    quarantine = _new_publication_quarantine(path)
    try:
        try:
            os.replace(path, quarantine)
        except FileNotFoundError:
            return False
        if quarantine.is_symlink() or not quarantine.is_file():
            return False
        try:
            inode, mtime_ns, size = _capture_file_identity(quarantine)
            digest = hashlib.sha256(quarantine.read_bytes()).hexdigest()
        except OSError:
            _restore_quarantined_file_if_absent(quarantine, path)
            return False
        matches = bool(
            inode == publication.inode
            and mtime_ns == publication.mtime_ns
            and size == publication.size
            and digest == publication.sha256
        )
        if not matches:
            _restore_quarantined_file_if_absent(quarantine, path)
            return False
        return True
    finally:
        quarantine.unlink(missing_ok=True)

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
        raise ValueError(f"request_id must resolve exactly once in latest ledger: {request_id}")
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
