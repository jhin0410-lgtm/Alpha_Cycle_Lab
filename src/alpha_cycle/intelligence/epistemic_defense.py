"""Independent counter-thesis and outside-graph discovery contracts for Decision System v2.1.

These objects are research evidence, not trading recommendations. They preserve independent
alternative explanations and candidate blind spots without mutating the original thesis or
turning epistemic diagnostics into a composite decision score.
"""

from __future__ import annotations

import hashlib
import json
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
from alpha_cycle.intelligence.decision_thesis_v2 import (
    EpistemicStatus,
    InvestmentThesisSnapshot,
)

EPISTEMIC_DEFENSE_SCHEMA_VERSION = 1


class MaterialityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class CounterThesisStatus(StrEnum):
    ACTIVE = "active"
    PARTIALLY_SUPPORTED = "partially_supported"
    NOT_SUPPORTED = "not_supported"
    UNRESOLVED = "unresolved"


class PromotionRecommendation(StrEnum):
    PROMOTE_TO_CRITICAL_VARIABLE = "promote_to_critical_variable"
    MONITOR = "monitor"
    REJECT_AS_IMMATERIAL = "reject_as_immaterial"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CounterExplanation:
    """One independently generated alternative explanation for thesis observations."""

    explanation_id: str
    statement: str
    mechanism: str
    epistemic_status: EpistemicStatus
    materiality: MaterialityLevel
    supporting_evidence_refs: tuple[str, ...]
    opposing_evidence_refs: tuple[str, ...]
    falsifier: str

    def __post_init__(self) -> None:
        for text_value, field in (
            (self.explanation_id, "explanation_id"),
            (self.statement, "statement"),
            (self.mechanism, "mechanism"),
            (self.falsifier, "falsifier"),
        ):
            _require_text(text_value, field)
        _validate_text_refs(self.supporting_evidence_refs, "supporting_evidence_refs")
        _validate_text_refs(self.opposing_evidence_refs, "opposing_evidence_refs")
        if self.epistemic_status in {
            EpistemicStatus.OBSERVED_FACT,
            EpistemicStatus.ACCOUNTING_IDENTITY,
            EpistemicStatus.EMPIRICALLY_VALIDATED_RELATIONSHIP,
        } and not self.supporting_evidence_refs:
            raise ValueError(
                f"{self.epistemic_status.value} counter explanation requires evidence"
            )

    def payload(self) -> dict[str, object]:
        return {
            "explanation_id": self.explanation_id,
            "statement": self.statement,
            "mechanism": self.mechanism,
            "epistemic_status": self.epistemic_status.value,
            "materiality": self.materiality.value,
            "supporting_evidence_refs": list(self.supporting_evidence_refs),
            "opposing_evidence_refs": list(self.opposing_evidence_refs),
            "falsifier": self.falsifier,
        }


@dataclass(frozen=True)
class UnresolvedContradiction:
    """Material evidence conflict kept visible until a later snapshot resolves it."""

    contradiction_id: str
    statement: str
    materiality: MaterialityLevel
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.contradiction_id, "contradiction_id")
        _require_text(self.statement, "statement")
        _validate_text_refs(self.evidence_refs, "evidence_refs")
        if not self.evidence_refs:
            raise ValueError("unresolved contradiction requires evidence_refs")

    def payload(self) -> dict[str, object]:
        return {
            "contradiction_id": self.contradiction_id,
            "statement": self.statement,
            "materiality": self.materiality.value,
            "evidence_refs": list(self.evidence_refs),
            "resolution_status": "unresolved",
        }


