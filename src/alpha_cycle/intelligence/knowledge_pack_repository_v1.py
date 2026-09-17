"""Declarative pack interchange and transactional, immutable version storage.

Stored lifecycle labels describe the proposal; storage does not certify source
authority or operational acceptance. No current-version pointer is inferred.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from alpha_cycle.intelligence.observable_universe import EvidenceMaturity
from alpha_cycle.intelligence.research_model_runtime_v1 import (
    EvidenceGap,
    GapKind,
    KnowledgePack,
    PackLifecycle,
    ResearchDriver,
    TransmissionHypothesis,
    TransmissionKind,
)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("pack value must be an object")
    return value


def _texts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError("pack field must be an array of non-empty strings")
    return tuple(value)


def _rows(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        raise ValueError("pack field must be an array")
    return tuple(_object(item) for item in value)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_knowledge_pack_json(content: str) -> KnowledgePack:
    """Read the exact exported schema; reject ignored fields and coerced values."""
    raw = _object(json.loads(content, object_pairs_hook=_unique_pairs))
    try:
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise ValueError("unsupported pack schema version")
        drivers = tuple(
            ResearchDriver(
                row["driver_id"],
                row["meaning"],
                row["role"],
                EvidenceMaturity(row["required_maturity"]),
                GapKind(row["gap_kind"]),
                _texts(row["source_requirements"]),
            )
            for row in _rows(raw["drivers"])
        )
        edges = tuple(
            TransmissionHypothesis(
                row["edge_id"],
                row["source"],
                row["target"],
                TransmissionKind(row["kind"]),
                row["lag"],
                row["rationale"],
                _texts(row["caveats"]),
            )
            for row in _rows(raw["transmissions"])
        )
        gaps = tuple(
            EvidenceGap(
                row["gap_id"],
                row["driver_id"],
                GapKind(row["kind"]),
                row["question"],
                EvidenceMaturity(row["required_maturity"]),
                None
                if row["available_maturity"] is None
                else EvidenceMaturity(row["available_maturity"]),
                _texts(row["evidence_refs"]),
                row["reason"],
            )
            for row in _rows(raw["unresolved_gaps"])
        )
        pack = KnowledgePack(
            domain_id=raw["domain_id"],
            version=raw["version"],
            lifecycle=PackLifecycle(raw["lifecycle"]),
            value_chain=_texts(raw["value_chain"]),
            drivers=drivers,
            transmissions=edges,
            company_exposures=_texts(raw["company_exposures"]),
            catalysts=_texts(raw["catalysts"]),
            risks=_texts(raw["risks"]),
            counter_thesis_questions=_texts(raw["counter_thesis_questions"]),
            unresolved_gaps=gaps,
            supported_horizons=_texts(raw["supported_horizons"]),
            parent_version=raw["parent_version"],
            revision_rationale=raw["revision_rationale"],
            content_id=raw["content_id"],
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("missing or invalid knowledge pack field") from exc
    _validate_structure(pack)
    # Comparing canonical JSON also distinguishes bool from int and prevents
    # unknown nested fields from disappearing during parsing.
    if _canonical(pack.payload()) != _canonical(raw):
        raise ValueError("pack schema or content identity mismatch")
    return pack


def dump_knowledge_pack_json(pack: KnowledgePack) -> str:
    content = _canonical(pack.payload())
    load_knowledge_pack_json(content)
    return content


def _validate_structure(pack: KnowledgePack) -> None:
    for driver in pack.drivers:
        _text(driver.role)
    for edge in pack.transmissions:
        for value in (edge.edge_id, edge.source, edge.target, edge.lag, edge.rationale):
            _text(value)
        if edge.source not in pack.value_chain or edge.target not in pack.value_chain:
            raise ValueError("transmission endpoints must exist in value chain")
    for gap in pack.unresolved_gaps:
        _text(gap.question)
        if gap.driver_id not in {driver.driver_id for driver in pack.drivers}:
            raise ValueError("gap references unknown driver")
        _text(gap.reason, allow_empty=True)
    if not pack.supported_horizons or set(pack.supported_horizons) - {"3m", "6m", "12m"}:
        raise ValueError("unsupported pack horizons")
    if len(set(pack.supported_horizons)) != len(pack.supported_horizons):
        raise ValueError("duplicate pack horizons")
    _text(pack.revision_rationale, allow_empty=True)
    if pack.parent_version is not None:
        _text(pack.parent_version)
        _text(pack.revision_rationale)
        if pack.parent_version == pack.version:
            raise ValueError("pack cannot be its own parent")


def _text(value: object, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError("pack field must be text")


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


class KnowledgePackRepository:
    """Append-only API keyed by domain and version, using SQLite transactions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS knowledge_packs ("
                "domain_id TEXT NOT NULL, version TEXT NOT NULL, "
                "content_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, "
                "PRIMARY KEY (domain_id, version))"
            )

    def publish(self, pack: KnowledgePack) -> str:
        """Install once or return an exact retry; never replace a version."""
        content = dump_knowledge_pack_json(pack)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT content_id, payload FROM knowledge_packs WHERE domain_id=? AND version=?",
                (pack.domain_id, pack.version),
            ).fetchone()
            if existing is not None:
                if existing != (pack.content_id, content):
                    raise ValueError("knowledge pack version is immutable")
                return pack.content_id
            if pack.parent_version is not None:
                parent = connection.execute(
                    "SELECT content_id, payload FROM knowledge_packs "
                    "WHERE domain_id=? AND version=?",
                    (pack.domain_id, pack.parent_version),
                ).fetchone()
                if parent is None:
                    raise ValueError("parent knowledge pack version is not installed")
                parsed = load_knowledge_pack_json(parent[1])
                if (parsed.domain_id, parsed.version, parsed.content_id) != (
                    pack.domain_id,
                    pack.parent_version,
                    parent[0],
                ):
                    raise ValueError("parent knowledge pack identity mismatch")
            connection.execute(
                "INSERT INTO knowledge_packs VALUES (?, ?, ?, ?)",
                (pack.domain_id, pack.version, pack.content_id, content),
            )
        return pack.content_id

    def load(self, domain_id: str, version: str) -> KnowledgePack:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT content_id, payload FROM knowledge_packs WHERE domain_id=? AND version=?",
                (domain_id, version),
            ).fetchone()
        if row is None:
            raise ValueError("knowledge pack version not found")
        pack = load_knowledge_pack_json(row[1])
        if (pack.domain_id, pack.version, pack.content_id) != (domain_id, version, row[0]):
            raise ValueError("stored knowledge pack identity mismatch")
        return pack
