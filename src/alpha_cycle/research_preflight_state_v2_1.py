"""Typed current-state projection for thesis preflight without changing ledger schema v1."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import AnalysisRequestSnapshot

RESEARCH_PREFLIGHT_STATE_SCHEMA_VERSION = 1
_STATE_DIRECTORY = "research_request_preflight_state_v2_1"
_POINTER_DIRECTORY = "research_request_preflight_current_v2_1"
_POINTER_KEYS = frozenset(
    {"schema_version", "request_snapshot_id", "state_snapshot_id", "selected_at"}
)


class ResearchPreflightStateError(ValueError):
    """Raised when persisted thesis-preflight current state fails validation."""


@dataclass(frozen=True)
class ResearchThesisPreflightStateSnapshot:
    request_snapshot_id: str
    request_id: str
    mode: ResearchRoundMode
    evaluation_date: date
    horizon_trading_days: int
    security_ids: tuple[str, ...]
    research_cutoff_at: datetime
    thesis_snapshot_ids: tuple[str, ...]
    blockers: tuple[ResearchRoundBlocker, ...]
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _validate_sha(self.request_snapshot_id, "request_snapshot_id")
        _require_text(self.request_id, "request_id")
        _require_utc(self.research_cutoff_at, "research_cutoff_at")
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("preflight-state horizon must be 60, 120, or 250 trading days")
        _validate_text_tuple(self.security_ids, "security_ids")
        if not self.security_ids:
            raise ValueError("preflight state requires at least one security")
        _validate_sha_tuple(self.thesis_snapshot_ids, "thesis_snapshot_ids")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("preflight-state blockers cannot contain duplicates")

    @property
    def ready_for_package_assembly(self) -> bool:
        return not self.blockers

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": RESEARCH_PREFLIGHT_STATE_SCHEMA_VERSION,
            "request_snapshot_id": self.request_snapshot_id,
            "request_id": self.request_id,
            "mode": self.mode.value,
            "evaluation_date": self.evaluation_date.isoformat(),
            "horizon_trading_days": self.horizon_trading_days,
            "security_ids": list(self.security_ids),
            "research_cutoff_at": self.research_cutoff_at.isoformat(),
            "thesis_snapshot_ids": list(self.thesis_snapshot_ids),
            "blockers": [item.payload() for item in self.blockers],
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "ready_for_package_assembly": self.ready_for_package_assembly,
            "ledger_schema_changed": False,
            "orchestrator_executed": False,
            "investment_conclusion_created": False,
            "automatic_execution_enabled": False,
        }


@dataclass(frozen=True)
class CurrentResearchThesisPreflightState:
    selected_at: datetime
    state: ResearchThesisPreflightStateSnapshot

    def __post_init__(self) -> None:
        _require_utc(self.selected_at, "selected_at")


@dataclass(frozen=True)
class _CurrentPointer:
    request_snapshot_id: str
    state_snapshot_id: str
    selected_at: datetime

    def __post_init__(self) -> None:
        _validate_sha(self.request_snapshot_id, "request_snapshot_id")
        _validate_sha(self.state_snapshot_id, "state_snapshot_id")
        _require_utc(self.selected_at, "selected_at")


def build_research_thesis_preflight_state(
    request: AnalysisRequestSnapshot,
    *,
    research_cutoff_at: datetime,
    thesis_snapshot_ids: tuple[str, ...],
    blockers: tuple[ResearchRoundBlocker, ...],
) -> ResearchThesisPreflightStateSnapshot:
    return ResearchThesisPreflightStateSnapshot(
        request_snapshot_id=request.snapshot_id,
        request_id=request.request_id,
        mode=request.mode,
        evaluation_date=request.evaluation_date,
        horizon_trading_days=request.horizon_trading_days,
        security_ids=request.security_ids,
        research_cutoff_at=canonical_utc(research_cutoff_at),
        thesis_snapshot_ids=thesis_snapshot_ids,
        blockers=blockers,
        guardrail_evidence_id=request.guardrail_evidence_id,
    )


def persist_research_thesis_preflight_state(
    snapshot: ResearchThesisPreflightStateSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    """Atomically publish immutable state; readers never observe partial JSON."""

    directory = Path(output_root) / _STATE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot.snapshot_id}.json"
    if path.exists():
        existing = load_research_thesis_preflight_state(path)
        if existing != snapshot:
            raise ResearchPreflightStateError(
                "existing preflight-state artifact conflicts with content address"
            )
        return path

    payload = dict(snapshot.payload_without_id())
    payload["snapshot_id"] = snapshot.snapshot_id
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{snapshot.snapshot_id}.",
        suffix=".tmp",
        dir=directory,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError:
            existing = load_research_thesis_preflight_state(path)
            if existing != snapshot:
                raise ResearchPreflightStateError(
                    "concurrent preflight-state publication conflicts with content address"
                )
    finally:
        temp_path.unlink(missing_ok=True)
    return path


def publish_current_research_thesis_preflight_state(
    snapshot: ResearchThesisPreflightStateSnapshot,
    *,
    selected_at: datetime,
    output_root: str | Path,
) -> Path:
    """Atomically move a request's operational pointer without rewriting immutable history."""

    selected = canonical_utc(selected_at)
    directory = Path(output_root) / _POINTER_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot.request_snapshot_id}.json"
    if path.exists():
        prior = _load_pointer(path)
        if prior.selected_at > selected:
            raise ResearchPreflightStateError(
                "preflight-current selected_at cannot move backward"
            )
        if (
            prior.selected_at == selected
            and prior.state_snapshot_id != snapshot.snapshot_id
        ):
            raise ResearchPreflightStateError(
                "one preflight-current selected_at cannot select different states"
            )
    payload = {
        "schema_version": RESEARCH_PREFLIGHT_STATE_SCHEMA_VERSION,
        "request_snapshot_id": snapshot.request_snapshot_id,
        "state_snapshot_id": snapshot.snapshot_id,
        "selected_at": selected.isoformat(),
    }
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{snapshot.request_snapshot_id}.",
        suffix=".tmp",
        dir=directory,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return path