@dataclass(frozen=True)
class CounterThesisSnapshot:
    """Content-addressed independent challenge to one frozen thesis snapshot."""

    counter_thesis_id: str
    snapshot_version: int
    parent_snapshot_id: str | None
    thesis_snapshot_id: str
    captured_at: datetime
    created_without_thesis_support_search: bool
    independence_method: str
    search_scope: tuple[str, ...]
    strongest_alternative_explanation_id: str
    alternative_explanations: tuple[CounterExplanation, ...]
    falsification_evidence_refs: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    unresolved_contradictions: tuple[UnresolvedContradiction, ...]
    status: CounterThesisStatus
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.counter_thesis_id, "counter_thesis_id")
        _require_text(self.independence_method, "independence_method")
        _require_text(
            self.strongest_alternative_explanation_id,
            "strongest_alternative_explanation_id",
        )
        _validate_sha(self.thesis_snapshot_id, "thesis_snapshot_id")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _require_aware(self.captured_at, "captured_at")
        _validate_lineage(
            self.snapshot_version,
            self.parent_snapshot_id,
            "counter-thesis",
        )
        if not self.created_without_thesis_support_search:
            raise ValueError(
                "counter-thesis must be created independently of thesis support search"
            )
        _validate_text_refs(self.search_scope, "search_scope")
        if not self.search_scope:
            raise ValueError("counter-thesis requires an explicit search_scope")
        if not self.alternative_explanations:
            raise ValueError("counter-thesis requires at least one alternative explanation")
        _validate_unique_ids(
            tuple(item.explanation_id for item in self.alternative_explanations),
            "explanation_id",
        )
        explanation_ids = {
            item.explanation_id for item in self.alternative_explanations
        }
        if self.strongest_alternative_explanation_id not in explanation_ids:
            raise ValueError("strongest alternative explanation must exist in snapshot")
        _validate_text_refs(
            self.falsification_evidence_refs,
            "falsification_evidence_refs",
        )
        _validate_text_refs(self.missing_evidence, "missing_evidence")
        _validate_unique_ids(
            tuple(item.contradiction_id for item in self.unresolved_contradictions),
            "contradiction_id",
        )

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": EPISTEMIC_DEFENSE_SCHEMA_VERSION,
            "counter_thesis_id": self.counter_thesis_id,
            "snapshot_version": self.snapshot_version,
            "parent_snapshot_id": self.parent_snapshot_id,
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "captured_at": self.captured_at.isoformat(),
            "created_without_thesis_support_search": (
                self.created_without_thesis_support_search
            ),
            "independence_method": self.independence_method,
            "search_scope": list(self.search_scope),
            "strongest_alternative_explanation_id": (
                self.strongest_alternative_explanation_id
            ),
            "alternative_explanations": [
                item.payload() for item in self.alternative_explanations
            ],
            "falsification_evidence_refs": list(self.falsification_evidence_refs),
            "missing_evidence": list(self.missing_evidence),
            "unresolved_contradictions": [
                item.payload() for item in self.unresolved_contradictions
            ],
            "status": self.status.value,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "decision_score_enabled": False,
            "investability_decision_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class BlindSpotCandidate:
    """Variable discovered outside the current critical-state representation."""

    candidate_id: str
    variable: str
    mechanism: str
    materiality: MaterialityLevel
    evidence_refs: tuple[str, ...]
    already_covered: bool
    promotion_recommendation: PromotionRecommendation
    rationale: str

    def __post_init__(self) -> None:
        for text_value, field in (
            (self.candidate_id, "candidate_id"),
            (self.variable, "variable"),
            (self.mechanism, "mechanism"),
            (self.rationale, "rationale"),
        ):
            _require_text(text_value, field)
        _validate_text_refs(self.evidence_refs, "evidence_refs")
        if (
            self.promotion_recommendation
            is PromotionRecommendation.PROMOTE_TO_CRITICAL_VARIABLE
        ):
            if self.already_covered:
                raise ValueError("already-covered variable cannot be promoted as a blind spot")
            if not self.evidence_refs:
                raise ValueError(
                    "blind-spot promotion requires at least one evidence reference"
                )
        if self.materiality is MaterialityLevel.HIGH and not self.evidence_refs:
            raise ValueError("high-materiality blind spot requires evidence_refs")

    def payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "variable": self.variable,
            "mechanism": self.mechanism,
            "materiality": self.materiality.value,
            "evidence_refs": list(self.evidence_refs),
            "already_covered": self.already_covered,
            "promotion_recommendation": self.promotion_recommendation.value,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class BlindSpotDiscoverySnapshot:
    """Content-addressed record of one outside-graph discovery pass."""

    discovery_id: str
    snapshot_version: int
    parent_snapshot_id: str | None
    thesis_snapshot_id: str
    captured_at: datetime
    existing_critical_state_variables: tuple[str, ...]
    graph_variables_used_as_exclusion_set: bool
    search_scope: tuple[str, ...]
    discovery_method: str
    search_completed: bool
    candidates: tuple[BlindSpotCandidate, ...]
    search_limitations: tuple[str, ...]
    no_candidate_found_reason: str | None
    guardrail_evidence_id: str

    def __post_init__(self) -> None:
        _require_text(self.discovery_id, "discovery_id")
        _require_text(self.discovery_method, "discovery_method")
        _validate_sha(self.thesis_snapshot_id, "thesis_snapshot_id")
        _validate_sha(self.guardrail_evidence_id, "guardrail_evidence_id")
        _require_aware(self.captured_at, "captured_at")
        _validate_lineage(
            self.snapshot_version,
            self.parent_snapshot_id,
            "blind-spot discovery",
        )
        _validate_text_refs(
            self.existing_critical_state_variables,
            "existing_critical_state_variables",
        )
        if not self.existing_critical_state_variables:
            raise ValueError("blind-spot scan requires existing critical state variables")
        if len(self.existing_critical_state_variables) > 5:
            raise ValueError("critical state variables cannot exceed the v2.1 cap of five")
        if not self.graph_variables_used_as_exclusion_set:
            raise ValueError(
                "outside-graph discovery must exclude already represented variables"
            )
        _validate_text_refs(self.search_scope, "search_scope")
        if not self.search_scope:
            raise ValueError("blind-spot discovery requires explicit search_scope")
        if not self.search_completed:
            raise ValueError("BlindSpotDiscoverySnapshot represents only completed scans")
        _validate_unique_ids(
            tuple(item.candidate_id for item in self.candidates),
            "candidate_id",
        )
        _validate_text_refs(self.search_limitations, "search_limitations")
        if not self.search_limitations:
            raise ValueError("blind-spot discovery must document search limitations")
        if not self.candidates:
            if self.no_candidate_found_reason is None:
                raise ValueError(
                    "empty blind-spot result requires no_candidate_found_reason"
                )
            _require_text(self.no_candidate_found_reason, "no_candidate_found_reason")
        elif self.no_candidate_found_reason is not None:
            raise ValueError(
                "no_candidate_found_reason is only valid when candidates are empty"
            )

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": EPISTEMIC_DEFENSE_SCHEMA_VERSION,
            "discovery_id": self.discovery_id,
            "snapshot_version": self.snapshot_version,
            "parent_snapshot_id": self.parent_snapshot_id,
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "captured_at": self.captured_at.isoformat(),
            "existing_critical_state_variables": list(
                self.existing_critical_state_variables
            ),
            "graph_variables_used_as_exclusion_set": (
                self.graph_variables_used_as_exclusion_set
            ),
            "search_scope": list(self.search_scope),
            "discovery_method": self.discovery_method,
            "search_completed": self.search_completed,
            "candidates": [item.payload() for item in self.candidates],
            "search_limitations": list(self.search_limitations),
            "no_candidate_found_reason": self.no_candidate_found_reason,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "decision_score_enabled": False,
            "investability_decision_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


