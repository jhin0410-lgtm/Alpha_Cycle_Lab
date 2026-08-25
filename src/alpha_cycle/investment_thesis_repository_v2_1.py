"""Typed, content-addressed repository for Decision System v2 InvestmentThesisSnapshot."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
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


@dataclass(frozen=True)
class InvestmentThesisRepositoryIndex:
    """One point-in-time scan of persisted theses, reusable across many securities."""

    as_of: datetime
    snapshots_by_id: dict[str, InvestmentThesisSnapshot]
    candidates_by_key: dict[tuple[str, int], tuple[InvestmentThesisSnapshot, ...]]

    def find_latest(
        self,
        *,
        security_id: str,
        horizon_trading_days: int,
    ) -> InvestmentThesisSnapshot | None:
        if not security_id.strip():
            raise ValueError("security_id must be non-empty text")
        candidates = self.candidates_by_key.get((security_id, horizon_trading_days), ())
        if not candidates:
            return None

        families: dict[tuple[str, str, int], list[InvestmentThesisSnapshot]] = defaultdict(list)
        for candidate in candidates:
            families[_lineage_identity(candidate)].append(candidate)
        for family in families.values():
            _validate_unforked_family(family)
            for candidate in family:
                _validate_lineage(candidate, self.snapshots_by_id)

        return max(
            candidates,
            key=lambda item: (item.captured_at, item.snapshot_version, item.snapshot_id),
        )


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

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{snapshot.snapshot_id}.",
        suffix=".tmp",
        dir=root,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # Hard-link publication is atomic and preserves O_EXCL-like no-overwrite semantics:
        # readers scanning *.json never see an empty or partially written thesis artifact.
        os.link(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            # A completed final hard link is authoritative; a hidden non-JSON temp residue is
            # non-discoverable and must not turn successful immutable publication into failure.
            pass
    return path


def load_investment_thesis(path: str | Path) -> InvestmentThesisSnapshot:
    source = Path(path)
    payload = _load_object(source)
    declared = _required_text(payload, "snapshot_id")
    if source.stem != declared:
        raise InvestmentThesisRepositoryError(
            "investment thesis filename does not match declared snapshot_id"
        )
    payload_without_id = dict(payload)
    del payload_without_id["snapshot_id"]
    if _sha(payload_without_id) != declared:
        raise InvestmentThesisRepositoryError(
            "investment thesis snapshot_id does not match persisted payload"
        )
    value = _parse_thesis(payload)
    if value.snapshot_id != declared:
        raise InvestmentThesisRepositoryError(
            "investment thesis snapshot_id does not match typed canonical payload"
        )
    return value


def build_investment_thesis_repository_index(
    artifact_root: str | Path,
    *,
    as_of: datetime,
) -> InvestmentThesisRepositoryIndex:
    """Read each discoverable thesis artifact once for one point-in-time cutoff."""

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    directory = Path(artifact_root) / _THESIS_DIRECTORY
    snapshots_by_id: dict[str, InvestmentThesisSnapshot] = {}
    candidates: dict[tuple[str, int], list[InvestmentThesisSnapshot]] = defaultdict(list)
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            value = load_investment_thesis(path)
            prior = snapshots_by_id.get(value.snapshot_id)
            if prior is not None and prior != value:
                raise InvestmentThesisRepositoryError(
                    "duplicate investment thesis snapshot_id has conflicting content"
                )
            snapshots_by_id[value.snapshot_id] = value
            if value.captured_at <= as_of:
                candidates[(value.security_id, value.horizon_trading_days)].append(value)
    return InvestmentThesisRepositoryIndex(
        as_of=as_of,
        snapshots_by_id=snapshots_by_id,
        candidates_by_key={key: tuple(values) for key, values in candidates.items()},
    )


def find_latest_investment_thesis(
    artifact_root: str | Path,
    *,
    security_id: str,
    horizon_trading_days: int,
    as_of: datetime,
) -> InvestmentThesisSnapshot | None:
    index = build_investment_thesis_repository_index(artifact_root, as_of=as_of)
    return index.find_latest(
        security_id=security_id,
        horizon_trading_days=horizon_trading_days,
    )


def _lineage_identity(snapshot: InvestmentThesisSnapshot) -> tuple[str, str, int]:
    return (
        snapshot.thesis_id,
        snapshot.security_id,
        snapshot.horizon_trading_days,
    )


def _validate_unforked_family(family: list[InvestmentThesisSnapshot]) -> None:
    versions: dict[int, str] = {}
    successors: dict[str, str] = {}
    for snapshot in family:
        prior_version_snapshot = versions.get(snapshot.snapshot_version)
        if prior_version_snapshot is not None and prior_version_snapshot != snapshot.snapshot_id:
            raise InvestmentThesisRepositoryError(
                "investment thesis lineage is forked at the same snapshot version"
            )
        versions[snapshot.snapshot_version] = snapshot.snapshot_id

        parent_id = snapshot.parent_snapshot_id
        if parent_id is None:
            continue
        prior_successor = successors.get(parent_id)
        if prior_successor is not None and prior_successor != snapshot.snapshot_id:
            raise InvestmentThesisRepositoryError(
                "investment thesis lineage has multiple successors for one parent"
            )
        successors[parent_id] = snapshot.snapshot_id


def _validate_lineage(
    snapshot: InvestmentThesisSnapshot,
    snapshots_by_id: dict[str, InvestmentThesisSnapshot],
) -> None:
    current = snapshot
    seen: set[str] = set()
    while current.snapshot_version > 1:
        if current.snapshot_id in seen:
            raise InvestmentThesisRepositoryError("investment thesis lineage contains a cycle")
        seen.add(current.snapshot_id)
        parent_id = current.parent_snapshot_id
        if parent_id is None:
            raise InvestmentThesisRepositoryError(
                "investment thesis lineage is missing a required parent_snapshot_id"
            )
        parent = snapshots_by_id.get(parent_id)
        if parent is None:
            raise InvestmentThesisRepositoryError(
                "investment thesis parent artifact is missing from the repository"
            )
        if _lineage_identity(parent) != _lineage_identity(current):
            raise InvestmentThesisRepositoryError(
                "investment thesis parent artifact belongs to a different thesis identity"
            )
        if parent.snapshot_version != current.snapshot_version - 1:
            raise InvestmentThesisRepositoryError(
                "investment thesis parent version does not immediately precede child version"
            )
        if parent.captured_at > current.captured_at:
            raise InvestmentThesisRepositoryError(
                "investment thesis parent cannot be captured after its child"
            )
        current = parent

    if current.snapshot_version != 1 or current.parent_snapshot_id is not None:
        raise InvestmentThesisRepositoryError(
            "investment thesis lineage must terminate at a parentless version-1 snapshot"
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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


def _enum[EnumT: StrEnum](
    enum_type: type[EnumT],
    payload: dict[str, Any],
    field: str,
) -> EnumT:
    raw = _required_text(payload, field)
    try:
        return enum_type(raw)
    except ValueError as exc:
        raise InvestmentThesisRepositoryError(f"invalid {field}: {raw}") from exc


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
