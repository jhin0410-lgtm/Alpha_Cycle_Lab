"""Industry-specific research contracts for deep vertical investment analysis.

A sector vertical is not a universal factor score.  It is a declaration of the
sector-specific evidence that must exist before Alpha Cycle can claim that it has
analysed the macro-to-earnings-to-expectations-to-price chain for that sector.

Coverage is descriptive only.  Missing evidence is never converted into a zero
investment score, and partial/blocked evidence never becomes certified evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

_ALLOWED_PRIORITIES = frozenset({"required", "important", "context"})
_ALLOWED_STATUSES = frozenset({"available", "partial", "blocked", "missing"})


@dataclass(frozen=True)
class SectorEvidenceRequirement:
    """One sector-specific research question and its evidence boundary."""

    key: str
    label: str
    domain: str
    priority: str
    rationale: str
    preferred_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.key or not self.key.replace("_", "").isalnum():
            raise ValueError("Sector requirement key must be non-empty snake_case")
        if not self.label.strip() or not self.domain.strip() or not self.rationale.strip():
            raise ValueError("Sector requirement label/domain/rationale cannot be blank")
        if self.priority not in _ALLOWED_PRIORITIES:
            raise ValueError(f"Unsupported sector requirement priority: {self.priority}")
        if any(not str(source).strip() for source in self.preferred_sources):
            raise ValueError("Sector preferred source names cannot be blank")


@dataclass(frozen=True)
class SectorRequirementState:
    """Observed support for one requirement at one evaluation point."""

    requirement_key: str
    status: str
    evidence_summary: str
    source_scope: str | None = None
    blocker: str | None = None

    def __post_init__(self) -> None:
        if not self.requirement_key.strip():
            raise ValueError("Sector requirement state key cannot be blank")
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError(f"Unsupported sector requirement status: {self.status}")
        if not self.evidence_summary.strip():
            raise ValueError("Sector requirement evidence summary cannot be blank")
        if self.status in {"blocked", "missing"} and not str(self.blocker or "").strip():
            raise ValueError("Blocked/missing sector evidence must explain the blocker")


@dataclass(frozen=True)
class SectorVerticalDefinition:
    """Research contract for one industry."""

    sector_id: str
    display_name: str
    thesis_question: str
    requirements: tuple[SectorEvidenceRequirement, ...]
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.sector_id or not self.sector_id.replace("_", "").isalnum():
            raise ValueError("sector_id must be non-empty snake_case")
        if not self.display_name.strip() or not self.thesis_question.strip():
            raise ValueError("Sector display name and thesis question cannot be blank")
        if not self.requirements:
            raise ValueError("Sector vertical requires at least one evidence requirement")
        keys = [requirement.key for requirement in self.requirements]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Sector vertical repeats requirement keys: {self.sector_id}")
        if self.decision_score_enabled:
            raise ValueError("Sector vertical coverage must remain non-scoring")

    @property
    def requirement_keys(self) -> tuple[str, ...]:
        return tuple(requirement.key for requirement in self.requirements)

    def requirement(self, key: str) -> SectorEvidenceRequirement:
        for requirement in self.requirements:
            if requirement.key == key:
                return requirement
        raise KeyError(key)


@dataclass(frozen=True)
class SectorVerticalCoverage:
    """Coverage state for one company under one sector research contract."""

    sector_id: str
    ticker: str
    readiness_status: str
    required_available: int
    required_total: int
    important_available: int
    important_total: int
    missing_required: tuple[str, ...]
    partial_required: tuple[str, ...]
    blocked_required: tuple[str, ...]
    missing_important: tuple[str, ...]
    states: tuple[SectorRequirementState, ...]
    decision_score_enabled: bool = False

    def __post_init__(self) -> None:
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("Sector coverage ticker must be a six-digit code")
        if self.readiness_status not in {
            "deep_research_contract_covered",
            "required_evidence_partial",
            "required_evidence_blocked",
            "required_evidence_missing",
        }:
            raise ValueError(f"Unsupported sector readiness status: {self.readiness_status}")
        if self.required_available < 0 or self.required_available > self.required_total:
            raise ValueError("Invalid required evidence coverage count")
        if self.important_available < 0 or self.important_available > self.important_total:
            raise ValueError("Invalid important evidence coverage count")
        if self.decision_score_enabled:
            raise ValueError("Sector vertical coverage must remain non-scoring")

    def as_dict(self) -> dict[str, object]:
        return {
            "sector_id": self.sector_id,
            "ticker": self.ticker,
            "readiness_status": self.readiness_status,
            "required_available": self.required_available,
            "required_total": self.required_total,
            "important_available": self.important_available,
            "important_total": self.important_total,
            "missing_required": list(self.missing_required),
            "partial_required": list(self.partial_required),
            "blocked_required": list(self.blocked_required),
            "missing_important": list(self.missing_important),
            "states": [
                {
                    "requirement_key": state.requirement_key,
                    "status": state.status,
                    "evidence_summary": state.evidence_summary,
                    "source_scope": state.source_scope,
                    "blocker": state.blocker,
                }
                for state in self.states
            ],
            "decision_score_enabled": False,
        }


def evaluate_sector_vertical_coverage(
    definition: SectorVerticalDefinition,
    ticker: str,
    states: Mapping[str, SectorRequirementState],
) -> SectorVerticalCoverage:
    """Evaluate research completeness without changing an investment score."""

    normalized_ticker = str(ticker).strip().zfill(6)
    unknown = set(states) - set(definition.requirement_keys)
    if unknown:
        raise ValueError(
            f"Sector coverage contains undeclared requirements for {definition.sector_id}: "
            + ",".join(sorted(unknown))
        )

    ordered_states: list[SectorRequirementState] = []
    missing_required: list[str] = []
    partial_required: list[str] = []
    blocked_required: list[str] = []
    missing_important: list[str] = []
    required_total = 0
    required_available = 0
    important_total = 0
    important_available = 0

    for requirement in definition.requirements:
        state = states.get(
            requirement.key,
            SectorRequirementState(
                requirement_key=requirement.key,
                status="missing",
                evidence_summary="연결된 증거가 없습니다.",
                blocker="required_source_not_connected",
            ),
        )
        if state.requirement_key != requirement.key:
            raise ValueError("Sector requirement state key does not match definition key")
        ordered_states.append(state)
        if requirement.priority == "required":
            required_total += 1
            if state.status == "available":
                required_available += 1
            elif state.status == "partial":
                partial_required.append(requirement.key)
            elif state.status == "blocked":
                blocked_required.append(requirement.key)
            else:
                missing_required.append(requirement.key)
        elif requirement.priority == "important":
            important_total += 1
            if state.status == "available":
                important_available += 1
            elif state.status != "available":
                missing_important.append(requirement.key)

    if missing_required:
        readiness = "required_evidence_missing"
    elif blocked_required:
        readiness = "required_evidence_blocked"
    elif partial_required:
        readiness = "required_evidence_partial"
    else:
        readiness = "deep_research_contract_covered"

    return SectorVerticalCoverage(
        sector_id=definition.sector_id,
        ticker=normalized_ticker,
        readiness_status=readiness,
        required_available=required_available,
        required_total=required_total,
        important_available=important_available,
        important_total=important_total,
        missing_required=tuple(missing_required),
        partial_required=tuple(partial_required),
        blocked_required=tuple(blocked_required),
        missing_important=tuple(missing_important),
        states=tuple(ordered_states),
        decision_score_enabled=False,
    )


__all__ = [
    "SectorEvidenceRequirement",
    "SectorRequirementState",
    "SectorVerticalCoverage",
    "SectorVerticalDefinition",
    "evaluate_sector_vertical_coverage",
]
