from __future__ import annotations

from dataclasses import replace

import pytest
from test_research_model_runtime_v1 import candidate as planner_candidate
from test_research_model_runtime_v1 import pack as planner_pack

from alpha_cycle.intelligence.counter_thesis_loop_v1 import build_counter_thesis_package
from alpha_cycle.intelligence.deep_research_integration_v1 import build_deep_research_package
from alpha_cycle.intelligence.r1_acceptance_v1 import (
    CAPABILITIES,
    AcceptanceStatus,
    CapabilityStatus,
    build_r1_acceptance_matrix,
    evaluate_domain,
)
from alpha_cycle.intelligence.research_model_runtime_v1 import build_research_plan


def domain_result(domain_id: str, *, real: bool = False, authority: bool = False):
    candidate = replace(planner_candidate(), domain_id=domain_id)
    pack = replace(planner_pack(), domain_id=domain_id, content_id="")
    plan = build_research_plan(candidate, pack)
    research = build_deep_research_package(plan, cutoff="2026-09-01")
    challenge = build_counter_thesis_package(plan, observations=(), hypotheses=())
    return evaluate_domain(
        domain_id=domain_id,
        plan=plan,
        research=research,
        challenge=challenge,
        learning=None,
        real_pit_evidence=real,
        source_authority_established=authority,
        cold_start=domain_id == "cold_start",
    )


def test_four_domains_share_one_matrix_and_internal_gaps_are_explicit() -> None:
    results = tuple(
        domain_result(domain)
        for domain in ("memory_semiconductor", "policy_backlog", "long_cycle_capex", "cold_start")
    )
    matrix = build_r1_acceptance_matrix(results, protected_state_unchanged=True)
    assert not matrix.product_ready
    assert all(item.status is AcceptanceStatus.INCOMPLETE for item in results)
    assert all("real_pit_evidence_unavailable" in item.blockers for item in results)
    assert all(
        tuple(name for name, _ in item.capability_status) == CAPABILITIES for item in results
    )
    first_statuses = dict(results[0].capability_status)
    assert first_statuses["research_planning"] == CapabilityStatus.IMPLEMENTED.value
    assert first_statuses["expectations_valuation"] == CapabilityStatus.EVIDENCE_BLOCKED.value
    assert first_statuses["macro_market_observatory"] == CapabilityStatus.MISSING.value
    assert first_statuses["counter_thesis"] == CapabilityStatus.CONTRACT_ONLY.value
    assert len(set(first_statuses.values())) > 1


def test_mismatched_domain_is_contract_failure() -> None:
    plan = build_research_plan(planner_candidate(), planner_pack())
    research = build_deep_research_package(plan, cutoff="2026-09-01")
    result = evaluate_domain(
        domain_id="wrong_domain",
        plan=plan,
        research=research,
        challenge=None,
        learning=None,
        real_pit_evidence=True,
        source_authority_established=True,
    )
    assert result.status is AcceptanceStatus.FAILED_CONTRACT
    assert "plan_domain_mismatch" in result.blockers


def test_boolean_assertions_cannot_accept_a_synthetic_domain_shape() -> None:
    plan = build_research_plan(planner_candidate(), planner_pack())
    research = build_deep_research_package(plan, cutoff="2026-09-01")
    result = evaluate_domain(
        domain_id="memory_semiconductor",
        plan=plan,
        research=research,
        challenge=None,
        learning=None,
        real_pit_evidence=True,
        source_authority_established=True,
    )
    assert result.status is AcceptanceStatus.INCOMPLETE
    assert not result.product_ready
    assert "real_pit_assertion_unverified" in result.blockers
    assert "source_authority_assertion_unverified" in result.blockers
    assert CapabilityStatus.REAL_ACCEPTANCE_PASSED.value not in dict(
        result.capability_status
    ).values()


@pytest.mark.parametrize("component", ["research", "challenge"])
def test_foreign_snapshot_cannot_share_candidate_identity(component: str) -> None:
    plan = build_research_plan(planner_candidate(), planner_pack())
    research = build_deep_research_package(plan, cutoff="2026-09-01")
    challenge = build_counter_thesis_package(plan, observations=(), hypotheses=())
    if component == "research":
        research = replace(research, current_snapshot_id="a" * 64, content_id="")
    else:
        challenge = replace(challenge, current_snapshot_id="a" * 64, content_id="")
    result = evaluate_domain(
        domain_id=plan.domain_id, plan=plan, research=research, challenge=challenge,
        learning=None, real_pit_evidence=True, source_authority_established=True,
    )
    assert result.status is AcceptanceStatus.FAILED_CONTRACT
    assert f"{component}_snapshot_lineage_mismatch" in result.blockers
    assert not result.product_ready


def test_accepted_label_does_not_override_missing_capabilities_or_blockers() -> None:
    result = domain_result("memory_semiconductor")
    assert not replace(result, status=AcceptanceStatus.ACCEPTED).product_ready
    assert not replace(result, status=AcceptanceStatus.ACCEPTED, blockers=()).product_ready
    with pytest.raises(ValueError):
        replace(result, capability_status=tuple((name, "typo") for name in CAPABILITIES))


def test_matrix_rejects_missing_domain_or_duplicate_domain() -> None:
    result = domain_result("memory_semiconductor")
    with pytest.raises(ValueError, match="four heterogeneous"):
        build_r1_acceptance_matrix((result,), protected_state_unchanged=True)
    with pytest.raises(ValueError, match="four heterogeneous"):
        build_r1_acceptance_matrix((result, result, result, result), protected_state_unchanged=True)
