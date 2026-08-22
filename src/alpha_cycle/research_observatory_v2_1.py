"""Validated read-side service for the Alpha Cycle Lab Research Observatory.

This module reconstructs immutable Research Run Ledger snapshots from disk, verifies their
content-addressed identity, and projects them into UI-friendly read models. It does not run
research, mutate a thesis, rank securities, infer alpha, size positions, or execute trades.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
    ResearchRoundStatus,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    AnalysisRequestSnapshot,
    ResearchProcessObservabilitySummary,
    ResearchRoundRunSnapshot,
    ResearchRunKind,
    ResearchRunLedgerSnapshot,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane

RESEARCH_OBSERVATORY_SCHEMA_VERSION = 1
_LEDGER_DIRECTORY = "research_run_ledger_v2_1"


class ObservatoryDataError(ValueError):
    """Raised when persisted observability data fails integrity or schema validation."""


@dataclass(frozen=True)
class ResearchInboxRow:
    security_id: str
    latest_request_at: datetime
    latest_run_completed_at: datetime | None
    requested_lane: UnderwritingLane
    mode: ResearchRoundMode
    state: str
    blocker_count: int
    opportunity_set_available: bool
    expectation_overlay_available: bool
    prospective_registered: bool

    def payload(self) -> dict[str, object]:
        return {
            "security_id": self.security_id,
            "latest_request_at": self.latest_request_at.isoformat(),
            "latest_run_completed_at": (
                self.latest_run_completed_at.isoformat()
                if self.latest_run_completed_at is not None
                else None
            ),
            "requested_lane": self.requested_lane.value,
            "mode": self.mode.value,
            "state": self.state,
            "blocker_count": self.blocker_count,
            "opportunity_set_available": self.opportunity_set_available,
            "expectation_overlay_available": self.expectation_overlay_available,
            "prospective_registered": self.prospective_registered,
        }


@dataclass(frozen=True)
class BlockerInspectorRow:
    run_id: str
    completed_at: datetime
    security_id: str | None
    component: str
    code: str
    detail: str
    snapshot_id: str | None

    def payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "completed_at": self.completed_at.isoformat(),
            "security_id": self.security_id,
            "component": self.component,
            "code": self.code,
            "detail": self.detail,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class ResearchHistoryRow:
    run_id: str
    request_id: str
    completed_at: datetime
    evaluation_date: date
    horizon_trading_days: int
    security_ids: tuple[str, ...]
    requested_lane: UnderwritingLane
    mode: ResearchRoundMode
    state: str
    blocker_count: int
    duration_seconds: float

    def payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "request_id": self.request_id,
            "completed_at": self.completed_at.isoformat(),
            "evaluation_date": self.evaluation_date.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "security_ids": ", ".join(self.security_ids),
            "requested_lane": self.requested_lane.value,
            "mode": self.mode.value,
            "state": self.state,
            "blocker_count": self.blocker_count,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class ResearchObservatoryState:
    source_path: Path
    ledger: ResearchRunLedgerSnapshot
    inbox: tuple[ResearchInboxRow, ...]
    blockers: tuple[BlockerInspectorRow, ...]
    history: tuple[ResearchHistoryRow, ...]

    @property
    def snapshot_id(self) -> str:
        return self.ledger.snapshot_id

    def health_payload(self) -> dict[str, object]:
        return {
            "schema_version": RESEARCH_OBSERVATORY_SCHEMA_VERSION,
            "ledger_snapshot_id": self.ledger.snapshot_id,
            "ledger_built_at": self.ledger.built_at.isoformat(),
            "source_path": str(self.source_path),
            "request_count": len(self.ledger.requests),
            "run_count": len(self.ledger.runs),
            "append_only_history": True,
            "content_address_verified": True,
            "read_only_adapter": True,
            "investment_logic_reimplemented": False,
            "predictive_skill_inference_enabled": False,
            "portfolio_optimization_enabled": False,
            "automatic_execution_enabled": False,
        }


def load_latest_observatory_state(artifact_root: str | Path) -> ResearchObservatoryState | None:
    """Load the newest valid ledger by embedded built_at, not filesystem modification time."""

    directory = Path(artifact_root) / _LEDGER_DIRECTORY
    if not directory.exists():
        return None
    paths = tuple(sorted(directory.glob("*.json")))
    if not paths:
        return None
    ledgers = tuple((path, load_research_run_ledger(path)) for path in paths)
    source_path, ledger = max(
        ledgers,
        key=lambda item: (item[1].built_at, item[1].snapshot_id),
    )
    return build_observatory_state(source_path, ledger)


def load_research_run_ledger(path: str | Path) -> ResearchRunLedgerSnapshot:
    """Reconstruct a typed ledger and verify its declared content-addressed identity."""

    source = Path(path)
    payload = _load_object(source)
    declared_snapshot_id = _required_text(payload, "snapshot_id")
    payload_without_id = dict(payload)
    del payload_without_id["snapshot_id"]
    computed_snapshot_id = _sha(payload_without_id)
    if computed_snapshot_id != declared_snapshot_id:
        raise ObservatoryDataError("ledger snapshot_id does not match persisted payload")
    if source.stem != declared_snapshot_id:
        raise ObservatoryDataError("ledger filename does not match declared snapshot_id")
    if _required_int(payload, "schema_version") != 1:
        raise ObservatoryDataError("unsupported research-run ledger schema version")

    requests_raw = _required_list(payload, "requests")
    runs_raw = _required_list(payload, "runs")
    requests = tuple(_parse_request(_object(item, "request")) for item in requests_raw)
    runs = tuple(_parse_run(_object(item, "run")) for item in runs_raw)
    summary = _parse_summary(_object(payload.get("summary"), "summary"))
    ledger = ResearchRunLedgerSnapshot(
        built_at=_datetime(_required_text(payload, "built_at"), "built_at"),
        requests=requests,
        runs=runs,
        summary=summary,
    )
    if ledger.snapshot_id != declared_snapshot_id:
        raise ObservatoryDataError("typed ledger reconstruction changed snapshot identity")
    _require_bool(payload, "append_only_history", expected=True)
    _require_bool(payload, "descriptive_observability_only", expected=True)
    _require_bool(payload, "predictive_skill_inference_enabled", expected=False)
    _require_bool(payload, "decision_quality_score_enabled", expected=False)
    _require_bool(payload, "portfolio_optimization_enabled", expected=False)
    _require_bool(payload, "automatic_execution_enabled", expected=False)
    return ledger


def build_observatory_state(
    source_path: str | Path,
    ledger: ResearchRunLedgerSnapshot,
) -> ResearchObservatoryState:
    return ResearchObservatoryState(
        source_path=Path(source_path),
        ledger=ledger,
        inbox=build_research_inbox(ledger),
        blockers=build_blocker_inspector(ledger),
        history=build_research_history(ledger),
    )


def build_research_inbox(
    ledger: ResearchRunLedgerSnapshot,
) -> tuple[ResearchInboxRow, ...]:
    latest_requests: dict[str, AnalysisRequestSnapshot] = {}
    latest_runs: dict[str, ResearchRoundRunSnapshot] = {}
    for request in ledger.requests:
        for security_id in request.security_ids:
            current = latest_requests.get(security_id)
            if current is None or _request_key(request) > _request_key(current):
                latest_requests[security_id] = request
    for run in ledger.runs:
        for security_id in run.security_ids:
            current = latest_runs.get(security_id)
            if current is None or _run_key(run) > _run_key(current):
                latest_runs[security_id] = run

    rows: list[ResearchInboxRow] = []
    for security_id in sorted(latest_requests):
        request = latest_requests[security_id]
        run = latest_runs.get(security_id)
        if run is None or run.started_at < request.requested_at:
            rows.append(
                ResearchInboxRow(
                    security_id=security_id,
                    latest_request_at=request.requested_at,
                    latest_run_completed_at=(run.completed_at if run is not None else None),
                    requested_lane=request.requested_lane,
                    mode=request.mode,
                    state="request_pending",
                    blocker_count=0,
                    opportunity_set_available=False,
                    expectation_overlay_available=False,
                    prospective_registered=False,
                )
            )
            continue
        rows.append(
            ResearchInboxRow(
                security_id=security_id,
                latest_request_at=request.requested_at,
                latest_run_completed_at=run.completed_at,
                requested_lane=run.requested_lane,
                mode=run.mode,
                state=_run_state(run),
                blocker_count=len(run.blockers),
                opportunity_set_available=run.opportunity_set_snapshot_id is not None,
                expectation_overlay_available=run.expectation_overlay_snapshot_id is not None,
                prospective_registered=(
                    run.prospective_registration_snapshot_id is not None
                ),
            )
        )
    return tuple(rows)


def build_blocker_inspector(
    ledger: ResearchRunLedgerSnapshot,
) -> tuple[BlockerInspectorRow, ...]:
    rows = [
        BlockerInspectorRow(
            run_id=run.run_id,
            completed_at=run.completed_at,
            security_id=blocker.security_id,
            component=blocker.component,
            code=blocker.code,
            detail=blocker.detail,
            snapshot_id=blocker.snapshot_id,
        )
        for run in reversed(ledger.runs)
        for blocker in run.blockers
    ]
    return tuple(rows)


def build_research_history(
    ledger: ResearchRunLedgerSnapshot,
) -> tuple[ResearchHistoryRow, ...]:
    return tuple(
        ResearchHistoryRow(
            run_id=run.run_id,
            request_id=run.request_id,
            completed_at=run.completed_at,
            evaluation_date=run.evaluation_date,
            horizon_trading_days=run.horizon_trading_days,
            security_ids=run.security_ids,
            requested_lane=run.requested_lane,
            mode=run.mode,
            state=_run_state(run),
            blocker_count=len(run.blockers),
            duration_seconds=run.duration_seconds,
        )
        for run in reversed(ledger.runs)
    )


def _parse_request(payload: dict[str, Any]) -> AnalysisRequestSnapshot:
    _require_bool(payload, "append_only_request", expected=True)
    snapshot_id = _required_text(payload, "snapshot_id")
    value = AnalysisRequestSnapshot(
        request_id=_required_text(payload, "request_id"),
        requested_at=_datetime(_required_text(payload, "requested_at"), "requested_at"),
        evaluation_date=_date(_required_text(payload, "evaluation_date"), "evaluation_date"),
        horizon_trading_days=_required_int(payload, "horizon_trading_days"),
        security_ids=_text_tuple(payload, "security_ids"),
        mode=_enum(ResearchRoundMode, payload, "mode"),
        requested_lane=_enum(UnderwritingLane, payload, "requested_lane"),
        request_text=_required_text(payload, "request_text"),
        guardrail_evidence_id=_required_text(payload, "guardrail_evidence_id"),
        tags=_text_tuple(payload, "tags"),
    )
    if value.snapshot_id != snapshot_id:
        raise ObservatoryDataError("analysis request snapshot identity mismatch")
    return value


def _parse_run(payload: dict[str, Any]) -> ResearchRoundRunSnapshot:
    snapshot_id = _required_text(payload, "snapshot_id")
    blockers = tuple(
        _parse_blocker(_object(item, "blocker"))
        for item in _required_list(payload, "blockers")
    )
    round_status_raw = payload.get("round_status")
    round_status = (
        None
        if round_status_raw is None
        else _enum_value(ResearchRoundStatus, round_status_raw, "round_status")
    )
    value = ResearchRoundRunSnapshot(
        run_id=_required_text(payload, "run_id"),
        request_snapshot_id=_required_text(payload, "request_snapshot_id"),
        request_id=_required_text(payload, "request_id"),
        kind=_enum(ResearchRunKind, payload, "kind"),
        started_at=_datetime(_required_text(payload, "started_at"), "started_at"),
        completed_at=_datetime(_required_text(payload, "completed_at"), "completed_at"),
        evaluation_date=_date(_required_text(payload, "evaluation_date"), "evaluation_date"),
        horizon_trading_days=_required_int(payload, "horizon_trading_days"),
        security_ids=_text_tuple(payload, "security_ids"),
        mode=_enum(ResearchRoundMode, payload, "mode"),
        requested_lane=_enum(UnderwritingLane, payload, "requested_lane"),
        research_round_snapshot_id=_optional_text(payload, "research_round_snapshot_id"),
        round_status=round_status,
        blockers=blockers,
        flags=_text_tuple(payload, "flags"),
        opportunity_set_snapshot_id=_optional_text(payload, "opportunity_set_snapshot_id"),
        expectation_overlay_snapshot_id=_optional_text(
            payload,
            "expectation_overlay_snapshot_id",
        ),
        prospective_registration_snapshot_id=_optional_text(
            payload,
            "prospective_registration_snapshot_id",
        ),
        guardrail_evidence_id=_required_text(payload, "guardrail_evidence_id"),
    )
    if value.snapshot_id != snapshot_id:
        raise ObservatoryDataError("research run snapshot identity mismatch")
    duration = payload.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        raise ObservatoryDataError("duration_seconds must be numeric")
    if abs(float(duration) - value.duration_seconds) > 1e-9:
        raise ObservatoryDataError("persisted duration_seconds does not match timestamps")
    _require_bool(payload, "descriptive_observability_only", expected=True)
    _require_bool(payload, "predictive_skill_inference_enabled", expected=False)
    _require_bool(payload, "weighted_score_training_enabled", expected=False)
    _require_bool(payload, "portfolio_optimization_enabled", expected=False)
    _require_bool(payload, "automatic_execution_enabled", expected=False)
    return value


def _parse_blocker(payload: dict[str, Any]) -> ResearchRoundBlocker:
    return ResearchRoundBlocker(
        component=_required_text(payload, "component"),
        code=_required_text(payload, "code"),
        detail=_required_text(payload, "detail"),
        security_id=_optional_text(payload, "security_id"),
        snapshot_id=_optional_text(payload, "snapshot_id"),
    )


def _parse_summary(payload: dict[str, Any]) -> ResearchProcessObservabilitySummary:
    _require_bool(payload, "process_metrics_only", expected=True)
    _require_bool(payload, "investment_alpha_claimed", expected=False)
    _require_bool(payload, "forecast_calibration_claimed", expected=False)
    return ResearchProcessObservabilitySummary(
        request_count=_required_int(payload, "request_count"),
        run_count=_required_int(payload, "run_count"),
        orchestrated_run_count=_required_int(payload, "orchestrated_run_count"),
        pre_orchestration_blocked_run_count=_required_int(
            payload,
            "pre_orchestration_blocked_run_count",
        ),
        blocked_run_count=_required_int(payload, "blocked_run_count"),
        prospective_run_count=_required_int(payload, "prospective_run_count"),
        replay_run_count=_required_int(payload, "replay_run_count"),
        prospective_registered_run_count=_required_int(
            payload,
            "prospective_registered_run_count",
        ),
        opportunity_set_run_count=_required_int(payload, "opportunity_set_run_count"),
        expectation_overlay_run_count=_required_int(
            payload,
            "expectation_overlay_run_count",
        ),
        unique_security_count=_required_int(payload, "unique_security_count"),
        mean_blockers_per_run=_optional_number(payload, "mean_blockers_per_run"),
        median_blockers_per_run=_optional_number(payload, "median_blockers_per_run"),
        mean_duration_seconds=_optional_number(payload, "mean_duration_seconds"),
        median_duration_seconds=_optional_number(payload, "median_duration_seconds"),
        status_counts=_counter_rows(payload, "status_counts"),
        blocker_component_counts=_counter_rows(payload, "blocker_component_counts"),
        blocker_code_counts=_counter_rows(payload, "blocker_code_counts"),
    )


def _run_state(run: ResearchRoundRunSnapshot) -> str:
    if run.round_status is not None:
        return run.round_status.value
    return run.kind.value


def _request_key(item: AnalysisRequestSnapshot) -> tuple[datetime, str, str]:
    return (item.requested_at, item.request_id, item.snapshot_id)


def _run_key(item: ResearchRoundRunSnapshot) -> tuple[datetime, str, str]:
    return (item.completed_at, item.run_id, item.snapshot_id)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservatoryDataError(f"cannot read observatory artifact: {path}") from exc
    return _object(raw, "root")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ObservatoryDataError(f"{field} must be a JSON object with string keys")
    return cast(dict[str, Any], value)


def _required_list(payload: dict[str, Any], field: str) -> list[object]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ObservatoryDataError(f"{field} must be a JSON array")
    return cast(list[object], value)


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ObservatoryDataError(f"{field} must be non-empty text")
    return value


def _optional_text(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ObservatoryDataError(f"{field} must be null or non-empty text")
    return value


def _required_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ObservatoryDataError(f"{field} must be an integer")
    return value


def _optional_number(payload: dict[str, Any], field: str) -> float | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ObservatoryDataError(f"{field} must be numeric or null")
    return float(value)


def _require_bool(payload: dict[str, Any], field: str, *, expected: bool) -> None:
    value = payload.get(field)
    if not isinstance(value, bool) or value is not expected:
        raise ObservatoryDataError(f"{field} must be {expected}")


def _text_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    values = _required_list(payload, field)
    if any(not isinstance(value, str) for value in values):
        raise ObservatoryDataError(f"{field} must contain only text values")
    return tuple(cast(str, value) for value in values)


def _counter_rows(payload: dict[str, Any], field: str) -> tuple[tuple[str, int], ...]:
    rows = _required_list(payload, field)
    result: list[tuple[str, int]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise ObservatoryDataError(f"{field} rows must be [key, count] pairs")
        key, count = row
        if not isinstance(key, str) or not isinstance(count, int) or isinstance(count, bool):
            raise ObservatoryDataError(f"{field} rows contain invalid values")
        result.append((key, count))
    return tuple(result)


def _datetime(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ObservatoryDataError(f"{field} is not an ISO datetime") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ObservatoryDataError(f"{field} must be timezone-aware")
    return result


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ObservatoryDataError(f"{field} is not an ISO date") from exc


def _enum(enum_type: type[Any], payload: dict[str, Any], field: str) -> Any:
    return _enum_value(enum_type, payload.get(field), field)


def _enum_value(enum_type: type[Any], value: object, field: str) -> Any:
    if not isinstance(value, str):
        raise ObservatoryDataError(f"{field} must be text")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ObservatoryDataError(f"{field} has an unsupported enum value") from exc


def _sha(payload: dict[str, object] | dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
