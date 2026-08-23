"""Typed, content-addressed repository for Decision System v2 InvestmentThesisSnapshot."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from alpha_cycle.intelligence.decision_thesis_v2 import (
    CatalystClock,
    ClaimDirection,
    EpistemicStatus,
    InvestmentThesisSnapshot,
    ThesisClaim,
    ThesisStatus,
    ThesisUncertainty,
    UncertaintyDimension,
    UncertaintyLevel,
)

_THESIS_DIRECTORY = "investment_thesis_v2_1"


class InvestmentThesisRepositoryError(ValueError):
    """Raised when a persisted thesis fails typed or content-address validation."""


def persist_investment_thesis(
    snapshot: InvestmentThesisSnapshot,
    *,
    artifact_root: str | Path,
) -> Path:
    root = Path(artifact_root) / _THESIS_DIRECTORY
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{snapshot.snapshot_id}.json"
    payload = dict(snapshot.payload_without_id())
    payload["snapshot_id"] = snapshot.snapshot_id
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd: int | None = None
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
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


def load_investment_thesis(path: str | Path) -> InvestmentThesisSnapshot:
    source = Path(path)
    payload = _load_object(source)
    declared = _required_text(payload, "snapshot_id")
    if source.stem != declared:
        raise InvestmentThesisRepositoryError(
            "investment thesis filename does not match declared snapshot_id"
        )
    value = _parse_thesis(payload)
    if value.snapshot_id != declared:
        raise InvestmentThesisRepositoryError(
            "investment thesis snapshot_id does not match typed canonical payload"
        )
    return value


def find_latest_investment_thesis(
    artifact_root: str | Path,
    *,
    security_id: str,
    horizon_trading_days: int,
    as_of: datetime,
) -> InvestmentThesisSnapshot | None:
    if not security_id.strip():
        raise ValueError("security_id must be non-empty text")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    directory = Path(artifact_root) / _THESIS_DIRECTORY
    if not directory.exists():
        return None

    candidates: list[InvestmentThesisSnapshot] = []
    for path in sorted(directory.glob("*.json")):
        value = load_investment_thesis(path)
        if (
            value.security_id == security_id
            and value.horizon_trading_days == horizon_trading_days
            and value.captured_at <= as_of
        ):
            candidates.append(value)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (item.captured_at, item.snapshot_version, item.snapshot_id),
    )


def _parse_thesis(payload: dict[str, Any]) -> InvestmentThesisSnapshot:
    if _required_int(payload, "schema_version") != 1:
        raise InvestmentThesisRepositoryError("unsupported investment thesis schema version")
    claims = tuple(
        _parse_claim(_object(item, "claim"))
        for item in _required_list(payload, "claims")
    )
    catalysts = tuple(
        _parse_catalyst(_object(item, "catalyst"))
        for item in _required_list(payload, "catalysts")
    )
    uncertainty = _parse_uncertainty(_object(payload.get("uncertainty"), "uncertainty"))
    parent_raw = payload.get("parent_snapshot_id")
    parent_snapshot_id = None if parent_raw is None else _text(parent_raw, "parent_snapshot_id")
    return InvestmentThesisSnapshot(
        thesis_id=_required_text(payload, "thesis_id"),
        snapshot_version=_required_int(payload, "snapshot_version"),
        parent_snapshot_id=parent_snapshot_id,
        captured_at=_datetime(_required_text(payload, "captured_at"), "captured_at"),
        security_id=_required_text(payload, "security_id"),
        horizon_trading_days=_required_int(payload, "horizon_trading_days"),
        variant_view=_required_text(payload, "variant_view"),
        why_now=_required_text(payload, "why_now"),
        claims=claims,
        catalysts=catalysts,
        forecast_refs=_text_tuple(payload, "forecast_refs"),
        scenario_refs=_text_tuple(payload, "scenario_refs"),
        uncertainty=uncertainty,
        kill_conditions=_text_tuple(payload, "kill_conditions"),
        first_rejection_risk=_required_text(payload, "first_rejection_risk"),
        portfolio_overlap=_text_tuple(payload, "portfolio_overlap"),
        opportunity_set_refs=_text_tuple(payload, "opportunity_set_refs"),
        status=_enum(ThesisStatus, payload, "status"),
    )


def _parse_claim(payload: dict[str, Any]) -> ThesisClaim:
    return ThesisClaim(
        claim_id=_required_text(payload, "claim_id"),
        category=_required_text(payload, "category"),
        statement=_required_text(payload, "statement"),
        epistemic_status=_enum(EpistemicStatus, payload, "epistemic_status"),
        direction=_enum(ClaimDirection, payload, "direction"),
        evidence_refs=_text_tuple(payload, "evidence_refs"),
        opposing_evidence_refs=_text_tuple(payload, "opposing_evidence_refs"),
    )


def _parse_catalyst(payload: dict[str, Any]) -> CatalystClock:
    earliest_raw = payload.get("earliest_date")
    latest_raw = payload.get("latest_date")
    condition_raw = payload.get("condition")
    earliest_date = (
        None
        if earliest_raw is None
        else _date(_text(earliest_raw, "earliest_date"), "earliest_date")
    )
    latest_date = (
        None
        if latest_raw is None
        else _date(_text(latest_raw, "latest_date"), "latest_date")
    )
    return CatalystClock(
        catalyst_id=_required_text(payload, "catalyst_id"),
        statement=_required_text(payload, "statement"),
        evidence_refs=_text_tuple(payload, "evidence_refs"),
        earliest_date=earliest_date,
        latest_date=latest_date,
        condition=None if condition_raw is None else _text(condition_raw, "condition"),
    )


def _parse_uncertainty(payload: dict[str, Any]) -> ThesisUncertainty:
    return ThesisUncertainty(
        evidence=_parse_uncertainty_dimension(_object(payload.get("evidence"), "evidence")),
        model=_parse_uncertainty_dimension(_object(payload.get("model"), "model")),
        regime=_parse_uncertainty_dimension(_object(payload.get("regime"), "regime")),
        expectation=_parse_uncertainty_dimension(
            _object(payload.get("expectation"), "expectation")
        ),
        catalyst=_parse_uncertainty_dimension(_object(payload.get("catalyst"), "catalyst")),
        valuation=_parse_uncertainty_dimension(
            _object(payload.get("valuation"), "valuation")
        ),
    )


def _parse_uncertainty_dimension(payload: dict[str, Any]) -> UncertaintyDimension:
    return UncertaintyDimension(
        level=_enum(UncertaintyLevel, payload, "level"),
        rationale=_required_text(payload, "rationale"),
    )


def _load_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvestmentThesisRepositoryError(f"cannot load investment thesis: {path}") from exc
    return _object(raw, "investment thesis")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvestmentThesisRepositoryError(f"{field} must be a JSON object")
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _required_list(payload: dict[str, Any], field: str) -> list[object]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise InvestmentThesisRepositoryError(f"{field} must be a JSON array")
    return cast(list[object], value)


def _required_text(payload: dict[str, Any], field: str) -> str:
    if field not in payload:
        raise InvestmentThesisRepositoryError(f"missing field: {field}")
    return _text(payload[field], field)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvestmentThesisRepositoryError(f"{field} must be non-empty text")
    return value


def _required_int(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvestmentThesisRepositoryError(f"{field} must be an integer")
    return value


def _text_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    return tuple(_text(item, field) for item in _required_list(payload, field))


def _datetime(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvestmentThesisRepositoryError(f"{field} must be an ISO datetime") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise InvestmentThesisRepositoryError(f"{field} must be timezone-aware")
    return result


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InvestmentThesisRepositoryError(f"{field} must be an ISO date") from exc


def _enum[_EnumT: StrEnum](
    enum_type: type[_EnumT],
    payload: dict[str, Any],
    field: str,
) -> _EnumT:
    raw = _required_text(payload, field)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise InvestmentThesisRepositoryError(f"invalid {field}: {raw}") from exc
