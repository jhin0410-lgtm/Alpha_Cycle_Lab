from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_research_model_runtime_v1 import candidate, pack

from alpha_cycle.intelligence.cold_start_research_v1 import (
    ColdStartProposalRepository,
    ColdStartRequest,
    accept_cold_start_response,
)
from alpha_cycle.intelligence.knowledge_pack_repository_v1 import KnowledgePackRepository
from alpha_cycle.intelligence.observable_universe import ResearchModelStatus
from alpha_cycle.intelligence.research_model_runtime_v1 import PackLifecycle, build_research_plan


def request() -> ColdStartRequest:
    return ColdStartRequest(candidate(), "cold-start-1", datetime(2026, 9, 1, 1, tzinfo=UTC))


def response(req: ColdStartRequest) -> str:
    draft = pack(PackLifecycle.DRAFT)
    draft = replace(
        draft,
        version=req.proposed_version,
        domain_id=req.candidate.domain_id or "",
        drivers=tuple(
            replace(driver, source_requirements=("proposed source plan",))
            for driver in draft.drivers
        ),
        content_id="",
    )
    return json.dumps(
        {
            "request_id": req.request_id,
            "proposed_at": req.requested_at.isoformat(),
            "model_label": "synthetic-test-model",
            "knowledge_pack": draft.payload_without_id(),
        }
    )


def test_model_exchange_persist_replay_install_and_plan(tmp_path: Path) -> None:
    req = request()
    assert req.message()["request_id"] == req.request_id
    store = ColdStartProposalRepository(tmp_path / "proposals.sqlite")
    proposal = store.record(req, response(req))
    replay = ColdStartProposalRepository(store.path).replay(req, proposal.proposal_id)
    assert replay == proposal
    assert store.record(req, response(req)) == proposal
    registry = KnowledgePackRepository(tmp_path / "packs.sqlite")
    registry.publish(replay.pack)
    installed = registry.load(req.candidate.domain_id or "", req.proposed_version)
    plan = build_research_plan(req.candidate, installed)
    assert plan.blocked
    assert plan.pack_lifecycle is PackLifecycle.DRAFT
    assert all(gap.critical for gap in proposal.pack.unresolved_gaps)
    assert plan.status != "ready_for_research"


@pytest.mark.parametrize(
    "mutation",
    [
        "request",
        "domain",
        "version",
        "promote",
        "parent",
        "source",
        "empty",
        "self_evidence",
        "early",
        "naive",
        "hash",
    ],
)
def test_rejects_unbound_or_self_promoting_response(mutation: str) -> None:
    req = request()
    raw = json.loads(response(req))
    model = raw["knowledge_pack"]
    if mutation == "request":
        raw["request_id"] = "foreign"
    elif mutation in {"domain", "version"}:
        model["domain_id" if mutation == "domain" else "version"] = "foreign"
    elif mutation == "promote":
        model["lifecycle"] = "operational"
    elif mutation == "parent":
        model["parent_version"] = "previous"
        model["revision_rationale"] = "claim parent"
    elif mutation == "source":
        model["drivers"][0]["source_requirements"] = []
    elif mutation == "empty":
        model["drivers"] = []
    elif mutation == "self_evidence":
        model["unresolved_gaps"] = [
            {
                "gap_id": "fake",
                "driver_id": "inventory",
                "kind": "required",
                "question": "claim observed",
                "required_maturity": "replayable_provider_evidence",
                "available_maturity": "replayable_provider_evidence",
                "evidence_refs": ["invented"],
                "reason": "",
            }
        ]
    elif mutation == "early":
        raw["proposed_at"] = (req.requested_at - timedelta(seconds=1)).isoformat()
    elif mutation == "naive":
        raw["proposed_at"] = "2026-09-01T02:00:00"
    else:
        model["content_id"] = "fake"
    with pytest.raises(ValueError):
        accept_cold_start_response(req, json.dumps(raw))


def test_replay_rejects_changed_request_and_corrupt_draft(tmp_path: Path) -> None:
    req = request()
    store = ColdStartProposalRepository(tmp_path / "proposals.sqlite")
    proposal = store.record(req, response(req))
    with pytest.raises(ValueError, match="request mismatch"):
        store.replay(replace(req, proposed_version="other"), proposal.proposal_id)
    with sqlite3.connect(store.path) as connection:
        connection.execute("UPDATE cold_start_proposals SET pack_json='{}'")
    with pytest.raises(ValueError, match="replay mismatch"):
        store.replay(req, proposal.proposal_id)
    with pytest.raises(ValueError, match="identity mismatch"):
        store.record(req, response(req))


def test_full_candidate_identity_is_bound_into_request() -> None:
    req = request()
    changed = replace(req, candidate=replace(req.candidate, prior_snapshot_id="f" * 64))
    assert changed.request_id != req.request_id
    with pytest.raises(ValueError, match="request identity"):
        accept_cold_start_response(changed, response(req))


def test_proposal_does_not_mutate_response_or_invent_evidence() -> None:
    req = request()
    supplied = response(req)
    proposal = accept_cold_start_response(req, supplied)
    assert json.loads(proposal.response_json) == json.loads(supplied)
    assert all(not gap.evidence_refs for gap in proposal.pack.unresolved_gaps)
    assert all(gap.available_maturity is None for gap in proposal.pack.unresolved_gaps)


def test_operational_model_uses_revision_path() -> None:
    with pytest.raises(ValueError, match="revision"):
        replace(
            request(),
            candidate=replace(candidate(), research_model_status=ResearchModelStatus.OPERATIONAL),
        )
