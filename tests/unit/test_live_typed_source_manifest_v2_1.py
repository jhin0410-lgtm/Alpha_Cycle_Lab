from __future__ import annotations

import json
import os
import subprocess
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle.live_typed_source_manifest_v2_1 import (
    LiveTypedSourceManifestError,
    freeze_live_typed_source_manifest,
    load_live_typed_source_manifest,
    persist_live_typed_source_manifest,
    verify_live_typed_source_manifest,
)


def _write_source_snapshot(
    root: Path,
    *,
    role: str,
    snapshot_id: str,
    captured_at: datetime,
    evaluation_date: date | None,
    content: str,
) -> Path:
    directory = root / role / f"snapshot__{snapshot_id[:12]}"
    directory.mkdir(parents=True)
    (directory / "data.json").write_text(content, encoding="utf-8")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "captured_at": captured_at.isoformat(),
        "files": ["data.json"],
    }
    if evaluation_date is not None:
        manifest["evaluation_date"] = evaluation_date.isoformat()
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return directory


def test_frozen_source_manifest_replays_exact_bytes(tmp_path: Path) -> None:
    evaluation_date = date(2026, 8, 25)
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    cutoff = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)
    market = _write_source_snapshot(
        tmp_path,
        role="market-intelligence",
        snapshot_id="1" * 64,
        captured_at=captured_at,
        evaluation_date=None,
        content='{"price": 123}',
    )
    research = _write_source_snapshot(
        tmp_path,
        role="research-intelligence",
        snapshot_id="2" * 64,
        captured_at=captured_at + timedelta(minutes=5),
        evaluation_date=evaluation_date,
        content='{"opendart": true, "ecos": true}',
    )

    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": market, "research": research},
        evaluation_date=evaluation_date,
        research_cutoff_at=cutoff,
        frozen_at=cutoff,
    )
    path = persist_live_typed_source_manifest(manifest, artifact_root=tmp_path)
    loaded = load_live_typed_source_manifest(path)

    assert loaded == manifest
    assert loaded.manifest_id == manifest.manifest_id
    assert tuple(source.role for source in loaded.sources) == ("market", "research")
    assert not (path.parent / "latest_live_typed_source_manifest_v2_1.json").exists()
    assert all(source.files[0].relative_path == "data.json" for source in loaded.sources)
    assert all(source.files[1].relative_path == "manifest.json" for source in loaded.sources)
    verify_live_typed_source_manifest(loaded, artifact_root=tmp_path)


def test_replay_rejects_mutated_source_bytes(tmp_path: Path) -> None:
    evaluation_date = date(2026, 8, 25)
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    source = _write_source_snapshot(
        tmp_path,
        role="market-intelligence",
        snapshot_id="3" * 64,
        captured_at=captured_at,
        evaluation_date=None,
        content="original",
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": source},
        evaluation_date=evaluation_date,
        research_cutoff_at=captured_at + timedelta(hours=1),
        frozen_at=captured_at + timedelta(minutes=30),
    )

    (source / "data.json").write_text("mutated", encoding="utf-8")

    with pytest.raises(LiveTypedSourceManifestError, match="source file bytes changed"):
        verify_live_typed_source_manifest(manifest, artifact_root=tmp_path)


def test_freeze_rejects_source_after_research_cutoff(tmp_path: Path) -> None:
    evaluation_date = date(2026, 8, 25)
    cutoff = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    source = _write_source_snapshot(
        tmp_path,
        role="research-intelligence",
        snapshot_id="4" * 64,
        captured_at=cutoff + timedelta(seconds=1),
        evaluation_date=evaluation_date,
        content="future",
    )

    with pytest.raises(LiveTypedSourceManifestError, match="captured after frozen_at"):
        freeze_live_typed_source_manifest(
            artifact_root=tmp_path,
            source_directories={"research": source},
            evaluation_date=evaluation_date,
            research_cutoff_at=cutoff,
            frozen_at=cutoff,
        )


def test_freeze_rejects_mixed_evaluation_dates(tmp_path: Path) -> None:
    evaluation_date = date(2026, 8, 25)
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    source = _write_source_snapshot(
        tmp_path,
        role="research-intelligence",
        snapshot_id="5" * 64,
        captured_at=captured_at,
        evaluation_date=date(2026, 8, 24),
        content="stale-generation",
    )

    with pytest.raises(LiveTypedSourceManifestError, match="evaluation_date differs"):
        freeze_live_typed_source_manifest(
            artifact_root=tmp_path,
            source_directories={"research": source},
            evaluation_date=evaluation_date,
            research_cutoff_at=captured_at + timedelta(hours=1),
            frozen_at=captured_at + timedelta(minutes=30),
        )