@dataclass(frozen=True)
class EpistemicDefensePackageSnapshot:
    """Binds thesis, counter-thesis, and blind-spot evidence without approving a trade."""

    captured_at: datetime
    thesis_snapshot_id: str
    counter_thesis_snapshot_id: str
    blind_spot_snapshot_id: str
    guardrail_evidence_id: str
    required_contracts_present: bool
    high_materiality_counter_explanation_count: int
    high_materiality_unresolved_contradiction_count: int
    uncovered_high_materiality_blind_spot_count: int
    blind_spot_promotion_candidate_count: int
    research_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_aware(self.captured_at, "captured_at")
        for digest_value, field in (
            (self.thesis_snapshot_id, "thesis_snapshot_id"),
            (self.counter_thesis_snapshot_id, "counter_thesis_snapshot_id"),
            (self.blind_spot_snapshot_id, "blind_spot_snapshot_id"),
            (self.guardrail_evidence_id, "guardrail_evidence_id"),
        ):
            _validate_sha(digest_value, field)
        if not self.required_contracts_present:
            raise ValueError(
                "epistemic defense package requires both v2.1 research contracts"
            )
        for count_value in (
            self.high_materiality_counter_explanation_count,
            self.high_materiality_unresolved_contradiction_count,
            self.uncovered_high_materiality_blind_spot_count,
            self.blind_spot_promotion_candidate_count,
        ):
            if count_value < 0:
                raise ValueError("epistemic diagnostic counts cannot be negative")
        _validate_text_refs(self.research_flags, "research_flags")

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": EPISTEMIC_DEFENSE_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "thesis_snapshot_id": self.thesis_snapshot_id,
            "counter_thesis_snapshot_id": self.counter_thesis_snapshot_id,
            "blind_spot_snapshot_id": self.blind_spot_snapshot_id,
            "guardrail_evidence_id": self.guardrail_evidence_id,
            "required_contracts_present": self.required_contracts_present,
            "high_materiality_counter_explanation_count": (
                self.high_materiality_counter_explanation_count
            ),
            "high_materiality_unresolved_contradiction_count": (
                self.high_materiality_unresolved_contradiction_count
            ),
            "uncovered_high_materiality_blind_spot_count": (
                self.uncovered_high_materiality_blind_spot_count
            ),
            "blind_spot_promotion_candidate_count": (
                self.blind_spot_promotion_candidate_count
            ),
            "research_flags": list(self.research_flags),
            "decision_score_enabled": False,
            "investability_decision_enabled": False,
            "automatic_execution_enabled": False,
        }

    @property
    def snapshot_id(self) -> str:
        return _sha(self.payload_without_id())


