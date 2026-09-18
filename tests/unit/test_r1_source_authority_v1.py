from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from test_observable_universe import snapshot
from test_research_model_runtime_v1 import candidate, pack

from alpha_cycle.intelligence.deep_research_integration_v1 import build_deep_research_package
from alpha_cycle.intelligence.r1_acceptance_v1 import evaluate_domain_with_evidence_manifest
from alpha_cycle.intelligence.r1_source_authority_v1 import (
    build_r1_source_authority_manifest,
)
from alpha_cycle.intelligence.research_model_runtime_v1 import build_research_plan


def test_manifest_binds_exact_pit_cutoff_and_authority() -> None:
    current = snapshot(cutoff=datetime(2026, 9, 1, tzinfo=UTC))
    reference_id = current.source_evidence_refs[0]
    manifest = build_r1_source_authority_manifest(
        current,
        research_cutoff_at=current.research_cutoff_at,
        authenticated_reference_ids=(reference_id,),
        authority_ids=("provider:fixture",),
    )
    assert manifest.snapshot_id == current.snapshot_id
    assert manifest.real_pit_evidence
    assert manifest.source_authority_established
    assert len(manifest.content_id) == 64


def test_manifest_rejects_cutoff_or_undefined_authenticated_reference() -> None:
    current = snapshot()
    with pytest.raises(ValueError, match="exactly match"):
        build_r1_source_authority_manifest(
            current,
            research_cutoff_at=datetime(2026, 8, 2, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="exist in the snapshot"):
        build_r1_source_authority_manifest(
            current,
            research_cutoff_at=current.research_cutoff_at,
            authenticated_reference_ids=("missing",),
        )


def test_manifest_without_authentication_stays_blocked() -> None:
    current = snapshot()
    manifest = build_r1_source_authority_manifest(
        current, research_cutoff_at=current.research_cutoff_at
    )
    assert manifest.real_pit_evidence
    assert not manifest.source_authority_established


def test_acceptance_consumes_manifest_and_rejects_plan_snapshot_mismatch() -> None:
    current = snapshot(cutoff=datetime(2026, 9, 1, tzinfo=UTC))
    plan = build_research_plan(
        replace(candidate(), current_snapshot_id=current.snapshot_id), pack()
    )
    research = build_deep_research_package(plan, cutoff="2026-09-01")
    evidence = build_r1_source_authority_manifest(
        current, research_cutoff_at=current.research_cutoff_at
    )
    result = evaluate_domain_with_evidence_manifest(
        domain_id=plan.domain_id,
        plan=plan,
        research=research,
        challenge=None,
        learning=None,
        evidence=evidence,
    )
    assert "source_authority_unestablished" in result.blockers
    assert result.status.value == "blocked_external_evidence"
