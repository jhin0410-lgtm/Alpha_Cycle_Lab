"""Write-side intake service for immutable Alpha Cycle Lab research requests.

Request intake is intentionally narrower than research execution. It records a human PM request
into the append-only Research Run Ledger so the Observatory can show it as ``request_pending``.
It never invents thesis evidence, runs valuation logic, or claims that research completed.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    AnalysisRequestSnapshot,
    ResearchRoundRunSnapshot,
    ResearchRunLedgerSnapshot,
    build_research_run_ledger,
    persist_analysis_request,
    persist_research_run_ledger,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state

_INTAKE_LOCK_NAME = ".research_request_intake.lock"


@dataclass(frozen=True)
class ResearchRequestReceipt:
    request: AnalysisRequestSnapshot
    ledger: ResearchRunLedgerSnapshot
    request_path: Path
    ledger_path: Path

    def payload(self) -> dict[str, object]:
        return {
            "request_id": self.request.request_id,
            "request_snapshot_id": self.request.snapshot_id,
            "ledger_snapshot_id": self.ledger.snapshot_id,
            "request_path": str(self.request_path),
            "ledger_path": str(self.ledger_path),
            "state": "request_pending",
            "research_executed": False,
            "investment_conclusion_created": False,
            "automatic_execution_enabled": False,
        }


def record_analysis_request(
    *,
    request_id: str,
    requested_at: datetime,
    recorded_at: datetime,
    evaluation_date: date,
    horizon_trading_days: int,
    security_ids: tuple[str, ...],
    mode: ResearchRoundMode,
    requested_lane: UnderwritingLane,
    request_text: str,
    artifact_root: str | Path,
    tags: tuple[str, ...] = (),
) -> ResearchRequestReceipt:
    """Append one immutable pending request to the latest validated ledger history."""

    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("requested_at must be timezone-aware")
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("recorded_at must be timezone-aware")
    if recorded_at < requested_at:
        raise ValueError("recorded_at cannot precede requested_at")

    guardrail = load_decision_system_v21_guardrails()
    request = AnalysisRequestSnapshot(
        request_id=request_id,
        requested_at=requested_at,
        evaluation_date=evaluation_date,
        horizon_trading_days=horizon_trading_days,
        security_ids=security_ids,
        mode=mode,
        requested_lane=requested_lane,
        request_text=request_text,
        guardrail_evidence_id=guardrail.evidence_id,
        tags=tags,
    )

    root = Path(artifact_root)
    with _exclusive_intake_lock(root):
        existing = load_latest_observatory_state(root)
        if existing is None:
            requests: tuple[AnalysisRequestSnapshot, ...] = ()
            runs: tuple[ResearchRoundRunSnapshot, ...] = ()
        else:
            requests = existing.ledger.requests
            runs = existing.ledger.runs

        if any(item.request_id == request.request_id for item in requests):
            raise ValueError(
                f"request_id already exists in the latest ledger: {request.request_id}"
            )

        ledger = build_research_run_ledger(
            (*requests, request),
            runs,
            built_at=recorded_at,
        )
        request_path = persist_analysis_request(request, output_root=root)
        try:
            ledger_path = persist_research_run_ledger(ledger, output_root=root)
        except BaseException:
            request_path.unlink(missing_ok=True)
            raise

    return ResearchRequestReceipt(
        request=request,
        ledger=ledger,
        request_path=request_path,
        ledger_path=ledger_path,
    )


@contextmanager
def _exclusive_intake_lock(artifact_root: Path) -> Iterator[None]:
    """Serialize local ledger appends so concurrent UI sessions cannot fork history."""

    artifact_root.mkdir(parents=True, exist_ok=True)
    lock_path = artifact_root / _INTAKE_LOCK_NAME
    fd: int | None = None
    created = False
    try:
        fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
        yield
    finally:
        if fd is not None:
            os.close(fd)
        if created:
            lock_path.unlink(missing_ok=True)