def build_counter_thesis_snapshot(
    *,
    guardrails: DecisionSystemV21Guardrails | None = None,
    **values: object,
) -> CounterThesisSnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    if not active.independent_counter_thesis_required_for_investable:
        raise ValueError(
            "active v2.1 guardrails do not require an independent counter-thesis"
        )
    if not active.counter_thesis_created_without_support_search_required:
        raise ValueError(
            "active v2.1 guardrails do not require counter-thesis independence"
        )
    payload = dict(values)
    supplied_guardrail = payload.pop("guardrail_evidence_id", None)
    if supplied_guardrail is not None and supplied_guardrail != active.evidence_id:
        raise ValueError("supplied guardrail evidence does not match active v2.1 policy")
    return CounterThesisSnapshot(
        **payload,  # type: ignore[arg-type]
        guardrail_evidence_id=active.evidence_id,
    )


def build_blind_spot_snapshot(
    *,
    guardrails: DecisionSystemV21Guardrails | None = None,
    **values: object,
) -> BlindSpotDiscoverySnapshot:
    active = guardrails or load_decision_system_v21_guardrails()
    if not active.outside_graph_discovery_required_for_investable:
        raise ValueError(
            "active v2.1 guardrails do not require outside-graph discovery"
        )
    critical = values.get("existing_critical_state_variables")
    if isinstance(critical, tuple) and len(critical) > active.critical_state_variable_max:
        raise ValueError("critical state variables exceed active v2.1 complexity budget")
    payload = dict(values)
    supplied_guardrail = payload.pop("guardrail_evidence_id", None)
    if supplied_guardrail is not None and supplied_guardrail != active.evidence_id:
        raise ValueError("supplied guardrail evidence does not match active v2.1 policy")
    return BlindSpotDiscoverySnapshot(
        **payload,  # type: ignore[arg-type]
        guardrail_evidence_id=active.evidence_id,
    )


def build_epistemic_defense_package(
    thesis: InvestmentThesisSnapshot,
    counter_thesis: CounterThesisSnapshot,
    blind_spot: BlindSpotDiscoverySnapshot,
    *,
    captured_at: datetime,
    guardrails: DecisionSystemV21Guardrails | None = None,
) -> EpistemicDefensePackageSnapshot:
    """Bind required epistemic evidence while leaving investability to a later underwriter."""

    active = guardrails or load_decision_system_v21_guardrails()
    _require_aware(captured_at, "captured_at")
    if counter_thesis.thesis_snapshot_id != thesis.snapshot_id:
        raise ValueError("counter-thesis is bound to a different thesis snapshot")
    if blind_spot.thesis_snapshot_id != thesis.snapshot_id:
        raise ValueError("blind-spot scan is bound to a different thesis snapshot")
    if counter_thesis.guardrail_evidence_id != active.evidence_id:
        raise ValueError("counter-thesis uses a different v2.1 guardrail snapshot")
    if blind_spot.guardrail_evidence_id != active.evidence_id:
        raise ValueError("blind-spot scan uses a different v2.1 guardrail snapshot")
    if counter_thesis.captured_at < thesis.captured_at:
        raise ValueError("counter-thesis cannot precede the frozen thesis snapshot")
    if blind_spot.captured_at < thesis.captured_at:
        raise ValueError("blind-spot scan cannot precede the frozen thesis snapshot")
    if captured_at < counter_thesis.captured_at or captured_at < blind_spot.captured_at:
        raise ValueError("epistemic package capture cannot precede its source snapshots")

    high_counter = sum(
        item.materiality is MaterialityLevel.HIGH
        for item in counter_thesis.alternative_explanations
    )
    high_contradictions = sum(
        item.materiality is MaterialityLevel.HIGH
        for item in counter_thesis.unresolved_contradictions
    )
    high_blind_spots = sum(
        item.materiality is MaterialityLevel.HIGH and not item.already_covered
        for item in blind_spot.candidates
    )
    promotions = sum(
        item.promotion_recommendation
        is PromotionRecommendation.PROMOTE_TO_CRITICAL_VARIABLE
        for item in blind_spot.candidates
    )
    flags: list[str] = []
    if high_counter:
        flags.append("high_materiality_counter_explanation_present")
    if high_contradictions:
        flags.append("high_materiality_unresolved_contradiction_present")
    if high_blind_spots:
        flags.append("uncovered_high_materiality_blind_spot_present")
    if promotions:
        flags.append("blind_spot_promotion_candidate_present")
    if counter_thesis.missing_evidence:
        flags.append("counter_thesis_missing_evidence_present")

    return EpistemicDefensePackageSnapshot(
        captured_at=captured_at,
        thesis_snapshot_id=thesis.snapshot_id,
        counter_thesis_snapshot_id=counter_thesis.snapshot_id,
        blind_spot_snapshot_id=blind_spot.snapshot_id,
        guardrail_evidence_id=active.evidence_id,
        required_contracts_present=True,
        high_materiality_counter_explanation_count=high_counter,
        high_materiality_unresolved_contradiction_count=high_contradictions,
        uncovered_high_materiality_blind_spot_count=high_blind_spots,
        blind_spot_promotion_candidate_count=promotions,
        research_flags=tuple(flags),
    )


