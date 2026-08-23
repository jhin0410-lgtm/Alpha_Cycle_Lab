"""Typed thesis preflight for pending Alpha Cycle Lab research requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    AnalysisRequestSnapshot,
    ResearchRoundRunSnapshot,
    ResearchRunKind,
    ResearchRunLedgerSnapshot,
    build_pre_orchestration_blocked_run,
    build_pre_orchestration_ready_run,
    build_research_run_ledger,
    persist_research_run,
    persist_research_run_ledger,
)
from alpha_cycle.investment_thesis_repository_v2_1 import (
    build_investment_thesis_repository_index,
)
from alpha_cycle.research_ledger_write_lock_v2_1 import (
    exclusive_research_ledger_write_lock,
)
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state


@dataclass(frozen=True)
class ResearchThesisPreflightReceipt:
    request: AnalysisRequestSnapshot
    research_cutoff_at: datetime
    thesis_snapshots: tuple[InvestmentThesisSnapshot, ...]
    blockers: tuple[ResearchRoundBlocker, ...]
    run: ResearchRoundRunSnapshot | None
    ledger: ResearchRunLedgerSnapshot
    run_path: Path | None
    ledger_path: Path | None
    changed_history: bool

    @property
    def ready_for_package_assembly(self) -> bool:
        return not self.blockers

    def payload(self) -> dict[str, object]:
        return {
            "request_id": self.request.request_id,
            "request_snapshot_id": self.request.snapshot_id,
            "research_cutoff_at": self.research_cutoff_at.isoformat(),
            "thesis_snapshot_ids": [item.snapshot_id for item in self.thesis_snapshots],
            "blockers": [item.payload() for item in self.blockers],
            "run_snapshot_id": self.run.snapshot_id if self.run is not None else None,
            "ledger_snapshot_id": self.ledger.snapshot_id,
            "run_path": str(self.run_path) if self.run_path is not None else None,
            "ledger_path": str(self.ledger_path) if self.ledger_path is not None else None,
            "changed_history": self.changed_history,
            "ready_for_package_assembly": self.ready_for_package_assembly,
            "orchestrator_executed": False,
            "investment_conclusion_created": False,
            "automatic_execution_enabled": False,
        }


def preflight_pending_request_theses(
    *,
    request_id: str,
    run_id: str,
    processed_at: datetime,
    artifact_root: str | Path,
    research_cutoff_at: datetime | None = None,
) -> ResearchThesisPreflightReceipt:
    """Resolve typed theses and append only meaningful pre-orchestration transitions."""

    _require_aware(processed_at, "processed_at")
    if research_cutoff_at is not None:
        _require_aware(research_cutoff_at, "research_cutoff_at")
    root = Path(artifact_root)

    with exclusive_research_ledger_write_lock(root):
        state = load_latest_observatory_state(root)
        if state is None:
            raise ValueError("no Research Run Ledger exists; record an analysis request first")
        ledger = state.ledger
        request = _find_request(ledger, request_id)
        if processed_at < request.requested_at:
            raise ValueError("processed_at cannot precede the analysis request")
        if any(item.run_id == run_id for item in ledger.runs):
            raise ValueError(f"run_id already exists in the latest ledger: {run_id}")

        cutoff = _resolve_research_cutoff(
            request,
            processed_at=processed_at,
            research_cutoff_at=research_cutoff_at,
        )

        # Build one validated point-in-time repository index while the shared write lock is held,
        # then resolve every requested security from memory. This avoids N full repository scans
        # for an N-security request and keeps intake lock hold time proportional to repository size.
        thesis_index = build_investment_thesis_repository_index(root, as_of=cutoff)
        theses: list[InvestmentThesisSnapshot] = []
        blockers: list[ResearchRoundBlocker] = []
        for security_id in _unique_security_ids(request.security_ids):
            thesis = thesis_index.find_latest(
                security_id=security_id,
                horizon_trading_days=request.horizon_trading_days,
            )
            if thesis is None:
                blockers.append(
                    ResearchRoundBlocker(
                        component="thesis",
                        code="investment_thesis_snapshot_missing",
                        detail=(
                            "no validated persisted InvestmentThesisSnapshot exists for the "
                            "requested security and trading-day horizon at the research cutoff"
                        ),
                        security_id=security_id,
                    )
                )
            else:
                theses.append(thesis)

        blockers_tuple = tuple(blockers)
        theses_tuple = tuple(theses)
        preflight_flags = _preflight_flags(
            request,
            cutoff,
            ready=not blockers_tuple,
        )

        # Idempotence is defined over the full immutable request history, not merely its latest
        # run. This matters for REPLAY cutoff A -> B -> A: revisiting A must reuse the prior A
        # preflight event instead of inflating run/blocker metrics with a duplicate event.
        prior = _matching_preflight_run(
            ledger,
            request_snapshot_id=request.snapshot_id,
            blockers=blockers_tuple,
            flags=preflight_flags,
        )
        if prior is not None:
            return ResearchThesisPreflightReceipt(
                request=request,
                research_cutoff_at=cutoff,
                thesis_snapshots=theses_tuple,
                blockers=blockers_tuple,
                run=prior,
                ledger=ledger,
                run_path=None,
                ledger_path=None,
                changed_history=False,
            )

        if processed_at <= ledger.built_at:
            raise ValueError(
                "processed_at must be later than the latest ledger built_at when appending history"
            )

        if blockers_tuple:
            run = build_pre_orchestration_blocked_run(
                request,
                run_id=run_id,
                started_at=processed_at,
                completed_at=processed_at,
                blockers=blockers_tuple,
                flags=preflight_flags,
            )
        else:
            # Readiness here means only that the typed thesis prerequisite has cleared. It does
            # not claim an orchestrated ResearchRoundSnapshot or any investment conclusion.
            run = build_pre_orchestration_ready_run(
                request,
                run_id=run_id,
                started_at=processed_at,
                completed_at=processed_at,
                flags=preflight_flags,
            )

        next_ledger = build_research_run_ledger(
            ledger.requests,
            (*ledger.runs, run),
            built_at=processed_at,
        )
        run_path = persist_research_run(run, output_root=root)
        try:
            ledger_path = persist_research_run_ledger(next_ledger, output_root=root)
        except BaseException:
            run_path.unlink(missing_ok=True)
            raise
        return ResearchThesisPreflightReceipt(
            request=request,
            research_cutoff_at=cutoff,
            thesis_snapshots=theses_tuple,
            blockers=blockers_tuple,
            run=run,
            ledger=next_ledger,
            run_path=run_path,
            ledger_path=ledger_path,
            changed_history=True,
        )


def _resolve_research_cutoff(
    request: AnalysisRequestSnapshot,
    *,
    processed_at: datetime,
    research_cutoff_at: datetime | None,
) -> datetime:
    if request.mode is ResearchRoundMode.REPLAY and research_cutoff_at is None:
        raise ValueError("replay thesis preflight requires an explicit research_cutoff_at")
    cutoff = research_cutoff_at or processed_at
    if cutoff > processed_at:
        raise ValueError("research_cutoff_at cannot be later than processed_at")
    if request.mode is ResearchRoundMode.PROSPECTIVE and cutoff < request.requested_at:
        raise ValueError(
            "prospective research_cutoff_at cannot precede the analysis request"
        )
    return cutoff


def _preflight_flags(
    request: AnalysisRequestSnapshot,
    cutoff: datetime,
    *,
    ready: bool,
) -> tuple[str, ...]:
    flags = [
        "typed_thesis_preflight_ready" if ready else "typed_thesis_preflight_blocked"
    ]
    if request.mode is ResearchRoundMode.REPLAY:
        flags.append(f"typed_thesis_replay_cutoff:{cutoff.isoformat()}")
    return tuple(flags)


def _find_request(
    ledger: ResearchRunLedgerSnapshot,
    request_id: str,
) -> AnalysisRequestSnapshot:
    matches = tuple(item for item in ledger.requests if item.request_id == request_id)
    if not matches:
        raise ValueError(f"request_id is not present in the latest ledger: {request_id}")
    if len(matches) != 1:
        raise ValueError(f"request_id is not unique in the latest ledger: {request_id}")
    return matches[0]


def _matching_preflight_run(
    ledger: ResearchRunLedgerSnapshot,
    *,
    request_snapshot_id: str,
    blockers: tuple[ResearchRoundBlocker, ...],
    flags: tuple[str, ...],
) -> ResearchRoundRunSnapshot | None:
    preflight_kinds = {
        ResearchRunKind.PRE_ORCHESTRATION_BLOCKED,
        ResearchRunKind.PRE_ORCHESTRATION_READY,
    }
    matching = tuple(
        item
        for item in ledger.runs
        if item.request_snapshot_id == request_snapshot_id
        and item.kind in preflight_kinds
        and item.blockers == blockers
        and item.flags == flags
    )
    return matching[-1] if matching else None


def _unique_security_ids(security_ids: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for security_id in security_ids:
        key = security_id.strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(security_id)
    return tuple(unique)


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
