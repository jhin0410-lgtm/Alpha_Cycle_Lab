from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import alpha_cycle.research_package_assembler_v2_1 as assembler

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def _fake_owned_opportunity_persist(snapshot: SimpleNamespace, *, output_root: Path):
    object_name = (
        "opportunity_candidate" if str(snapshot.snapshot_id).startswith("a") else "opportunity_set"
    )
    root = Path(output_root) / object_name
    root_created = not root.exists()
    root.mkdir(parents=True, exist_ok=True)
    snapshot_id = str(snapshot.snapshot_id)
    directory = assembler._opportunity_snapshot_directory(
        Path(output_root),
        object_name=object_name,
        captured_at=snapshot.captured_at,
        snapshot_id=snapshot_id,
    )
    directory.mkdir()
    (directory / f"{object_name}.json").write_text("{}\n", encoding="utf-8")
    pointer = root / f"latest_{object_name}.json"
    pointer_before = pointer.read_bytes() if pointer.exists() else None
    pointer_after = json.dumps(
        {
            "schema_version": 1,
            "object_type": object_name,
            "snapshot_id": snapshot_id,
            "snapshot_path": str(directory),
        },
        sort_keys=True,
    ).encode("utf-8")
    pointer.write_bytes(pointer_after)
    stat = pointer.stat()
    return assembler._OwnedOpportunityPublication(
        root=root,
        directory=directory,
        directory_created=True,
        root_created=root_created,
        pointer=pointer,
        pointer_before=pointer_before,
        pointer_after=pointer_after,
        pointer_inode=stat.st_ino,
        pointer_mtime_ns=stat.st_mtime_ns,
        pointer_size=stat.st_size,
    )


def _ignore_validation(*args, **kwargs) -> None:
    del args, kwargs


def test_ledger_publish_failure_rolls_back_all_new_downstream_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = SimpleNamespace(snapshot_id="a" * 64, captured_at=NOW)
    opportunity_set = SimpleNamespace(snapshot_id="b" * 64, captured_at=NOW)
    artifacts = SimpleNamespace(
        opportunity_candidates=(candidate,),
        opportunity_set=opportunity_set,
        snapshot=SimpleNamespace(snapshot_id="c" * 64, payload_without_id=lambda: {}),
    )
    round_path = tmp_path / "research_round_v2_1" / "round.json"
    run_path = tmp_path / "research_round_run_v2_1" / "run.json"

    monkeypatch.setattr(assembler, "validate_publication_layout", _ignore_validation)
    monkeypatch.setattr(
        assembler,
        "validate_existing_opportunity_artifacts",
        _ignore_validation,
    )
    monkeypatch.setattr(
        assembler,
        "validate_persisted_opportunity_candidate",
        _ignore_validation,
    )
    monkeypatch.setattr(
        assembler,
        "validate_persisted_opportunity_set",
        _ignore_validation,
    )
    monkeypatch.setattr(
        assembler,
        "_persist_owned_opportunity_snapshot",
        _fake_owned_opportunity_persist,
    )

    def persist_owned_json(*, root, repository_name, snapshot_id, payload_without_id):
        del root, snapshot_id, payload_without_id
        if repository_name == "research_run_ledger_v2_1":
            raise RuntimeError("injected ledger publication failure")
        path = round_path if repository_name == "research_round_v2_1" else run_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        return path, assembler._capture_owned_file(path)

    monkeypatch.setattr(assembler, "_persist_owned_content_addressed_json", persist_owned_json)

    with pytest.raises(RuntimeError, match="injected ledger publication failure"):
        assembler._publish_orchestrated_artifacts(
            artifacts=artifacts,
            run=SimpleNamespace(snapshot_id="d" * 64, payload_without_id=lambda: {}),
            ledger=SimpleNamespace(snapshot_id="e" * 64, payload_without_id=lambda: {}),
            root=tmp_path,
        )

    assert not round_path.exists()
    assert not run_path.exists()
    for object_name in ("opportunity_candidate", "opportunity_set"):
        root = tmp_path / object_name
        assert root.exists()
        assert not (root / f"latest_{object_name}.json").exists()
        assert any(path.is_dir() for path in root.iterdir())


def test_rollback_preserves_concurrently_replaced_pointer_and_immutable_artifact(
    tmp_path: Path,
) -> None:
    candidate = SimpleNamespace(snapshot_id="a" * 64, captured_at=NOW)
    publication = _fake_owned_opportunity_persist(candidate, output_root=tmp_path)
    concurrent_pointer = b'{"snapshot_id":"concurrent"}\n'
    publication.pointer.write_bytes(concurrent_pointer)

    cleanup_errors: list[BaseException] = []
    assembler._rollback_owned_opportunity_publication(publication, cleanup_errors)

    assert cleanup_errors == []
    assert publication.pointer.read_bytes() == concurrent_pointer
    assert publication.directory.exists()
