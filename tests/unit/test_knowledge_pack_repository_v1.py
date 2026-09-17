from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from test_research_model_runtime_v1 import pack

from alpha_cycle.intelligence.knowledge_pack_repository_v1 import (
    KnowledgePackRepository,
    dump_knowledge_pack_json,
    load_knowledge_pack_json,
)


@pytest.mark.parametrize("domain", ["memory_semiconductor", "defense", "power_grid", "cold_start"])
def test_declarative_round_trip_and_reopen(tmp_path: Path, domain: str) -> None:
    original = replace(pack(), domain_id=domain, content_id="")
    supplied = json.dumps(original.payload())
    model = load_knowledge_pack_json(supplied)
    path = tmp_path / "packs.sqlite"
    KnowledgePackRepository(path).publish(model)
    assert KnowledgePackRepository(path).load(domain, model.version) == original


def test_revision_retains_parent_and_rejects_same_version_edit(tmp_path: Path) -> None:
    repository = KnowledgePackRepository(tmp_path / "packs.sqlite")
    original = pack()
    repository.publish(original)
    revised = replace(
        original,
        version="2",
        parent_version=original.version,
        revision_rationale="new inventory question",
        risks=("new risk",),
        content_id="",
    )
    repository.publish(revised)
    assert repository.load(original.domain_id, original.version) == original
    assert repository.load(revised.domain_id, "2") == revised
    with pytest.raises(ValueError, match="immutable"):
        repository.publish(replace(original, risks=("rewritten history",), content_id=""))


def test_concurrent_identical_publication_is_idempotent(tmp_path: Path) -> None:
    repository = KnowledgePackRepository(tmp_path / "packs.sqlite")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = tuple(pool.map(repository.publish, [pack()] * 8))
    assert set(ids) == {pack().content_id}
    assert repository.load(pack().domain_id, pack().version) == pack()


def test_competing_versions_cannot_overwrite_winner(tmp_path: Path) -> None:
    repository = KnowledgePackRepository(tmp_path / "packs.sqlite")
    proposals = [replace(pack(), risks=(f"risk-{i}",), content_id="") for i in range(4)]

    def publish(index: int) -> str | None:
        try:
            return repository.publish(proposals[index])
        except ValueError as exc:
            assert "immutable" in str(exc)
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = tuple(pool.map(publish, range(4)))
    successful = tuple(value for value in results if value is not None)
    assert len(successful) == 1
    assert repository.load(pack().domain_id, pack().version).content_id == successful[0]


def test_missing_parent_and_corrupt_payload_fail_closed(tmp_path: Path) -> None:
    repository = KnowledgePackRepository(tmp_path / "packs.sqlite")
    child = replace(
        pack(),
        version="2",
        parent_version=pack().version,
        revision_rationale="revision",
        content_id="",
    )
    with pytest.raises(ValueError, match="parent"):
        repository.publish(child)
    repository.publish(pack())
    with sqlite3.connect(repository.path) as connection:
        connection.execute("UPDATE knowledge_packs SET payload='{}'")
    with pytest.raises(ValueError, match="field"):
        repository.load(pack().domain_id, pack().version)
    with pytest.raises(ValueError, match="field"):
        repository.publish(child)


@pytest.mark.parametrize(
    "mutation", ["unknown", "nested_unknown", "bool_schema", "missing_id", "hash"]
)
def test_interchange_rejects_lossy_or_tampered_input(mutation: str) -> None:
    raw = json.loads(dump_knowledge_pack_json(pack()))
    if mutation == "unknown":
        raw["certified"] = True
    elif mutation == "nested_unknown":
        raw["drivers"][0]["certified"] = True
    elif mutation == "bool_schema":
        raw["schema_version"] = True
    elif mutation == "missing_id":
        del raw["content_id"]
    else:
        raw["risks"] = ["tampered"]
    with pytest.raises(ValueError):
        load_knowledge_pack_json(json.dumps(raw))


def test_duplicate_json_keys_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate JSON"):
        load_knowledge_pack_json('{"schema_version":1,"schema_version":1}')


def test_missing_ancestor_blocks_load_retry_and_new_child(tmp_path: Path) -> None:
    repository = KnowledgePackRepository(tmp_path / "packs.sqlite")
    first = pack()
    second = replace(
        first,
        version="2",
        parent_version=first.version,
        revision_rationale="revision",
        content_id="",
    )
    third = replace(second, version="3", parent_version="2", content_id="")
    repository.publish(first)
    repository.publish(second)
    with sqlite3.connect(repository.path) as connection:
        connection.execute("DELETE FROM knowledge_packs WHERE version=?", (first.version,))
    for action in (
        lambda: repository.load(second.domain_id, second.version),
        lambda: repository.publish(second),
        lambda: repository.publish(third),
    ):
        with pytest.raises(ValueError, match="ancestor not found"):
            action()


def test_unknown_transmission_endpoint_rejected() -> None:
    original = pack()
    invalid = replace(
        original,
        transmissions=(replace(original.transmissions[0], target="unknown"),),
        content_id="",
    )
    with pytest.raises(ValueError, match="endpoints"):
        dump_knowledge_pack_json(invalid)