def load_research_thesis_preflight_state(
    path: str | Path,
) -> ResearchThesisPreflightStateSnapshot:
    source = Path(path)
    payload = _load_object(source)
    declared = _required_text(payload, "snapshot_id")
    if source.stem != declared:
        raise ResearchPreflightStateError(
            "preflight-state filename does not match declared snapshot_id"
        )
    payload_without_id = dict(payload)
    del payload_without_id["snapshot_id"]
    if _sha(payload_without_id) != declared:
        raise ResearchPreflightStateError(
            "preflight-state snapshot_id does not match persisted payload"
        )
    value = _parse_state(payload)
    if value.snapshot_id != declared:
        raise ResearchPreflightStateError(
            "typed preflight-state reconstruction changed snapshot identity"
        )
    return value


def load_current_research_thesis_preflight_states(
    artifact_root: str | Path,
) -> dict[str, CurrentResearchThesisPreflightState]:
    root = Path(artifact_root)
    pointer_directory = root / _POINTER_DIRECTORY
    state_directory = root / _STATE_DIRECTORY
    if not pointer_directory.exists():
        return {}
    result: dict[str, CurrentResearchThesisPreflightState] = {}
    for pointer_path in sorted(pointer_directory.glob("*.json")):
        pointer = _load_pointer(pointer_path)
        state = load_research_thesis_preflight_state(
            state_directory / f"{pointer.state_snapshot_id}.json"
        )
        if state.request_snapshot_id != pointer.request_snapshot_id:
            raise ResearchPreflightStateError(
                "preflight-current pointer references a different request"
            )
        result[state.request_snapshot_id] = CurrentResearchThesisPreflightState(
            selected_at=pointer.selected_at,
            state=state,
        )
    return result


def validate_preflight_state_request_binding(
    state: ResearchThesisPreflightStateSnapshot,
    request: AnalysisRequestSnapshot,
) -> None:
    checks = (
        (state.request_snapshot_id == request.snapshot_id, "request snapshot mismatch"),
        (state.request_id == request.request_id, "request id mismatch"),
        (state.mode is request.mode, "request mode mismatch"),
        (state.evaluation_date == request.evaluation_date, "evaluation date mismatch"),
        (state.horizon_trading_days == request.horizon_trading_days, "horizon mismatch"),
        (state.security_ids == request.security_ids, "security list mismatch"),
        (state.guardrail_evidence_id == request.guardrail_evidence_id, "guardrail mismatch"),
    )
    for condition, message in checks:
        if not condition:
            raise ResearchPreflightStateError(f"preflight-state {message}")