def test_load_rejects_unknown_manifest_fields(tmp_path: Path) -> None:
    evaluation_date = date(2026, 8, 25)
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    source = _write_source_snapshot(
        tmp_path,
        role="market-intelligence",
        snapshot_id="6" * 64,
        captured_at=captured_at,
        evaluation_date=None,
        content="stable",
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": source},
        evaluation_date=evaluation_date,
        research_cutoff_at=captured_at + timedelta(hours=1),
        frozen_at=captured_at + timedelta(minutes=30),
    )
    path = persist_live_typed_source_manifest(manifest, artifact_root=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unknown_field"] = "tamper"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(LiveTypedSourceManifestError, match="unknown=.*unknown_field"):
        load_live_typed_source_manifest(path)


def test_freeze_rejects_snapshot_outside_artifact_root(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    outside = tmp_path / "outside"
    source = _write_source_snapshot(
        outside,
        role="market-intelligence",
        snapshot_id="7" * 64,
        captured_at=datetime(2026, 8, 25, 6, 0, tzinfo=UTC),
        evaluation_date=None,
        content="outside",
    )

    with pytest.raises(LiveTypedSourceManifestError, match="escapes artifact_root"):
        freeze_live_typed_source_manifest(
            artifact_root=artifact_root,
            source_directories={"market": source},
            evaluation_date=date(2026, 8, 25),
            research_cutoff_at=datetime(2026, 8, 25, 7, 0, tzinfo=UTC),
            frozen_at=datetime(2026, 8, 25, 6, 30, tzinfo=UTC),
        )


def test_freeze_rejects_symlinked_source_file(tmp_path: Path) -> None:
    source = _write_source_snapshot(
        tmp_path,
        role="market-intelligence",
        snapshot_id="8" * 64,
        captured_at=datetime(2026, 8, 25, 6, 0, tzinfo=UTC),
        evaluation_date=None,
        content="bound",
    )
    target = source / "target.json"
    target.write_text("foreign", encoding="utf-8")
    (source / "data.json").unlink()
    try:
        os.symlink(target, source / "data.json")
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(LiveTypedSourceManifestError, match="regular file"):
        freeze_live_typed_source_manifest(
            artifact_root=tmp_path,
            source_directories={"market": source},
            evaluation_date=date(2026, 8, 25),
            research_cutoff_at=datetime(2026, 8, 25, 7, 0, tzinfo=UTC),
            frozen_at=datetime(2026, 8, 25, 6, 30, tzinfo=UTC),
        )


@pytest.mark.parametrize("content", (b"\xff\xfe", b"{not-json"))
def test_freeze_rejects_malformed_source_manifest(tmp_path: Path, content: bytes) -> None:
    source = _write_source_snapshot(
        tmp_path,
        role="research-intelligence",
        snapshot_id="9" * 64,
        captured_at=datetime(2026, 8, 25, 6, 0, tzinfo=UTC),
        evaluation_date=date(2026, 8, 25),
        content="stable",
    )
    (source / "manifest.json").write_bytes(content)

    with pytest.raises(LiveTypedSourceManifestError, match="cannot load JSON object"):
        freeze_live_typed_source_manifest(
            artifact_root=tmp_path,
            source_directories={"research": source},
            evaluation_date=date(2026, 8, 25),
            research_cutoff_at=datetime(2026, 8, 25, 7, 0, tzinfo=UTC),
            frozen_at=datetime(2026, 8, 25, 6, 30, tzinfo=UTC),
        )


def test_source_manifest_cannot_self_certify_valuation(tmp_path: Path) -> None:
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    source = _write_source_snapshot(
        tmp_path,
        role="market-intelligence",
        snapshot_id="a" * 64,
        captured_at=captured_at,
        evaluation_date=None,
        content="stable",
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": source},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(hours=1),
        frozen_at=captured_at + timedelta(minutes=30),
    )
    path = persist_live_typed_source_manifest(manifest, artifact_root=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["valuation_authority_certified"] = True
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(LiveTypedSourceManifestError, match="cannot certify"):
        load_live_typed_source_manifest(path)


def test_manifest_rejects_duplicate_role_and_freeze_after_cutoff(tmp_path: Path) -> None:
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    source = _write_source_snapshot(
        tmp_path,
        role="market-intelligence",
        snapshot_id="b" * 64,
        captured_at=captured_at,
        evaluation_date=None,
        content="stable",
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=tmp_path,
        source_directories={"market": source},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(hours=1),
        frozen_at=captured_at + timedelta(minutes=30),
    )

    with pytest.raises(ValueError, match="roles must be unique"):
        replace(manifest, sources=(manifest.sources[0], manifest.sources[0]))
    with pytest.raises(ValueError, match="frozen_at cannot follow"):
        replace(manifest, frozen_at=captured_at + timedelta(hours=2))


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-specific")
def test_persist_rejects_junction_backed_repository(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    captured_at = datetime(2026, 8, 25, 6, 0, tzinfo=UTC)
    source = _write_source_snapshot(
        artifact_root,
        role="market-intelligence",
        snapshot_id="c" * 64,
        captured_at=captured_at,
        evaluation_date=None,
        content="stable",
    )
    manifest = freeze_live_typed_source_manifest(
        artifact_root=artifact_root,
        source_directories={"market": source},
        evaluation_date=date(2026, 8, 25),
        research_cutoff_at=captured_at + timedelta(hours=1),
        frozen_at=captured_at + timedelta(minutes=30),
    )
    outside = tmp_path / "outside-manifests"
    outside.mkdir()
    repository = artifact_root / "live_typed_source_manifest_v2_1"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(repository), str(outside)],
        check=True,
        capture_output=True,
    )

    with pytest.raises(LiveTypedSourceManifestError, match="escapes artifact_root"):
        persist_live_typed_source_manifest(manifest, artifact_root=artifact_root)
