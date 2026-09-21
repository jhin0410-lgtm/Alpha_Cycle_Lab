"""Product R1 acceptance matrix over the shared research loop.

The harness reports external evidence blockers explicitly. Synthetic common-core
execution is useful for proving generality, but it cannot produce a real PIT or
source-authority acceptance claim by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from alpha_cycle.intelligence.counter_thesis_loop_v1 import CounterThesisPackage
from alpha_cycle.intelligence.deep_research_integration_v1 import DeepResearchPackage
from alpha_cycle.intelligence.outcome_learning_v1 import OutcomeLearningRecord
from alpha_cycle.intelligence.persisted_research_plan_v1 import PersistedResearchPlan
from alpha_cycle.intelligence.r1_source_authority_v1 import R1SourceAuthorityManifest
from alpha_cycle.intelligence.research_model_runtime_v1 import ResearchPlan


class AcceptanceStatus(StrEnum):
    ACCEPTED = "accepted"
    INCOMPLETE = "incomplete"
    BLOCKED_EXTERNAL_EVIDENCE = "blocked_external_evidence"
    FAILED_CONTRACT = "failed_contract"


class CapabilityStatus(StrEnum):
    IMPLEMENTED = "implemented"
    REAL_ACCEPTANCE_PASSED = "real_acceptance_passed"
    CONTRACT_ONLY = "contract_only"
    EVIDENCE_BLOCKED = "evidence_blocked"
    MISSING = "missing"
    FAILED_CONTRACT = "failed_contract"


CAPABILITIES: tuple[str, ...] = (
    "macro_market_observatory",
    "universe_change_detection",
    "opportunity_discovery",
    "research_planning",
    "adaptive_knowledge_packs",
    "company_transmission",
    "expectations_valuation",
    "catalyst_technical_flow",
    "counter_thesis",
    "prospective_forecast",
    "research_synthesis_decision",
    "outcome_learning",
)


@dataclass(frozen=True)
class DomainAcceptance:
    domain_id: str
    status: AcceptanceStatus
    capability_status: tuple[tuple[str, str], ...]
    blockers: tuple[str, ...]
    lineage_ids: tuple[str, ...]
    cold_start: bool = False

    def __post_init__(self) -> None:
        if tuple(name for name, _ in self.capability_status) != CAPABILITIES:
            raise ValueError("acceptance must report every R1 capability exactly once")
        for _, status in self.capability_status:
            CapabilityStatus(status)
        if len(set(self.lineage_ids)) != len(self.lineage_ids) or any(
            not item for item in self.lineage_ids
        ):
            raise ValueError("acceptance lineage must be non-empty and unique")

    @property
    def product_ready(self) -> bool:
        return (
            self.status is AcceptanceStatus.ACCEPTED
            and not self.blockers
            and bool(self.lineage_ids)
            and all(status in {
                CapabilityStatus.IMPLEMENTED.value,
                CapabilityStatus.REAL_ACCEPTANCE_PASSED.value,
            } for _, status in self.capability_status)
            and any(status == CapabilityStatus.REAL_ACCEPTANCE_PASSED.value
                    for _, status in self.capability_status)
        )


@dataclass(frozen=True)
class R1AcceptanceMatrix:
    domains: tuple[DomainAcceptance, ...]
    protected_state_unchanged: bool

    def __post_init__(self) -> None:
        expected = {"memory_semiconductor", "policy_backlog", "long_cycle_capex", "cold_start"}
        if {item.domain_id for item in self.domains} != expected:
            raise ValueError("R1 acceptance requires four heterogeneous domains")
        if len(self.domains) != 4:
            raise ValueError("R1 acceptance domains must be unique")

    @property
    def product_ready(self) -> bool:
        return self.protected_state_unchanged and all(item.product_ready for item in self.domains)

    def blockers(self) -> tuple[str, ...]:
        return tuple(
            f"{item.domain_id}:{blocker}" for item in self.domains for blocker in item.blockers
        )


def evaluate_domain(
    *,
    domain_id: str,
    plan: ResearchPlan | PersistedResearchPlan,
    research: DeepResearchPackage,
    challenge: CounterThesisPackage | None,
    learning: OutcomeLearningRecord | None,
    real_pit_evidence: bool,
    source_authority_established: bool,
    cold_start: bool = False,
) -> DomainAcceptance:
    """Report supplied runtime artifacts, never certify origin from caller flags.

    The legacy booleans are retained as assertions for diagnostics only. This
    entry point has no source-specific authentication or forecast-replay input,
    so it cannot establish full real Product R1 acceptance.
    """
    actual_plan = plan.plan if isinstance(plan, PersistedResearchPlan) else plan
    blockers: list[str] = []
    if actual_plan.domain_id != domain_id:
        blockers.append("plan_domain_mismatch")
    if research.candidate_id != actual_plan.candidate_id:
        blockers.append("research_candidate_lineage_mismatch")
    if research.plan_content_id != plan.content_id:
        blockers.append("research_plan_identity_mismatch")
    if research.current_snapshot_id != actual_plan.current_snapshot_id:
        blockers.append("research_snapshot_lineage_mismatch")
    if challenge is not None and challenge.candidate_id != actual_plan.candidate_id:
        blockers.append("challenge_candidate_lineage_mismatch")
    if challenge is not None and challenge.current_snapshot_id != actual_plan.current_snapshot_id:
        blockers.append("challenge_snapshot_lineage_mismatch")
    if (
        learning is not None
        and learning.decision is not None
        and learning.decision.candidate_id != actual_plan.candidate_id
    ):
        blockers.append("decision_candidate_lineage_mismatch")
    blockers.append(
        "real_pit_assertion_unverified" if real_pit_evidence else "real_pit_evidence_unavailable"
    )
    blockers.append(
        "source_authority_assertion_unverified" if source_authority_established
        else "source_authority_unestablished"
    )
    statuses: dict[str, str] = {
        name: CapabilityStatus.MISSING.value for name in CAPABILITIES
    }
    statuses["opportunity_discovery"] = (
        CapabilityStatus.IMPLEMENTED.value if actual_plan.candidate_lineage is not None
        else CapabilityStatus.CONTRACT_ONLY.value
    )
    statuses["research_planning"] = CapabilityStatus.IMPLEMENTED.value
    statuses["adaptive_knowledge_packs"] = (
        CapabilityStatus.CONTRACT_ONLY.value if actual_plan.pack_content_id is not None
        else CapabilityStatus.MISSING.value
    )
    statuses["company_transmission"] = (
        CapabilityStatus.EVIDENCE_BLOCKED.value
        if not research.observations
        else CapabilityStatus.CONTRACT_ONLY.value
    )
    statuses["counter_thesis"] = (
        CapabilityStatus.IMPLEMENTED.value if challenge is not None
        and challenge.observations and challenge.hypotheses and challenge.reopened_gaps
        and all(item.evidence_refs for item in challenge.observations)
        and all(item.tests and item.evidence_refs for item in challenge.hypotheses)
        else CapabilityStatus.CONTRACT_ONLY.value
        if challenge is not None
        else CapabilityStatus.MISSING.value
    )
    statuses["outcome_learning"] = (
        CapabilityStatus.CONTRACT_ONLY.value
        if learning is not None
        else CapabilityStatus.MISSING.value
    )
    statuses["expectations_valuation"] = CapabilityStatus.EVIDENCE_BLOCKED.value
    statuses["catalyst_technical_flow"] = CapabilityStatus.EVIDENCE_BLOCKED.value
    statuses["research_synthesis_decision"] = CapabilityStatus.CONTRACT_ONLY.value
    # A learning-link ID is not an immutable prospective registration receipt.
    # A pack hash is not pack replay; observations alone do not prove transmission.
    contract_failed = any(
        item
        in {
            "plan_domain_mismatch",
            "research_candidate_lineage_mismatch",
            "research_plan_identity_mismatch",
            "research_snapshot_lineage_mismatch",
            "challenge_candidate_lineage_mismatch",
            "challenge_snapshot_lineage_mismatch",
            "decision_candidate_lineage_mismatch",
        }
        for item in blockers
    )
    if contract_failed:
        statuses = {name: CapabilityStatus.FAILED_CONTRACT.value for name in CAPABILITIES}
        status = AcceptanceStatus.FAILED_CONTRACT
    else:
        status = AcceptanceStatus.INCOMPLETE
        blockers.extend(
            f"{name}:{value}" for name, value in statuses.items()
            if value not in {CapabilityStatus.IMPLEMENTED.value,
                             CapabilityStatus.REAL_ACCEPTANCE_PASSED.value}
        )
        if actual_plan.blocked:
            blockers.append("research_plan_has_open_critical_gaps")
    return DomainAcceptance(
        domain_id,
        status,
        tuple((name, statuses[name]) for name in CAPABILITIES),
        tuple(blockers),
        (actual_plan.candidate_id, actual_plan.current_snapshot_id, research.content_id),
        cold_start,
    )


def build_r1_acceptance_matrix(
    domains: tuple[DomainAcceptance, ...], *, protected_state_unchanged: bool
) -> R1AcceptanceMatrix:
    """Build the final report from independently evaluated domain results."""
    return R1AcceptanceMatrix(
        tuple(sorted(domains, key=lambda item: item.domain_id)), protected_state_unchanged
    )


def evaluate_domain_with_evidence_manifest(
    *,
    domain_id: str,
    plan: ResearchPlan | PersistedResearchPlan,
    research: DeepResearchPackage,
    challenge: CounterThesisPackage | None,
    learning: OutcomeLearningRecord | None,
    evidence: R1SourceAuthorityManifest,
    cold_start: bool = False,
) -> DomainAcceptance:
    """Evaluate acceptance using a snapshot-bound authority manifest.

    The manifest is checked against the plan's snapshot identity before its
    derived PIT and authority flags are passed into the compatibility evaluator.
    """

    actual_plan = plan.plan if isinstance(plan, PersistedResearchPlan) else plan
    if evidence.snapshot_id != actual_plan.current_snapshot_id:
        return DomainAcceptance(
            domain_id,
            AcceptanceStatus.FAILED_CONTRACT,
            tuple((name, CapabilityStatus.FAILED_CONTRACT.value) for name in CAPABILITIES),
            ("acceptance_evidence_snapshot_mismatch",),
            (actual_plan.candidate_id, actual_plan.current_snapshot_id, research.content_id),
            cold_start,
        )
    return evaluate_domain(
        domain_id=domain_id,
        plan=plan,
        research=research,
        challenge=challenge,
        learning=learning,
        real_pit_evidence=evidence.real_pit_evidence,
        source_authority_established=evidence.source_authority_established,
        cold_start=cold_start,
    )
