"""Fail-closed persisted research-package assembly for Decision System v2.1.

This module does not create research evidence. It reconstructs already-persisted typed objects,
checks their PIT/request bindings, and delegates research logic to the existing
`run_research_round` orchestrator only after a complete package exists.
"""

from __future__ import annotations

import json
import os
import shutil
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
from alpha_cycle.research_package_integrity_v2_1 import (
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
    if (
        view is not None
        and artifact_root is not None
        and not decision_view_has_valid_persisted_selection(
            view,
            artifact_root=artifact_root,
        )
    ):
        _block(
            blockers,
            "research_package",
            "decision_view_persisted_selection_invalid",
            security_id,
        )
    if (
        underwriting is not None
        and view is not None
        and underwriting.lane is UnderwritingLane.DEEP
    ):
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

    opportunity_publications: list[_OwnedOpportunityPublication] = []
    round_path: Path | None = None
    run_path: Path | None = None
    try:
        for candidate in artifacts.opportunity_candidates:
            publication = _persist_owned_opportunity_snapshot(candidate, output_root=root)
            opportunity_publications.append(publication)
            validate_persisted_opportunity_candidate(
                root,
                candidate,
                require_pointer=_pointer_version_is_current(publication),
            )
        if artifacts.opportunity_set is not None:
            publication = _persist_owned_opportunity_snapshot(
                artifacts.opportunity_set,
                output_root=root,
            )
            opportunity_publications.append(publication)
            validate_persisted_opportunity_set(
                root,
                artifacts.opportunity_set,
                require_pointer=_pointer_version_is_current(publication),
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
        for publication in reversed(opportunity_publications):
            _rollback_owned_opportunity_publication(publication, cleanup_errors)
        if cleanup_errors:
            raise RuntimeError(
                "orchestrated research publication failed and rollback was incomplete"
            ) from cleanup_errors[0]
        raise exc


def _persist_owned_opportunity_snapshot(
    snapshot: OpportunityCandidateSnapshot | OpportunitySetSnapshot,
    *,
    output_root: Path,
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
    root = output_root / object_name
    root_created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    directory = _opportunity_snapshot_directory(
        output_root,
        object_name=object_name,
        captured_at=snapshot.captured_at,
        snapshot_id=snapshot.snapshot_id,
    )
    directory_created = False
    if not directory.exists():
        temporary = root / f".{directory.name}.{os.getpid()}.owned.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            manifest = {
                "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
                "object_type": object_name,
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "immutable": True,
                "files": [f"{object_name}.json"],
                **manifest_extra,
            }
            (temporary / f"{object_name}.json").write_text(
                json.dumps(
                    snapshot.payload_without_id(),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            try:
                temporary.rename(directory)
                directory_created = True
            except OSError:
                if not directory.exists():
                    raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    pointer = root / f"latest_{object_name}.json"
    pointer_before = _optional_bytes(pointer)
    pointer_after = json.dumps(
        {
            "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,
            "object_type": object_name,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_path": str(directory),
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    pointer_temp = _write_owned_pointer_temp(root, pointer.name, pointer_after)
    try:
        if pointer_before is None:
            try:
                os.link(pointer_temp, pointer)
            except FileExistsError:
                # A concurrent publisher won the absent-pointer race; do not overwrite it.
                pass
        else:
            pointer_temp.replace(pointer)
    finally:
        pointer_temp.unlink(missing_ok=True)
    if pointer.exists() and pointer.read_bytes() == pointer_after:
        stat = pointer.stat()
        inode = stat.st_ino
        mtime_ns = stat.st_mtime_ns
        size = stat.st_size
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
    )


def _write_owned_pointer_temp(root: Path, pointer_name: str, content: bytes) -> Path:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{pointer_name}.",
        suffix=".owned.tmp",
        dir=root,
    )
    temporary = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _pointer_version_is_current(publication: _OwnedOpportunityPublication) -> bool:
    if publication.pointer_inode < 0 or not publication.pointer.exists():
        return False
    if publication.pointer.is_symlink():
        return False
    try:
        stat = publication.pointer.stat()
        return bool(
            stat.st_ino == publication.pointer_inode
            and stat.st_mtime_ns == publication.pointer_mtime_ns
            and stat.st_size == publication.pointer_size
            and publication.pointer.read_bytes() == publication.pointer_after
        )
    except OSError:
        return False


def _rollback_owned_opportunity_publication(
    publication: _OwnedOpportunityPublication,
    cleanup_errors: list[BaseException],
) -> None:
    # Never restore an older pointer over a possibly newer concurrent publisher. If a pointer
    # existed before this transaction, preserve this valid immutable publication on failure.
    if publication.pointer_before is not None:
        return
    # If another publisher has changed/replaced the pointer, ownership is no longer exclusive;
    # preserve both the pointer and immutable directory rather than deleting foreign state.
    if not _pointer_version_is_current(publication):
        return
    try:
        publication.pointer.unlink(missing_ok=True)
    except BaseException as exc:
        cleanup_errors.append(exc)
        return
    if publication.directory_created:
        try:
            if publication.directory.is_symlink():
                raise RuntimeError(
                    f"rollback refused symlinked snapshot directory: {publication.directory}"
                )
            if publication.directory.exists():
                shutil.rmtree(publication.directory)
        except BaseException as exc:
            cleanup_errors.append(exc)
            return
    if publication.root_created:
        try:
            publication.root.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            pass


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
