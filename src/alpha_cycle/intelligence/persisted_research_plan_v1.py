"""Bind research drivers to exact observations replayed by the R1-A store.

This adapter inherits upstream evidence maturity. It does not independently
certify provider semantics or upgrade captured evidence into numeric authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from alpha_cycle.intelligence.observable_universe import (
    EvidenceMaturity,
    PlannerCandidateInput,
    load_current_universe_state,
)
from alpha_cycle.intelligence.research_model_runtime_v1 import (
    KnowledgePack,
    ResearchPlan,
    build_research_plan,
)


@dataclass(frozen=True)
class DriverObservationBinding:
    driver_id: str
    member_id: str
    dimension_id: str
    metric_id: str
    unit: str
    basis: str
    window: str
    semantics: str
    maximum_age: timedelta

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.driver_id,
                self.member_id,
                self.dimension_id,
                self.metric_id,
                self.unit,
                self.basis,
                self.window,
                self.semantics,
            )
        ):
            raise ValueError("observation bindings require explicit non-empty semantics")
        if not isinstance(self.maximum_age, timedelta) or self.maximum_age < timedelta(0):
            raise ValueError("maximum observation age must be nonnegative")

    def payload(self) -> dict[str, object]:
        return {
            "driver_id": self.driver_id,
            "member_id": self.member_id,
            "dimension_id": self.dimension_id,
            "metric_id": self.metric_id,
            "unit": self.unit,
            "basis": self.basis,
            "window": self.window,
            "semantics": self.semantics,
            "maximum_age_microseconds": self.maximum_age // timedelta(microseconds=1),
        }


@dataclass(frozen=True)
class DriverEvidenceResolution:
    binding: DriverObservationBinding
    observation_id: str | None
    status: str
    evidence_refs: tuple[str, ...]
    maturity: EvidenceMaturity

    def payload(self) -> dict[str, object]:
        return {
            "binding": self.binding.payload(),
            "observation_id": self.observation_id,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "maturity": self.maturity.value,
        }


@dataclass(frozen=True)
class PersistedResearchPlan:
    plan: ResearchPlan
    resolutions: tuple[DriverEvidenceResolution, ...]

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "plan": self.plan.payload(),
            "plan_content_id": self.plan.content_id,
            "resolutions": [item.payload() for item in self.resolutions],
            "authority_policy": "inherit_observation_maturity_without_promotion",
        }

    @property
    def content_id(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()


def build_persisted_research_plan(
    candidate: PlannerCandidateInput,
    pack: KnowledgePack,
    *,
    universe_store: str | Path,
    bindings: tuple[DriverObservationBinding, ...],
) -> PersistedResearchPlan:
    """Read the current successful generation; reject stale/foreign handoffs."""
    current = load_current_universe_state(universe_store)
    if current is None:
        raise ValueError("current universe attempt is not ready")
    snapshot = current.snapshot
    if not current.ready or snapshot is None:
        raise ValueError("current universe attempt is not ready")
    if snapshot.snapshot_id != candidate.current_snapshot_id:
        raise ValueError("candidate does not reference current universe snapshot")
    if snapshot.research_cutoff_at != candidate.evaluated_at:
        raise ValueError("candidate evaluation cutoff differs from snapshot")
    members = {member.member_id: member for member in snapshot.members}
    member = members.get(candidate.member_id)
    if member is None or (member.kind, member.domain_id) != (
        candidate.member_kind,
        candidate.domain_id,
    ):
        raise ValueError("candidate member scope differs from snapshot")
    if tuple(sorted(candidate.required_dimensions)) != tuple(sorted(member.required_dimensions)):
        raise ValueError("candidate required dimensions differ from snapshot")
    if tuple(sorted(candidate.missing_dimensions)) != tuple(sorted(member.unavailable_dimensions)):
        raise ValueError("candidate missing dimensions differ from snapshot")
    if candidate.research_model_status is not member.research_model_status:
        raise ValueError("candidate research model status differs from snapshot")
    if pack.domain_id != candidate.domain_id:
        raise ValueError("candidate and knowledge pack domain mismatch")
    drivers = {driver.driver_id: driver for driver in pack.drivers}
    if len({binding.driver_id for binding in bindings}) != len(bindings):
        raise ValueError("duplicate driver observation bindings")
    if any(binding.driver_id not in drivers for binding in bindings):
        raise ValueError("binding references unknown pack driver")
    observations = {item.slot: item for item in snapshot.observations}
    available: dict[str, tuple[EvidenceMaturity, tuple[str, ...]]] = {}
    resolved: list[DriverEvidenceResolution] = []
    rank = {value: index for index, value in enumerate(EvidenceMaturity)}
    for binding in sorted(bindings, key=lambda item: item.driver_id):
        observation = observations.get((binding.member_id, binding.dimension_id))
        status = "missing"
        if observation is not None and observation.maturity is not EvidenceMaturity.UNAVAILABLE:
            if (
                observation.metric_id,
                observation.unit,
                observation.basis,
                observation.window,
                observation.semantics,
            ) != (
                binding.metric_id,
                binding.unit,
                binding.basis,
                binding.window,
                binding.semantics,
            ):
                status = "semantic_mismatch"
            elif (
                snapshot.research_cutoff_at
                - min(observation.observed_at, *(ref.available_at for ref in observation.evidence))
                > binding.maximum_age
            ):
                status = "stale"
            elif rank[observation.maturity] < rank[drivers[binding.driver_id].required_maturity]:
                status = "insufficient_maturity"
            else:
                status = "usable"
            if status in {"usable", "insufficient_maturity"}:
                available[binding.driver_id] = (
                    observation.maturity,
                    tuple(ref.reference_id for ref in observation.evidence),
                )
        resolved.append(
            DriverEvidenceResolution(
                binding,
                None if observation is None else observation.observation_id,
                status,
                ()
                if observation is None
                else tuple(ref.reference_id for ref in observation.evidence),
                EvidenceMaturity.UNAVAILABLE if observation is None else observation.maturity,
            )
        )
    return PersistedResearchPlan(
        build_research_plan(candidate, pack, available_evidence=available), tuple(resolved)
    )