def persist_counter_thesis(
    snapshot: CounterThesisSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
        "counter_thesis",
    )


def persist_blind_spot_discovery(
    snapshot: BlindSpotDiscoverySnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
        "blind_spot",
    )


def persist_epistemic_defense_package(
    snapshot: EpistemicDefensePackageSnapshot,
    *,
    output_root: str | Path,
) -> Path:
    return _persist_snapshot(
        snapshot.snapshot_id,
        snapshot.captured_at,
        snapshot.payload_without_id(),
        output_root,
        "epistemic_package",
    )


def _persist_snapshot(
    snapshot_id: str,
    captured_at: datetime,
    payload: dict[str, object],
    output_root: str | Path,
    object_type: str,
) -> Path:
    root = Path(output_root) / object_type
    root.mkdir(parents=True, exist_ok=True)
    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / f"{timestamp}__{snapshot_id[:12]}"
    pointer = root / f"latest_{object_type}.json"
    if directory.exists():
        manifest = _read_json(directory / "manifest.json")
        if str(manifest.get("snapshot_id", "")) != snapshot_id:
            raise ValueError(f"existing {object_type} directory conflicts with snapshot")
    else:
        temporary = root / f".{directory.name}.tmp"
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.mkdir()
        try:
            filename = f"{object_type}.json"
            manifest = {
                "schema_version": EPISTEMIC_DEFENSE_SCHEMA_VERSION,
                "object_type": object_type,
                "snapshot_id": snapshot_id,
                "captured_at": captured_at.isoformat(),
                "immutable": True,
                "decision_score_enabled": False,
                "investability_decision_enabled": False,
                "automatic_execution_enabled": False,
                "files": [filename],
            }
            (temporary / filename).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
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
                "schema_version": EPISTEMIC_DEFENSE_SCHEMA_VERSION,
                "object_type": object_type,
                "snapshot_id": snapshot_id,
                "snapshot_path": str(directory),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return pointer


def _validate_lineage(
    snapshot_version: int,
    parent_snapshot_id: str | None,
    object_name: str,
) -> None:
    if snapshot_version <= 0:
        raise ValueError(f"{object_name} snapshot_version must be positive")
    if snapshot_version == 1 and parent_snapshot_id is not None:
        raise ValueError(f"first {object_name} snapshot cannot have a parent")
    if snapshot_version > 1:
        if parent_snapshot_id is None:
            raise ValueError(f"later {object_name} snapshots require parent_snapshot_id")
        _validate_sha(parent_snapshot_id, "parent_snapshot_id")


def _validate_unique_ids(values: tuple[str, ...], field: str) -> None:
    for text_value in values:
        _require_text(text_value, field)
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {field} values are prohibited")


def _require_text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _validate_text_refs(values: tuple[str, ...], field: str) -> None:
    for text_value in values:
        _require_text(text_value, field)
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
    return {
        str(key): item
        for key, item in cast(dict[object, object], payload).items()
    }


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
    "BlindSpotCandidate",
    "BlindSpotDiscoverySnapshot",
    "CounterExplanation",
    "CounterThesisSnapshot",
    "CounterThesisStatus",
    "EpistemicDefensePackageSnapshot",
    "MaterialityLevel",
    "PromotionRecommendation",
    "UnresolvedContradiction",
    "build_blind_spot_snapshot",
    "build_counter_thesis_snapshot",
    "build_epistemic_defense_package",
    "persist_blind_spot_discovery",
    "persist_counter_thesis",
    "persist_epistemic_defense_package",
]
