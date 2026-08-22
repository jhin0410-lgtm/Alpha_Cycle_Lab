"""Bull/base/bear payoff surfaces for Decision System v2.1 without false probability precision."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    DecisionSystemV21Guardrails,
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot

PAYOFF_SURFACE_SCHEMA_VERSION = 1
EXPECTED_SCENARIO_LABELS = ("bear", "base", "bull")


class ScenarioLabel(StrEnum):
    BEAR = "bear"
    BASE = "base"
    BULL = "bull"


@dataclass(frozen=True)
class PayoffScenario:
    """One conditional return range; it is not assigned a probability in schema v1."""

    scenario_id: str
    label: ScenarioLabel
    horizon_trading_days: int
    trigger_conditions: tuple[str, ...]
    fundamental_assumptions: tuple[str, ...]
    catalyst_refs: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]
    return_lower: float
    return_upper: float
    thesis_break_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario_id")
        if self.horizon_trading_days not in {60, 120, 250}:
            raise ValueError("payoff scenario horizon must be 60, 120, or 250 trading days")
        _validate_text_tuple(self.trigger_conditions, "trigger_conditions")
        _validate_text_tuple(self.fundamental_assumptions, "fundamental_assumptions")
        _validate_text_tuple(self.catalyst_refs, "catalyst_refs")
        _validate_sha_tuple(self.source_evidence_ids, "source_evidence_ids")
        _validate_text_tuple(self.thesis_break_conditions, "thesis_break_conditions")
        if not self.trigger_conditions:
            raise ValueError("payoff scenario requires trigger_conditions")
        if not self.fundamental_assumptions:
            raise ValueError("payoff scenario requires fundamental_assumptions")
        if not self.source_evidence_ids:
            raise ValueError("numeric payoff range requires source_evidence_ids")
        _require_finite(self.return_lower, "return_lower")
        _require_finite(self.return_upper, "return_upper")
        if self.return_lower < -1.0 or self.return_upper < -1.0:
            raise ValueError("common-equity return range cannot be below -100%")
        if self.return_upper < self.return_lower:
            raise ValueError("return_upper cannot be below return_lower")

    def payload(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label.value,
            "horizon_trading_days": self.horizon_trading_days,
            "trigger_conditions": list(self.trigger_conditions),
            "fundamental_assumptions": list(self.fundamental_assumptions),
            "catalyst_refs": list(self.catalyst_refs),
            "source_evidence_ids": list(self.source_evidence_ids),
            "return_lower": self.return_lower,
            "return_upper": self.return_upper,
            "thesis_break_conditions": list(self.thesis_break_conditions),
            "scenario_probability": None,
        }


@dataclass(frozen=True)
class PayoffSurfaceSnapshot:
    """Immutable scenario surface tied to one frozen thesis snapshot."""

    captured_at: datetime
    thesis_snapshot_id: str
    security_id: str
    horizon_trading_days: int
    scenarios: tuple[PayoffScenario, ...]
    source_snapshot_ids: tuple[str, ...]
    guardrail_evidence_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        _validate_sha(self.thesis_snapshot_id, "thesis_snapshot_id")
        _require_text(self.security_id, "security_id")
        _validate_sha_tuple(self.source_snapshot_ids, "source_snapshot_ids")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _validate_text_tuple(self.warnings, "warnings")
        labels = tuple(sorted(item.label.value for item in self.scenarios))
        if labels != EXPECTED_SCENARIO_LABELS:
            raise ValueError("payoff surface requires exactly one bear, base, and bull scenario")
        ids = tuple(item.scenario_id for item in self.scenarios)
        if len(set(ids)) != len(ids):
            raise ValueError("payoff surface scenario ids must be unique")
        for scenario in self.scenarios:
            if scenario.horizon_trading_days != self.horizon_trading_days:
                raise ValueError("all payoff scenarios must share the thesis horizon")

    def payload_without_id(self) -> dict[str, object]:
        ordered = sorted(self.scenarios, key=lambda item: item.label.value)
        return {
            "schema_version": PAYOFF_SURFACE_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "security_id": self.security_id,
            "horizon_trading_days": self.horizon_trading_days,
            "scenarios": [item.payload() for item in ordered],
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "warnings": list(self.warnings),
            "probabilities_calibrated": False,
            "expected_value_calculated": False,
            "target_price_enabled": False,
            "optimal_position_size_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())

    @property
    def worst_case_return_lower(self) -> float:
        return min(item.return_lower for item in self.scenarios)

    @property
    def best_case_return_upper(self) -> float:
        return max(item.return_upper for item in self.scenarios)


def build_payoff_surface(
    thesis: InvestmentThesisSnapshot,
    *,
    captured_at: datetime,
    scenarios: tuple[PayoffScenario, ...],
    source_snapshot_ids: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> PayoffSurfaceSnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if captured_at < thesis.captured_at:
        raise ValueError("payoff surface cannot precede the frozen thesis snapshot")
    return PayoffSurfaceSnapshot(
        captured_at=captured_at,
        thesis_snapshot_id=thesis.snapshot_id,
        security_id=thesis.security_id,
        horizon_trading_days=thesis.horizon_trading_days,
        scenarios=scenarios,
        source_snapshot_ids=source_snapshot_ids,
        guardrail_evidence_id=active.evidence_id,
        warnings=warnings,
    )


def persist_payoff_surface(
    snapshot: PayoffSurfaceSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot.snapshot_id[:12]}"
    pointer = root / "latest_payoff_surface.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot.snapshot_id:
            raise ValueError("existing payoff-surface directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            manifest = {
                "schema_version": PAYOFF_SURFACE_SCHEMA_VERSION,
                "snapshot_id": snapshot.snapshot_id,
                "captured_at": snapshot.captured_at.isoformat(),
                "thesis_snapshot_id": snapshot.thesis_snapshot_id,
                "security_id": snapshot.security_id,
                "horizon_trading_days": snapshot.horizon_trading_days,
                "scenario_count": len(snapshot.scenarios),
                "guardrail_evidence_id": snapshot.guardrail_evidence_id,
                "probabilities_calibrated": False,
                "expected_value_calculated": False,
                "target_price_enabled": False,
                "optimal_position_size_enabled": False,
                "order_api_enabled": False,
                "files": ["payoff_surface.json"],
            }
            (temporary / "payoff_surface.json").write_text(
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
            temporary.rename(directory)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
    pointer.write_text(
        json.dumps(
            {
                "schema_version": PAYOFF_SURFACE_SCHEMA_VERSION,
                "snapshot_id": snapshot.snapshot_id,
                "snapshot_path": str(directory),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pointer


def _require_finite(value: float, field: str) -> None:
    if not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _validate_text_tuple(values: tuple[str, ...], field: str) -> None:
    for value in values:
        _require_text(value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha_tuple(values: tuple[str, ...], field: str) -> None:
    for digest in values:
        _validate_sha(digest, field)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} cannot contain duplicates")


def _validate_sha(value: str, field: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return {str(key): item for key, item in cast(dict[object, object], payload).items()}


def _sha(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "PayoffScenario",
    "PayoffSurfaceSnapshot",
    "ScenarioLabel",
    "build_payoff_surface",
    "persist_payoff_surface",
]
