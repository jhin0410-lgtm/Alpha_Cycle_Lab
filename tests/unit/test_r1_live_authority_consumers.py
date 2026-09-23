"""Synthetic issuance-boundary tests, not real provider acceptance receipts."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_r1_opendart_observations import selection
from test_r1_opendart_reconciliation import reconcile, setup_source
from test_r1_research_cli import args
from test_research_model_runtime_v1 import candidate, pack
from test_valuation_authority_v2_1 import CAPTURED

import alpha_cycle.intelligence.r1_opendart_reconciliation as official
import alpha_cycle.r1_research_cli as cli
from alpha_cycle.intelligence.deep_research_integration_v1 import build_deep_research_package
from alpha_cycle.intelligence.r1_acceptance_v1 import (
    AcceptanceStatus,
    evaluate_domain_with_evidence_manifest,
)
from alpha_cycle.intelligence.r1_opendart_observations import load_opendart_universe
from alpha_cycle.intelligence.r1_source_authority_v1 import build_opendart_source_authority_manifest
from alpha_cycle.intelligence.research_model_runtime_v1 import build_research_plan


def bound_inputs(tmp_path):
    source, directory = setup_source(tmp_path)
    report = reconcile(directory, source.raw_opendart)
    official._LIVE_VERIFICATIONS[report] = report.content_id
    universe = load_opendart_universe(
        directory, selections=(selection(),), universe_id="test", version="1", cutoff_at=CAPTURED,
    )
    manifest = build_opendart_source_authority_manifest(
        universe, report, decision_critical_reference_ids=universe.source_evidence_refs,
    )
    handoff = replace(
        candidate(), current_snapshot_id=universe.snapshot_id, evaluated_at=CAPTURED,
        evidence_refs=universe.source_evidence_refs,
    )
    plan = build_research_plan(handoff, pack())
    research = build_deep_research_package(plan, cutoff=CAPTURED.isoformat())
    return directory, report, manifest, plan, research


def evaluate(manifest, plan, research):
    return evaluate_domain_with_evidence_manifest(
        domain_id="memory_semiconductor", plan=plan, research=research,
        challenge=None, learning=None, evidence=manifest,
    )


def test_verified_source_clears_only_source_blockers_not_missing_execution(tmp_path):
    _, report, manifest, plan, research = bound_inputs(tmp_path)
    assert report.fresh_official_verification
    result = evaluate(manifest, plan, research)
    assert result.status is AcceptanceStatus.INCOMPLETE
    assert not result.product_ready
    assert "real_pit_assertion_unverified" not in result.blockers
    assert "source_authority_assertion_unverified" not in result.blockers
    assert manifest.content_id in result.lineage_ids
    assert "prospective_forecast:missing" in result.blockers
    assert "outcome_learning:missing" in result.blockers


def test_copied_manifest_and_foreign_cutoff_do_not_clear_source_boundary(tmp_path):
    _, report, manifest, plan, research = bound_inputs(tmp_path)
    assert report.fresh_official_verification
    copied = evaluate(replace(manifest), plan, research)
    assert "real_pit_evidence_unavailable" in copied.blockers
    assert "source_authority_unestablished" in copied.blockers
    future = replace(research, cutoff=(CAPTURED + timedelta(days=1)).isoformat(), content_id="")
    mismatch = evaluate(manifest, plan, future)
    assert mismatch.status is AcceptanceStatus.FAILED_CONTRACT
    assert "acceptance_evidence_cutoff_mismatch" in mismatch.blockers


def test_verified_but_unused_claim_cannot_clear_research_source_blockers(tmp_path):
    _, _, manifest, plan, _ = bound_inputs(tmp_path)
    unrelated = replace(plan, usable_evidence_refs=("unverified-research-ref",))
    research = build_deep_research_package(unrelated, cutoff=CAPTURED.isoformat())
    result = evaluate(manifest, unrelated, research)
    assert result.status is AcceptanceStatus.FAILED_CONTRACT
    assert "acceptance_authority_not_used_by_plan" in result.blockers


@pytest.mark.parametrize("live", [False, True])
def test_cli_exposes_narrow_issued_claims_without_promoting_product(
    tmp_path, capsys, monkeypatch, live,
):
    directory, report, _, _, _ = bound_inputs(tmp_path / "source")
    chosen = report if live else replace(report)
    monkeypatch.setattr(cli, "verify_opendart_reported_fields", lambda *a, **kw: chosen)
    code = cli.main(args(directory, tmp_path / "store") + ["--verify-official"])
    output = json.loads(capsys.readouterr().out)
    if not live:
        assert code == 2
        assert output["status"] == "failed"
        return
    assert code == 0
    assert output["claim_authority"]["real_pit_evidence"]
    assert output["claim_authority"]["source_authority_established"]
    assert not output["product_r1_accepted"]
    assert not output["provider_origin_authenticated"]