def canonical_utc(value: datetime) -> datetime:
    _require_aware(value, "datetime")
    return value.astimezone(UTC)


def _load_pointer(path: Path) -> _CurrentPointer:
    payload = _load_object(path)
    if frozenset(payload) != _POINTER_KEYS:
        raise ResearchPreflightStateError("preflight-current pointer fields are not canonical")
    if _required_int(payload, "schema_version") != RESEARCH_PREFLIGHT_STATE_SCHEMA_VERSION:
        raise ResearchPreflightStateError("unsupported preflight-current pointer schema version")
    request_snapshot_id = _required_text(payload, "request_snapshot_id")
    state_snapshot_id = _required_text(payload, "state_snapshot_id")
    if path.stem != request_snapshot_id:
        raise ResearchPreflightStateError(
            "preflight-current pointer filename does not match request_snapshot_id"
        )
    selected_at = _datetime(_required_text(payload, "selected_at"), "selected_at")
    return _CurrentPointer(
        request_snapshot_id=request_snapshot_id,
        state_snapshot_id=state_snapshot_id,
        selected_at=selected_at,
    )


def _parse_state(payload: dict[str, Any]) -> ResearchThesisPreflightStateSnapshot:
    if _required_int(payload, "schema_version") != RESEARCH_PREFLIGHT_STATE_SCHEMA_VERSION:
        raise ResearchPreflightStateError("unsupported preflight-state schema version")
    blockers = tuple(
        _parse_blocker(_object(item, "blocker"))
        for item in _required_list(payload, "blockers")
    )
    value = ResearchThesisPreflightStateSnapshot(
        request_snapshot_id=_required_text(payload, "request_snapshot_id"),
        request_id=_required_text(payload, "request_id"),
        mode=_enum(ResearchRoundMode, payload, "mode"),
        evaluation_date=_date(_required_text(payload, "evaluation_date"), "evaluation_date"),
        horizon_trading_days=_required_int(payload, "horizon_trading_days"),
        security_ids=_text_tuple(payload, "security_ids"),
        research_cutoff_at=_datetime(
            _required_text(payload, "research_cutoff_at"),
            "research_cutoff_at",
        ),
        thesis_snapshot_ids=_text_tuple(payload, "thesis_snapshot_ids"),
        blockers=blockers,
        guardrail_evidence_id=_required_text(payload, "guardrail_evidence_id"),
    )
    _require_bool(
        payload,
        "ready_for_package_assembly",
        expected=value.ready_for_package_assembly,
    )
    _require_bool(payload, "ledger_schema_changed", expected=False)
    _require_bool(payload, "orchestrator_executed", expected=False)
    _require_bool(payload, "investment_conclusion_created", expected=False)
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


def _load_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchPreflightStateError(f"cannot read preflight-state artifact: {path}") from exc
    return _object(raw, "root")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ResearchPreflightStateError(f"{field} must be a JSON object with string keys")
    return cast(dict[str, Any], value)


def _required_list(payload: dict[str, Any], field: str) -> list[object]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ResearchPreflightStateError(f"{field} must be a JSON array")
    return cast(list[object], value)


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ResearchPreflightStateError(f"{field} must be non-empty text")
    return value


def _optional_text(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ResearchPreflightStateError(f"{field} must be null or non-empty text")
    return value


def _required_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ResearchPreflightStateError(f"{field} must be an integer")
    return value


def _text_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    return tuple(_required_text({field: item}, field) for item in _required_list(payload, field))


def _datetime(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ResearchPreflightStateError(f"{field} must be an ISO datetime") from exc
    _require_aware(result, field)
    return result


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ResearchPreflightStateError(f"{field} must be an ISO date") from exc


def _enum[EnumT: StrEnum](
    enum_type: type[EnumT],
    payload: dict[str, Any],
    field: str,
) -> EnumT:
    raw = _required_text(payload, field)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise ResearchPreflightStateError(f"invalid {field}: {raw}") from exc


def _require_bool(payload: dict[str, Any], field: str, *, expected: bool) -> None:
    value = payload.get(field)
    if not isinstance(value, bool) or value is not expected:
        raise ResearchPreflightStateError(f"{field} must be {expected}")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_utc(value: datetime, field: str) -> None:
    _require_aware(value, field)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field} must be canonical UTC")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _validate_sha(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
