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


def test_four_domains_share_one_matrix_and_external_blocks_are_explicit() -> None:
    results = tuple(
        domain_result(domain)
        for domain in ("memory_semiconductor", "policy_backlog", "long_cycle_capex", "cold_start")
    )
    matrix = build_r1_acceptance_matrix(results, protected_state_unchanged=True)
    assert not matrix.product_ready
    assert all(item.status is AcceptanceStatus.BLOCKED_EXTERNAL_EVIDENCE for item in results)
    assert all("real_pit_evidence_unavailable" in item.blockers for item in results)
    assert all(
        tuple(name for name, _ in item.capability_status) == CAPABILITIES for item in results
    )
    first_statuses = dict(results[0].capability_status)
    assert first_statuses["research_planning"] == CapabilityStatus.IMPLEMENTED.value
    assert first_statuses["expectations_valuation"] == CapabilityStatus.CONTRACT_ONLY.value
    assert first_statuses["macro_market_observatory"] == CapabilityStatus.CONTRACT_ONLY.value
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


def test_lineage_and_real_evidence_can_accept_a_synthetic_domain_shape() -> None:
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
    assert result.status is AcceptanceStatus.ACCEPTED
    assert result.product_ready


def test_matrix_rejects_missing_domain_or_duplicate_domain() -> None:
    result = domain_result("memory_semiconductor")
    with pytest.raises(ValueError, match="four heterogeneous"):
        build_r1_acceptance_matrix((result,), protected_state_unchanged=True)
    with pytest.raises(ValueError, match="four heterogeneous"):
        build_r1_acceptance_matrix((result, result, result, result), protected_state_unchanged=True)
