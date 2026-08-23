"""Append-only research request/run observability for Decision System v2.1.

The ledger records what research was requested, what actually ran, and why a run was blocked.
It is deliberately descriptive. It does not reimplement investment logic, infer predictive skill,
score securities, size positions, or execute trades.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from statistics import mean, median

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
    ResearchRoundSnapshot,
    ResearchRoundStatus,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane

RESEARCH_RUN_LEDGER_SCHEMA_VERSION = 1
_SUPPORTED_HORIZONS = frozenset({60, 120, 250})
_HEX_DIGITS = frozenset("0123456789abcdef")


class ResearchRunKind(StrEnum):
    PRE_ORCHESTRATION_BLOCKED = "pre_orchestration_blocked"
    PRE_ORCHESTRATION_READY = "pre_orchestration_ready"
    ORCHESTRATED = "orchestrated"


@dataclass(frozen=True)
class AnalysisRequestSnapshot:
    """Immutable record of a human/system research request before execution."""

    request_id: str
    requested_at: datetime
    evaluation_date: date
    horizon_trading_days: int
    security_ids: tuple[str, ...]
    mode: ResearchRoundMode
    requested_lane: UnderwritingLane
    request_text: str
    guardrail_evidence_id: str
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        _require_aware(self.requested_at, "requested_at")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("request horizon must be 60, 120, or 250 trading days")
        _validate_text_tuple(self.security_ids, "security_ids")
        if not self.security_ids:
            raise ValueError("analysis request requires at least one security")
        if not isinstance(self.mode, ResearchRoundMode):
            raise ValueError("mode must be a ResearchRoundMode")
        if not isinstance(self.requested_lane, UnderwritingLane):
            raise ValueError("requested_lane must be an UnderwritingLane")
        _require_text(self.request_text, "request_text")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _validate_text_tuple(self.tags, "tags")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": RESEARCH_RUN_LEDGER_SCHEMA_VERSION,
            "request_id": self.request_id,
            "requested_at": self.requested_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "security_ids": list(self.security_ids),
            "mode": self.mode.value,
            "requested_lane": self.requested_lane.value,
            "request_text": self.request_text,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "tags": list(self.tags),
            "append_only_request": True,
        }


@dataclass(frozen=True)
class ResearchRoundRunSnapshot:
    """Immutable execution record bound to a request and optionally an orchestrator snapshot."""

    run_id: str
    request_snapshot_id: str
    request_id: str
    kind: ResearchRunKind
    started_at: datetime
    completed_at: datetime
    evaluation_date: date
    horizon_trading_days: int
    security_ids: tuple[str, ...]
    mode: ResearchRoundMode
    requested_lane: UnderwritingLane
    research_round_snapshot_id: str | None
    round_status: ResearchRoundStatus | None
    blockers: tuple[ResearchRoundBlocker, ...]
    flags: tuple[str, ...]
    opportunity_set_snapshot_id: str | None
    expectation_overlay_snapshot_id: str | None
    prospective_registration_snapshot_id: str | None
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _validate_sha(self.request_snapshot_id, "request_snapshot_id")
        _require_text(self.request_id, "request_id")
        if not isinstance(self.kind, ResearchRunKind):
            raise ValueError("kind must be a ResearchRunKind")
        _require_aware(self.started_at, "started_at")
        _require_aware(self.completed_at, "completed_at")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        if self.horizon_trading_days not in _SUPPORTED_HORIZONS:
            raise ValueError("run horizon must be 60, 120, or 250 trading days")
        _validate_text_tuple(self.security_ids, "security_ids")
        if not self.security_ids:
            raise ValueError("research run requires at least one security")
        if not isinstance(self.mode, ResearchRoundMode):
            raise ValueError("mode must be a ResearchRoundMode")
        if not isinstance(self.requested_lane, UnderwritingLane):
            raise ValueError("requested_lane must be an UnderwritingLane")
        _validate_text_tuple(self.flags, "flags")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        for value, field in (
            (self.research_round_snapshot_id, "research_round_snapshot_id"),
            (self.opportunity_set_snapshot_id, "opportunity_set_snapshot_id"),
            (self.expectation_overlay_snapshot_id, "expectation_overlay_snapshot_id"),
            (
                self.prospective_registration_snapshot_id,
                "prospective_registration_snapshot_id",
            ),
        ):
            if value is not None:
                _validate_sha(value, field)
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("research run blockers cannot contain duplicates")
        self._validate_kind()

    def _validate_kind(self) -> None:
        if self.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED:
            if self.research_round_snapshot_id is not None or self.round_status is not None:
                raise ValueError("pre-orchestration blocked run cannot claim a round snapshot")
            if not self.blockers:
                raise ValueError("pre-orchestration blocked run requires blockers")
            if any(
                value is not None
                for value in (
                    self.opportunity_set_snapshot_id,
                    self.expectation_overlay_snapshot_id,
                    self.prospective_registration_snapshot_id,
                )
            ):
                raise ValueError("pre-orchestration blocked run cannot claim downstream artifacts")
            return
        if self.kind is ResearchRunKind.PRE_ORCHESTRATION_READY:
            if self.research_round_snapshot_id is not None or self.round_status is not None:
                raise ValueError("pre-orchestration ready run cannot claim a round snapshot")
            if self.blockers:
                raise ValueError("pre-orchestration ready run cannot contain blockers")
            if any(
                value is not None
                for value in (
                    self.opportunity_set_snapshot_id,
                    self.expectation_overlay_snapshot_id,
                    self.prospective_registration_snapshot_id,
                )
            ):
                raise ValueError("pre-orchestration ready run cannot claim downstream artifacts")
            return
        if self.research_round_snapshot_id is None or self.round_status is None:
            raise ValueError("orchestrated run requires a bound research-round snapshot")
        blocked_statuses = {
            ResearchRoundStatus.PROSPECTIVE_BLOCKED,
            ResearchRoundStatus.REPLAY_BLOCKED,
        }
        if self.round_status in blocked_statuses and not self.blockers:
            raise ValueError("blocked orchestrated run requires blockers")
        if self.round_status not in blocked_statuses and self.blockers:
            raise ValueError("ready orchestrated run cannot contain blockers")

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": RESEARCH_RUN_LEDGER_SCHEMA_VERSION,
            "run_id": self.run_id,
            "request_snapshot_id": self.request_snapshot_id,
            "request_id": self.request_id,
            "kind": self.kind.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "evaluation_date": self.evaluation_date.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "security_ids": list(self.security_ids),
            "mode": self.mode.value,
            "requested_lane": self.requested_lane.value,
            "research_round_snapshot_id": self.research_round_snapshot_id,
            "round_status": self.round_status.value if self.round_status else None,
            "blockers": [item.payload() for item in self.blockers],
            "flags": list(self.flags),
            "opportunity_set_snapshot_id": self.opportunity_set_snapshot_id,
            "expectation_overlay_snapshot_id": self.expectation_overlay_snapshot_id,
            "prospective_registration_snapshot_id": (
                self.prospective_registration_snapshot_id
            ),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "descriptive_observability_only": True,
            "predictive_skill_inference_enabled": False,
            "weighted_score_training_enabled": False,
            "portfolio_optimization_enabled": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class ResearchProcessObservabilitySummary:
    request_count: int
    run_count: int
    orchestrated_run_count: int
    pre_orchestration_blocked_run_count: int
    blocked_run_count: int
    prospective_run_count: int
    replay_run_count: int
    prospective_registered_run_count: int
    opportunity_set_run_count: int
    expectation_overlay_run_count: int
    unique_security_count: int
    mean_blockers_per_run: float | None
    median_blockers_per_run: float | None
    mean_duration_seconds: float | None
    median_duration_seconds: float | None
    status_counts: tuple[tuple[str, int], ...]
    blocker_component_counts: tuple[tuple[str, int], ...]
    blocker_code_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        counts = (
            self.request_count,
            self.run_count,
            self.orchestrated_run_count,
            self.pre_orchestration_blocked_run_count,
            self.blocked_run_count,
            self.prospective_run_count,
            self.replay_run_count,
            self.prospective_registered_run_count,
            self.opportunity_set_run_count,
            self.expectation_overlay_run_count,
            self.unique_security_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("observability counts cannot be negative")
        pre_orchestration_ready_run_count = sum(
            count
            for status, count in self.status_counts
            if status == ResearchRunKind.PRE_ORCHESTRATION_READY.value
        )
        if (
            self.orchestrated_run_count
            + self.pre_orchestration_blocked_run_count
            + pre_orchestration_ready_run_count
            != self.run_count
        ):
            raise ValueError("run-kind counts must sum to run_count")
        if self.prospective_run_count + self.replay_run_count != self.run_count:
            raise ValueError("mode counts must sum to run_count")
        if self.blocked_run_count > self.run_count:
            raise ValueError("blocked_run_count cannot exceed run_count")
        for metric in (
            self.mean_blockers_per_run,
            self.median_blockers_per_run,
            self.mean_duration_seconds,
            self.median_duration_seconds,
        ):
            if metric is not None and metric < 0:
                raise ValueError("observability metrics cannot be negative")
        _validate_counter_rows(self.status_counts, "status_counts")
        _validate_counter_rows(self.blocker_component_counts, "blocker_component_counts")
        _validate_counter_rows(self.blocker_code_counts, "blocker_code_counts")
        if self.run_count == 0 and any(
            metric is not None
            for metric in (
                self.mean_blockers_per_run,
                self.median_blockers_per_run,
                self.mean_duration_seconds,
                self.median_duration_seconds,
            )
        ):
            raise ValueError("empty run history cannot claim run metrics")

    def payload(self) -> dict[str, object]:
        return {
            "request_count": self.request_count,
            "run_count": self.run_count,
            "orchestrated_run_count": self.orchestrated_run_count,
            "pre_orchestration_blocked_run_count": self.pre_orchestration_blocked_run_count,
            "blocked_run_count": self.blocked_run_count,
            "prospective_run_count": self.prospective_run_count,
            "replay_run_count": self.replay_run_count,
            "prospective_registered_run_count": self.prospective_registered_run_count,
            "opportunity_set_run_count": self.opportunity_set_run_count,
            "expectation_overlay_run_count": self.expectation_overlay_run_count,
            "unique_security_count": self.unique_security_count,
            "mean_blockers_per_run": self.mean_blockers_per_run,
            "median_blockers_per_run": self.median_blockers_per_run,
            "mean_duration_seconds": self.mean_duration_seconds,
            "median_duration_seconds": self.median_duration_seconds,
            "status_counts": [list(item) for item in self.status_counts],
            "blocker_component_counts": [list(item) for item in self.blocker_component_counts],
            "blocker_code_counts": [list(item) for item in self.blocker_code_counts],
            "process_metrics_only": True,
            "investment_alpha_claimed": False,
            "forecast_calibration_claimed": False,
        }


@dataclass(frozen=True)
class ResearchRunLedgerSnapshot:
    built_at: datetime
    requests: tuple[AnalysisRequestSnapshot, ...]
    runs: tuple[ResearchRoundRunSnapshot, ...]
    summary: ResearchProcessObservabilitySummary

    def __post_init__(self) -> None:
        _require_aware(self.built_at, "built_at")
        if any(item.requested_at > self.built_at for item in self.requests):
            raise ValueError("ledger cannot be built before a request was recorded")
        if any(item.completed_at > self.built_at for item in self.runs):
            raise ValueError("ledger cannot be built before a run completed")
        if self.requests != tuple(sorted(self.requests, key=_request_sort_key)):
            raise ValueError("ledger requests must use canonical chronological order")
        if self.runs != tuple(sorted(self.runs, key=_run_sort_key)):
            raise ValueError("ledger runs must use canonical chronological order")
        request_ids = [item.request_id for item in self.requests]
        request_snapshot_ids = [item.snapshot_id for item in self.requests]
        run_ids = [item.run_id for item in self.runs]
        run_snapshot_ids = [item.snapshot_id for item in self.runs]
        if len(set(request_ids)) != len(request_ids):
            raise ValueError("ledger request ids must be unique")
        if len(set(request_snapshot_ids)) != len(request_snapshot_ids):
            raise ValueError("ledger request snapshots must be unique")
        if len(set(run_ids)) != len(run_ids):
            raise ValueError("ledger run ids must be unique")
        if len(set(run_snapshot_ids)) != len(run_snapshot_ids):
            raise ValueError("ledger run snapshots must be unique")
        request_by_snapshot = {item.snapshot_id: item for item in self.requests}
        bound_round_ids: set[str] = set()
        for run in self.runs:
            request = request_by_snapshot.get(run.request_snapshot_id)
            if request is None:
                raise ValueError("every run must bind to a request contained in the ledger")
            _validate_request_run_binding(request, run)
            if run.research_round_snapshot_id is not None:
                if run.research_round_snapshot_id in bound_round_ids:
                    raise ValueError("a research-round snapshot cannot be counted twice")
                bound_round_ids.add(run.research_round_snapshot_id)
        expected = build_research_process_observability_summary(self.requests, self.runs)
        if self.summary != expected:
            raise ValueError("ledger summary must be recomputed from immutable requests and runs")

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": RESEARCH_RUN_LEDGER_SCHEMA_VERSION,
            "built_at": self.built_at.isoformat(),
            "requests": [
                {**item.payload_without_id(), "snapshot_id": item.snapshot_id}
                for item in self.requests
            ],
            "runs": [
                {**item.payload_without_id(), "snapshot_id": item.snapshot_id}
                for item in self.runs
            ],
            "summary": self.summary.payload(),
            "append_only_history": True,
            "descriptive_observability_only": True,
            "predictive_skill_inference_enabled": False,
            "decision_quality_score_enabled": False,
            "portfolio_optimization_enabled": False,
            "automatic_execution_enabled": False,
        }


def bind_orchestrated_run(
    request: AnalysisRequestSnapshot,
    round_snapshot: ResearchRoundSnapshot,
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
) -> ResearchRoundRunSnapshot:
    """Bind an actual orchestrator snapshot to the exact research request."""

    _require_aware(started_at, "started_at")
    _require_aware(completed_at, "completed_at")
    if started_at < request.requested_at:
        raise ValueError("research run cannot start before its request")
    if round_snapshot.captured_at > completed_at:
        raise ValueError("research round cutoff cannot be after run completion")
    _validate_request_round_binding(request, round_snapshot)
    if (
        request.mode is ResearchRoundMode.PROSPECTIVE
        and request.requested_at > round_snapshot.captured_at
    ):
        raise ValueError("prospective round cannot predate the request that caused it")
    return ResearchRoundRunSnapshot(
        run_id=run_id,
        request_snapshot_id=request.snapshot_id,
        request_id=request.request_id,
        kind=ResearchRunKind.ORCHESTRATED,
        started_at=started_at,
        completed_at=completed_at,
        evaluation_date=request.evaluation_date,
        horizon_trading_days=request.horizon_trading_days,
        security_ids=request.security_ids,
        mode=request.mode,
        requested_lane=request.requested_lane,
        research_round_snapshot_id=round_snapshot.snapshot_id,
        round_status=round_snapshot.status,
        blockers=round_snapshot.blockers,
        flags=round_snapshot.flags,
        opportunity_set_snapshot_id=round_snapshot.opportunity_set_snapshot_id,
        expectation_overlay_snapshot_id=round_snapshot.expectation_overlay_snapshot_id,
        prospective_registration_snapshot_id=(
            round_snapshot.prospective_registration_snapshot_id
        ),
        guardrail_evidence_id=request.guardrail_evidence_id,
    )


def build_pre_orchestration_blocked_run(
    request: AnalysisRequestSnapshot,
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    blockers: tuple[ResearchRoundBlocker, ...],
    flags: tuple[str, ...] = (),
) -> ResearchRoundRunSnapshot:
    """Record a fail-closed request that could not form typed orchestrator inputs."""

    if not blockers:
        raise ValueError("pre-orchestration blocked run requires at least one blocker")
    if started_at < request.requested_at:
        raise ValueError("research run cannot start before its request")
    return ResearchRoundRunSnapshot(
        run_id=run_id,
        request_snapshot_id=request.snapshot_id,
        request_id=request.request_id,
        kind=ResearchRunKind.PRE_ORCHESTRATION_BLOCKED,
        started_at=started_at,
        completed_at=completed_at,
        evaluation_date=request.evaluation_date,
        horizon_trading_days=request.horizon_trading_days,
        security_ids=request.security_ids,
        mode=request.mode,
        requested_lane=request.requested_lane,
        research_round_snapshot_id=None,
        round_status=None,
        blockers=blockers,
        flags=flags,
        opportunity_set_snapshot_id=None,
        expectation_overlay_snapshot_id=None,
        prospective_registration_snapshot_id=None,
        guardrail_evidence_id=request.guardrail_evidence_id,
    )


def build_pre_orchestration_ready_run(
    request: AnalysisRequestSnapshot,
    *,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    flags: tuple[str, ...] = (),
) -> ResearchRoundRunSnapshot:
    """Record that typed pre-orchestration prerequisites cleared without claiming a round."""

    if started_at < request.requested_at:
        raise ValueError("research run cannot start before its request")
    return ResearchRoundRunSnapshot(
        run_id=run_id,
        request_snapshot_id=request.snapshot_id,
        request_id=request.request_id,
        kind=ResearchRunKind.PRE_ORCHESTRATION_READY,
        started_at=started_at,
        completed_at=completed_at,
        evaluation_date=request.evaluation_date,
        horizon_trading_days=request.horizon_trading_days,
        security_ids=request.security_ids,
        mode=request.mode,
        requested_lane=request.requested_lane,
        research_round_snapshot_id=None,
        round_status=None,
        blockers=(),
        flags=flags,
        opportunity_set_snapshot_id=None,
        expectation_overlay_snapshot_id=None,
        prospective_registration_snapshot_id=None,
        guardrail_evidence_id=request.guardrail_evidence_id,
    )


def build_research_run_ledger(
    requests: tuple[AnalysisRequestSnapshot, ...],
    runs: tuple[ResearchRoundRunSnapshot, ...],
    *,
    built_at: datetime,
) -> ResearchRunLedgerSnapshot:
    canonical_requests = tuple(sorted(requests, key=_request_sort_key))
    canonical_runs = tuple(sorted(runs, key=_run_sort_key))
    summary = build_research_process_observability_summary(
        canonical_requests,
        canonical_runs,
    )
    return ResearchRunLedgerSnapshot(
        built_at=built_at,
        requests=canonical_requests,
        runs=canonical_runs,
        summary=summary,
    )


def build_research_process_observability_summary(
    requests: tuple[AnalysisRequestSnapshot, ...],
    runs: tuple[ResearchRoundRunSnapshot, ...],
) -> ResearchProcessObservabilitySummary:
    statuses = Counter(
        item.round_status.value if item.round_status is not None else item.kind.value
        for item in runs
    )
    components = Counter(blocker.component for item in runs for blocker in item.blockers)
    codes = Counter(blocker.code for item in runs for blocker in item.blockers)
    blockers_per_run = [len(item.blockers) for item in runs]
    durations = [item.duration_seconds for item in runs]
    request_securities = {security for item in requests for security in item.security_ids}
    run_securities = {security for item in runs for security in item.security_ids}
    return ResearchProcessObservabilitySummary(
        request_count=len(requests),
        run_count=len(runs),
        orchestrated_run_count=sum(item.kind is ResearchRunKind.ORCHESTRATED for item in runs),
        pre_orchestration_blocked_run_count=sum(
            item.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED for item in runs
        ),
        blocked_run_count=sum(item.blocked for item in runs),
        prospective_run_count=sum(
            item.mode is ResearchRoundMode.PROSPECTIVE for item in runs
        ),
        replay_run_count=sum(item.mode is ResearchRoundMode.REPLAY for item in runs),
        prospective_registered_run_count=sum(
            item.round_status is ResearchRoundStatus.PROSPECTIVE_REGISTERED for item in runs
        ),
        opportunity_set_run_count=sum(
            item.opportunity_set_snapshot_id is not None for item in runs
        ),
        expectation_overlay_run_count=sum(
            item.expectation_overlay_snapshot_id is not None for item in runs
        ),
        unique_security_count=len(request_securities | run_securities),
        mean_blockers_per_run=(mean(blockers_per_run) if blockers_per_run else None),
        median_blockers_per_run=(median(blockers_per_run) if blockers_per_run else None),
        mean_duration_seconds=(mean(durations) if durations else None),
        median_duration_seconds=(median(durations) if durations else None),
        status_counts=tuple(sorted(statuses.items())),
        blocker_component_counts=tuple(sorted(components.items())),
        blocker_code_counts=tuple(sorted(codes.items())),
    )


def runs_for_security(
    ledger: ResearchRunLedgerSnapshot,
    security_id: str,
) -> tuple[ResearchRoundRunSnapshot, ...]:
    _require_text(security_id, "security_id")
    return tuple(item for item in ledger.runs if security_id in item.security_ids)


def latest_run_for_security(
    ledger: ResearchRunLedgerSnapshot,
    security_id: str,
) -> ResearchRoundRunSnapshot | None:
    history = runs_for_security(ledger, security_id)
    return history[-1] if history else None


def persist_analysis_request(
    snapshot: AnalysisRequestSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_content_addressed(
        "analysis_request_v2_1",
        snapshot.snapshot_id,
        snapshot.payload_without_id(),
        output_root,
    )


def persist_research_run(
    snapshot: ResearchRoundRunSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_content_addressed(
        "research_round_run_v2_1",
        snapshot.snapshot_id,
        snapshot.payload_without_id(),
        output_root,
    )


def persist_research_run_ledger(
    snapshot: ResearchRunLedgerSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_content_addressed(
        "research_run_ledger_v2_1",
        snapshot.snapshot_id,
        snapshot.payload_without_id(),
        output_root,
    )


def _validate_request_round_binding(
    request: AnalysisRequestSnapshot,
    round_snapshot: ResearchRoundSnapshot,
) -> None:
    checks = (
        (request.mode is round_snapshot.mode, "research-round mode mismatch"),
        (
            request.evaluation_date == round_snapshot.evaluation_date,
            "research-round evaluation date mismatch",
        ),
        (
            request.horizon_trading_days == round_snapshot.horizon_trading_days,
            "research-round horizon mismatch",
        ),
        (
            request.security_ids == round_snapshot.security_ids,
            "research-round security mismatch",
        ),
        (
            request.guardrail_evidence_id == round_snapshot.guardrail_evidence_id,
            "research-round guardrail mismatch",
        ),
    )
    for condition, message in checks:
        if not condition:
            raise ValueError(message)


def _validate_request_run_binding(
    request: AnalysisRequestSnapshot,
    run: ResearchRoundRunSnapshot,
) -> None:
    checks = (
        (run.request_id == request.request_id, "run request_id mismatch"),
        (run.request_snapshot_id == request.snapshot_id, "run request snapshot mismatch"),
        (run.mode is request.mode, "run mode mismatch"),
        (run.evaluation_date == request.evaluation_date, "run evaluation date mismatch"),
        (run.horizon_trading_days == request.horizon_trading_days, "run horizon mismatch"),
        (run.security_ids == request.security_ids, "run security mismatch"),
        (run.requested_lane is request.requested_lane, "run requested lane mismatch"),
        (
            run.guardrail_evidence_id == request.guardrail_evidence_id,
            "run guardrail mismatch",
        ),
        (run.started_at >= request.requested_at, "run predates request"),
    )
    for condition, message in checks:
        if not condition:
            raise ValueError(message)


def _persist_content_addressed(
    directory: str,
    snapshot_id: str,
    payload_without_id: dict[str, object],
    output_root: str | Path,
) -> Path:
    path = Path(output_root) / directory / f"{snapshot_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload_without_id)
    payload["snapshot_id"] = snapshot_id
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd: int | None = None
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if fd is not None:
            os.close(fd)
        if created:
            path.unlink(missing_ok=True)
        raise
    return path


def _request_sort_key(item: AnalysisRequestSnapshot) -> tuple[datetime, str, str]:
    return (item.requested_at, item.request_id, item.snapshot_id)


def _run_sort_key(item: ResearchRoundRunSnapshot) -> tuple[datetime, str, str]:
    return (item.completed_at, item.run_id, item.snapshot_id)


def _validate_counter_rows(values: tuple[tuple[str, int], ...], field: str) -> None:
    keys = [key for key, _ in values]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{field} cannot contain duplicate keys")
    if tuple(sorted(values)) != values:
        raise ValueError(f"{field} must be sorted")
    for key, count in values:
        _require_text(key, field)
        if count <= 0:
            raise ValueError(f"{field} counts must be positive")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in _HEX_DIGITS for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")


def _sha(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
