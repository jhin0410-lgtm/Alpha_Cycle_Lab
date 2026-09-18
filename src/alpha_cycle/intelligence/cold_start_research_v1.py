"""Model-agnostic cold-start exchange; generated knowledge remains a draft.

A proposal is recorded before a caller chooses to install it in the version
repository. Recording a proposal never certifies its evidence or promotes it.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alpha_cycle.intelligence.knowledge_pack_repository_v1 import (
    dump_knowledge_pack_json,
    load_knowledge_pack_json,
)
from alpha_cycle.intelligence.observable_universe import PlannerCandidateInput, ResearchModelStatus
from alpha_cycle.intelligence.research_model_runtime_v1 import (
    EvidenceGap,
    GapKind,
    KnowledgePack,
    PackLifecycle,
    build_research_plan,
)


@dataclass(frozen=True)
class ColdStartRequest:
    candidate: PlannerCandidateInput
    proposed_version: str
    requested_at: datetime

    def __post_init__(self) -> None:
        _aware(self.requested_at)
        _aware(self.candidate.evaluated_at)
        if self.requested_at < self.candidate.evaluated_at:
            raise ValueError("model request cannot precede candidate evaluation")
        if not self.candidate.domain_id or not self.candidate.domain_id.strip():
            raise ValueError("cold start requires an explicit domain identity")
        if not self.proposed_version.strip():
            raise ValueError("cold start requires a proposed version")
        if self.candidate.research_model_status in {
            ResearchModelStatus.REVIEWED,
            ResearchModelStatus.SOURCE_BOUND,
            ResearchModelStatus.OPERATIONAL,
            ResearchModelStatus.CALIBRATING,
        }:
            raise ValueError("established models require a revision rather than cold start")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "requested_at": self.requested_at.astimezone(UTC).isoformat(),
            "proposed_version": self.proposed_version,
            "research_plan": build_research_plan(self.candidate).payload(),
            "response_contract": {
                "fields": ["request_id", "proposed_at", "model_label", "knowledge_pack"],
                "knowledge_pack_schema": "KnowledgePack schema_version=1, omit content_id",
                "knowledge_pack_fields": [
                    "schema_version",
                    "domain_id",
                    "version",
                    "lifecycle",
                    "value_chain",
                    "drivers",
                    "transmissions",
                    "company_exposures",
                    "catalysts",
                    "risks",
                    "counter_thesis_questions",
                    "unresolved_gaps",
                    "supported_horizons",
                    "parent_version",
                    "revision_rationale",
                ],
                "driver_fields": [
                    "driver_id",
                    "meaning",
                    "role",
                    "required_maturity",
                    "gap_kind",
                    "source_requirements",
                ],
                "transmission_fields": [
                    "edge_id",
                    "source",
                    "target",
                    "kind",
                    "lag",
                    "rationale",
                    "caveats",
                ],
                "lifecycle": "draft",
                "requirements": [
                    "Declare material drivers and source acquisition plans.",
                    "Describe value-chain transmission, lag, caveats, and counter-thesis.",
                    "Keep evidence gaps unresolved; source suggestions are not observations.",
                    "Use the requested domain and version, with no parent for cold start.",
                    "Return a JSON object without Markdown fences.",
                    "Use empty unresolved_gaps: the runtime opens missing material-driver gaps.",
                ],
            },
        }

    @property
    def request_id(self) -> str:
        return _digest(self.payload())

    def message(self) -> dict[str, object]:
        """The complete message supplied to a reasoning model or connector."""
        return {"request_id": self.request_id, **self.payload()}


@dataclass(frozen=True)
class ColdStartProposal:
    request_id: str
    proposed_at: datetime
    model_label: str
    pack: KnowledgePack
    response_json: str

    @property
    def proposal_id(self) -> str:
        return _digest(
            {
                "request_id": self.request_id,
                "proposed_at": self.proposed_at.astimezone(UTC).isoformat(),
                "model_label": self.model_label,
                "pack_content_id": self.pack.content_id,
                "response_json": self.response_json,
            }
        )


def accept_cold_start_response(request: ColdStartRequest, content: str) -> ColdStartProposal:
    """Validate model output and add explicit missing material-driver evidence."""
    raw = json.loads(content, object_pairs_hook=_unique_object)
    if not isinstance(raw, dict) or set(raw) != {
        "request_id",
        "proposed_at",
        "model_label",
        "knowledge_pack",
    }:
        raise ValueError("cold-start response schema mismatch")
    if raw["request_id"] != request.request_id:
        raise ValueError("cold-start response request identity mismatch")
    if not isinstance(raw["model_label"], str) or not raw["model_label"].strip():
        raise ValueError("model label must be non-empty text")
    if not isinstance(raw["proposed_at"], str):
        raise ValueError("proposal timestamp must be text")
    proposed_at = datetime.fromisoformat(raw["proposed_at"])
    _aware(proposed_at)
    if proposed_at < request.requested_at:
        raise ValueError("proposal cannot precede request")
    declaration = raw["knowledge_pack"]
    if not isinstance(declaration, dict) or "content_id" in declaration:
        raise ValueError("model must supply a pack declaration without content_id")
    # The runtime computes identity; a model must not guess a content hash.
    pack = load_knowledge_pack_json(_canonical({**declaration, "content_id": _digest(declaration)}))
    if pack.domain_id != request.candidate.domain_id or pack.version != request.proposed_version:
        raise ValueError("proposed pack domain or version mismatch")
    if pack.lifecycle is not PackLifecycle.DRAFT or pack.parent_version is not None:
        raise ValueError("cold-start proposals must be unpromoted draft root versions")
    required = tuple(driver for driver in pack.drivers if driver.gap_kind is GapKind.REQUIRED)
    if not required or not pack.transmissions or not pack.counter_thesis_questions:
        raise ValueError("proposal needs material drivers, transmission, and counter-thesis")
    if any(not driver.source_requirements for driver in required):
        raise ValueError("material drivers require source acquisition plans")
    if any(gap.available_maturity is not None or gap.evidence_refs for gap in pack.unresolved_gaps):
        raise ValueError("model proposals cannot self-attest observed evidence")
    represented = {gap.driver_id for gap in pack.unresolved_gaps if gap.kind is GapKind.REQUIRED}
    gaps = tuple(
        EvidenceGap(
            f"cold-start:{driver.driver_id}",
            driver.driver_id,
            GapKind.REQUIRED,
            f"Acquire and validate evidence for {driver.meaning}",
            driver.required_maturity,
            reason="model proposal supplies no observed source evidence",
        )
        for driver in required
        if driver.driver_id not in represented
    )
    draft = replace(pack, unresolved_gaps=(*pack.unresolved_gaps, *gaps), content_id="")
    return ColdStartProposal(
        request.request_id, proposed_at, raw["model_label"], draft, _canonical(raw)
    )


class ColdStartProposalRepository:
    """Persist request/response and resulting draft for exact, request-bound replay."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS cold_start_proposals ("
                "proposal_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, "
                "request_json TEXT NOT NULL, response_json TEXT NOT NULL, pack_json TEXT NOT NULL)"
            )

    def record(self, request: ColdStartRequest, response: str) -> ColdStartProposal:
        proposal = accept_cold_start_response(request, response)
        values = (
            proposal.proposal_id,
            request.request_id,
            _canonical(request.payload()),
            proposal.response_json,
            dump_knowledge_pack_json(proposal.pack),
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM cold_start_proposals WHERE proposal_id=?",
                (proposal.proposal_id,),
            ).fetchone()
            if existing is not None and existing != values:
                raise ValueError("stored cold-start proposal identity mismatch")
            if existing is None:
                connection.execute(
                    "INSERT INTO cold_start_proposals VALUES (?, ?, ?, ?, ?)", values
                )
        return proposal

    def replay(self, request: ColdStartRequest, proposal_id: str) -> ColdStartProposal:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT request_id, request_json, response_json, pack_json "
                "FROM cold_start_proposals WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
        if row is None:
            raise ValueError("cold-start proposal not found")
        if row[:2] != (request.request_id, _canonical(request.payload())):
            raise ValueError("stored proposal request mismatch")
        proposal = accept_cold_start_response(request, row[2])
        if proposal.proposal_id != proposal_id or dump_knowledge_pack_json(proposal.pack) != row[3]:
            raise ValueError("stored proposal replay mismatch")
        return proposal


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("cold-start timestamps must be timezone-aware")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate cold-start response field")
        result[key] = value
    return result


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
