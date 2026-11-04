"""Synthetic writer/replay regressions; not real financial source acceptance."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from test_observable_universe import T0, T1, T2, snapshot
from test_persisted_research_plan_v1 import binding, model
from test_r1_research_cli import args, source

import alpha_cycle.intelligence.research_session_v1 as sessions
import alpha_cycle.r1_research_cli as cli
from alpha_cycle.intelligence.observable_universe import (
    CandidateRule,
    ChangeState,
    ConcurrentUniverseUpdateError,
    ResearchPriority,
    _encoded,
    _sha,
    load_current_universe_state,
    persist_successful_universe_attempt,
    publish_failed_universe_attempt,
)


def setup(root: Path):
    persist_successful_universe_attempt(snapshot(1), output_root=root, attempted_at=T0)
    prior = load_current_universe_state(root)
    persist_successful_universe_attempt(
        snapshot(3, cutoff=T1, version="2"),
        output_root=root,
        attempted_at=T1,
    )
    current = load_current_universe_state(root)
    return dict(
        universe_store=root,
        current=current,
        comparison_prior=prior,
        rules=(
            CandidateRule(
                "changed",
                "market_return",
                (ChangeState.CHANGED,),
                ResearchPriority.ROUTINE,
                "measured change",
            ),
        ),
        packs={"000660": model()},
        bindings={"000660": (binding(),)},
    )


def forged(path: Path, payload: dict, *, rehash: bool = True) -> Path:
    if rehash:
        payload.pop("session_id", None)
        payload["session_id"] = _sha(payload)
    destination = path.parent / f"{payload['session_id']}.json"
    destination.write_bytes(_encoded(payload))
    return destination


def test_exact_repeat_and_portable_fresh_process_replay(tmp_path: Path) -> None:
    options = setup(tmp_path / "store")
    session, path = sessions.persist_research_session(**options)
    again, same_path = sessions.persist_research_session(**options)
    assert same_path == path and again.content == session.content
    assert len(session.rounds) == 1
    assert (
        session.rounds[0]["candidate"]["prior_snapshot_id"]
        == options["comparison_prior"].snapshot.snapshot_id
    )
    assert session.rounds[0]["plan"]["plan"]["blockers"]  # Existing missing consensus.
    portable = tmp_path / path.name
    shutil.copyfile(path, portable)
    shutil.rmtree(options["universe_store"])
    replayed = sessions.replay_research_session(portable)
    assert replayed.content == session.content
    completed = subprocess.run(
        [
            os.sys.executable,
            "-m",
            "alpha_cycle.intelligence.research_session_v1",
            "--session",
            str(portable),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["session_id"] == session.session_id
    assert not result["authority_policy"]["live_authority_reissued"]


@pytest.mark.parametrize("latest", ["failure", "success", "broken_pointer"])
def test_replay_ignores_current_pointer_and_latest_attempt(tmp_path: Path, latest: str) -> None:
    options = setup(tmp_path)
    session, path = sessions.persist_research_session(**options)
    if latest == "failure":
        publish_failed_universe_attempt(
            output_root=tmp_path, attempted_at=T2, failure_code="offline"
        )
        with pytest.raises(ConcurrentUniverseUpdateError):
            sessions.persist_research_session(**options)
    elif latest == "success":
        persist_successful_universe_attempt(
            snapshot(7, cutoff=T2), output_root=tmp_path, attempted_at=T2
        )
    else:
        (tmp_path / "observable_universe_v1/current.json").write_text("broken")
    assert sessions.replay_research_session(path).content == session.content


@pytest.mark.parametrize("location", ["top", "rule", "binding", "pack", "plan", "package"])
def test_unknown_fields_rejected_even_after_rehash(tmp_path: Path, location: str) -> None:
    session, path = sessions.persist_research_session(**setup(tmp_path))
    payload = session.payload
    targets = {
        "top": payload,
        "rule": payload["candidate_rules"][0],
        "binding": payload["binding_policies"]["000660"][0],
        "pack": payload["knowledge_packs"]["000660"],
        "plan": payload["rounds"][0]["plan"],
        "package": payload["rounds"][0]["research"],
    }
    targets[location]["unknown_future_field"] = True
    with pytest.raises(ValueError):
        sessions.replay_research_session(forged(path, payload))


@pytest.mark.parametrize("part", ["manifest", "snapshot", "parent", "round", "generation"])
def test_tampered_or_mixed_inputs_fail_closed(tmp_path: Path, part: str) -> None:
    session, path = sessions.persist_research_session(**setup(tmp_path))
    payload = session.payload
    if part == "manifest":
        row = payload["universe_archive"][0]
        value = json.loads(base64.b64decode(row["manifest_bytes"]))
        value["previous_successful_manifest_id"] = "f" * 64
        row["manifest_bytes"] = base64.b64encode(_encoded(value)).decode()
    elif part == "snapshot":
        row = payload["universe_archive"][0]
        value = json.loads(base64.b64decode(row["snapshot_bytes"]))
        value["version"] = "tampered"
        row["snapshot_bytes"] = base64.b64encode(_encoded(value)).decode()
    elif part == "parent":
        payload["comparison_prior_generation"] = payload["current_generation"]
    elif part == "round":
        payload["rounds"][0]["research"]["plan_content_id"] = "f" * 64
    else:
        payload["current_generation"]["attempt_id"] = "f" * 64
    with pytest.raises(ValueError):
        sessions.replay_research_session(forged(path, payload))


def test_snapshot_unknown_fields_and_future_evidence_are_revalidated(tmp_path: Path) -> None:
    session, path = sessions.persist_research_session(**setup(tmp_path))
    for field in ("unknown", "research_cutoff_at"):
        payload = session.payload
        row = payload["universe_archive"][0]
        value = json.loads(base64.b64decode(row["snapshot_bytes"]))
        if field == "unknown":
            value["unknown"] = True
        else:
            value[field] = T0.isoformat()  # Existing T1 observation becomes future evidence.
        value.pop("snapshot_id")
        value["snapshot_id"] = _sha(value)
        data = _encoded(value)
        manifest = json.loads(base64.b64decode(row["manifest_bytes"]))
        manifest["snapshot_id"] = value["snapshot_id"]
        import hashlib

        manifest["snapshot_bytes_sha256"] = hashlib.sha256(data).hexdigest()
        manifest.pop("manifest_id")
        manifest["manifest_id"] = _sha(manifest)
        row.update(
            manifest_id=manifest["manifest_id"],
            manifest_bytes=base64.b64encode(_encoded(manifest)).decode(),
            snapshot_bytes=base64.b64encode(data).decode(),
        )
        generation = payload["current_generation"]
        generation.update(snapshot_id=value["snapshot_id"], manifest_id=manifest["manifest_id"])
        generation["attempt_id"] = _sha(
            {
                "status": "succeeded",
                **{key: generation[key] for key in ("attempted_at", "snapshot_id", "manifest_id")},
            }
        )
        with pytest.raises(ValueError):
            sessions.replay_research_session(forged(path, payload))


def test_recorded_source_claims_cannot_reissue_authority(tmp_path: Path) -> None:
    options = setup(tmp_path)
    options["source_receipts"] = {"historical_live_receipt": {"fresh_official_verification": True}}
    session, path = sessions.persist_research_session(**options)
    replayed = sessions.replay_research_session(path)
    assert not replayed.payload["authority_policy"]["provider_origin_authenticated"]
    payload = session.payload
    payload["authority_policy"]["live_authority_reissued"] = True
    with pytest.raises(ValueError, match="authority"):
        sessions.replay_research_session(forged(path, payload))


def test_concurrent_identical_writes_and_conflicting_bytes(tmp_path: Path) -> None:
    options = setup(tmp_path)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: sessions.persist_research_session(**options), range(3)))
    assert len({session.session_id for session, _ in results}) == 1
    path = results[0][1]
    path.write_text("conflicting immutable bytes")
    with pytest.raises(ValueError, match="conflict"):
        sessions.persist_research_session(**options)
    assert path.read_text() == "conflicting immutable bytes"


@pytest.mark.parametrize("stage", ["stage", "link"])
def test_partial_write_failure_never_publishes_partial_session(tmp_path, monkeypatch, stage):
    options = setup(tmp_path)
    if stage == "stage":
        original = sessions._write_immutable

        def fail(path, content):
            if "acl-session-write-" in str(path):
                path.write_bytes(content[:10])
                raise OSError("partial staged write")
            original(path, content)

        monkeypatch.setattr(sessions, "_write_immutable", fail)
    else:

        def interrupted(*_):
            raise OSError("publication interrupted")

        monkeypatch.setattr(sessions, "_link_open_file_at", interrupted)
    with pytest.raises(OSError):
        sessions.persist_research_session(**options)
    assert not list((tmp_path / sessions.REPOSITORY).glob("*.json"))


@pytest.mark.parametrize("target", ["store", "repository", "artifact", "manifests", "snapshots"])
def test_symlink_paths_are_rejected(tmp_path, target):
    root = tmp_path / "store"
    options = setup(root)
    session, path = sessions.persist_research_session(**options)
    if target == "artifact":
        copy = tmp_path / "saved.json"
        shutil.copyfile(path, copy)
        path.unlink()
        path.symlink_to(copy)
        with pytest.raises(ValueError):
            sessions.replay_research_session(path)
        return
    if target == "store":
        selected = root
    elif target == "repository":
        selected = root / sessions.REPOSITORY
    else:
        selected = root / "observable_universe_v1" / target
    moved = tmp_path / "moved"
    selected.rename(moved)
    selected.symlink_to(moved, target_is_directory=True)
    with pytest.raises((OSError, ValueError)):
        sessions.persist_research_session(**options)
    assert session.session_id


def test_baseline_and_unchanged_explicit_requests_are_not_discovery(tmp_path, capsys):
    original = source(tmp_path / "source")
    store = tmp_path / "store"
    command = args(original, store) + ["--request-member", "000660", "--request-reason", "Review"]
    for _ in range(2):
        assert cli.main(command) == 0
        output = json.loads(capsys.readouterr().out)
        assert len(output["rounds"]) == 1
        entry = output["rounds"][0]
        assert "candidate" not in entry
        assert entry["request"]["semantics"] == "explicit_research_not_measured_discovery"
        assert entry["plan"]["candidate_lineage"] is None
        assert not any(c["state"] == "changed" for c in output["changes"])
        replayed = sessions.replay_research_session(Path(output["session_path"]))
        assert replayed.rounds == output["rounds"]


def test_cli_does_not_report_success_before_session_commit(tmp_path, capsys, monkeypatch):
    original = source(tmp_path / "source")
    store = tmp_path / "store"

    def interrupted(**_):
        raise OSError("session write failed")

    monkeypatch.setattr(cli, "persist_research_session", interrupted)
    assert cli.main(args(original, store)) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "failed" and "session_id" not in output
    assert not load_current_universe_state(store).ready


def test_source_change_during_session_publication_is_superseded(tmp_path, capsys, monkeypatch):
    original = source(tmp_path / "source")
    store = tmp_path / "store"
    publish = cli.persist_research_session

    def competing(**kwargs):
        current = kwargs["current"]
        publish_failed_universe_attempt(
            output_root=store,
            attempted_at=current.attempted_at.replace(microsecond=999999),
            research_cutoff_at=current.research_cutoff_at,
            failure_code="competing_failure",
        )
        return publish(**kwargs)

    monkeypatch.setattr(cli, "persist_research_session", competing)
    assert cli.main(args(original, store)) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "superseded"
    assert load_current_universe_state(store).failure_code == "competing_failure"


def test_binding_policy_and_pack_identity_are_retained(tmp_path):
    options = setup(tmp_path)
    first, _ = sessions.persist_research_session(**options)
    options["bindings"] = {"000660": (replace(binding(), maximum_age=T2 - T0),)}
    second, _ = sessions.persist_research_session(**options)
    assert first.session_id != second.session_id
    assert first.rounds[0]["plan_content_id"] != second.rounds[0]["plan_content_id"]
    assert first.payload["knowledge_packs"]["000660"]["content_id"] == model().content_id


def test_recovery_baseline_retains_failure_and_full_parent_chain(tmp_path, capsys):
    original = source(tmp_path / "source")
    store = tmp_path / "store"
    assert cli.main(args(original, store)) == 0
    capsys.readouterr()
    assert cli.main(args(tmp_path / "missing", store)) == 2
    capsys.readouterr()
    assert cli.main(args(original, store) + ["--request-member", "000660"]) == 0
    output = json.loads(capsys.readouterr().out)
    session = sessions.replay_research_session(Path(output["session_path"]))
    assert session.payload["comparison_prior_generation"] is None
    assert session.payload["preceding_attempt"]["status"] == "failed"
    assert len(session.payload["universe_archive"]) == 2
    assert session.payload["changes"] == []
    assert "candidate" not in session.rounds[0]


def test_prior_cannot_be_omitted_to_disguise_change_as_baseline(tmp_path):
    options = setup(tmp_path)
    session, path = sessions.persist_research_session(**options)
    payload = session.payload
    payload["preceding_attempt"] = None
    payload["comparison_prior_generation"] = None
    with pytest.raises(ValueError, match="preceding attempt"):
        sessions.replay_research_session(forged(path, payload))


def test_archive_missing_parent_and_duplicate_keys_are_rejected(tmp_path):
    session, path = sessions.persist_research_session(**setup(tmp_path))
    payload = session.payload
    payload["universe_archive"].pop()
    with pytest.raises(ValueError, match="parent"):
        sessions.replay_research_session(forged(path, payload))
    path.write_bytes(
        session.content.replace(
            b'"schema_version": 1,', b'"schema_version": 1, "schema_version": 1,', 1
        )
    )
    with pytest.raises(ValueError, match="duplicate"):
        sessions.replay_research_session(path)


def test_session_filename_and_unhashed_tampering_are_rejected(tmp_path):
    session, path = sessions.persist_research_session(**setup(tmp_path))
    payload = session.payload
    payload["rounds"][0]["unavailable"] = []
    with pytest.raises(ValueError, match="identity"):
        sessions.replay_research_session(forged(path, payload, rehash=False))
    other = tmp_path / "wrong-name.json"
    other.write_bytes(session.content)
    with pytest.raises(ValueError, match="filename"):
        sessions.replay_research_session(other)


def test_repository_swap_during_publication_cannot_redirect_write(tmp_path, monkeypatch):
    options = setup(tmp_path / "store")
    outside = tmp_path / "outside"
    outside.mkdir()
    real_link = sessions._link_open_file_at

    def swapped(fd, directory_fd, name):
        repository = options["universe_store"] / sessions.REPOSITORY
        repository.rename(tmp_path / "retained-inode")
        repository.symlink_to(outside, target_is_directory=True)
        real_link(fd, directory_fd, name)

    monkeypatch.setattr(sessions, "_link_open_file_at", swapped)
    with pytest.raises(ValueError, match="changed"):
        sessions.persist_research_session(**options)
    assert list(outside.iterdir()) == []


def test_offline_replay_never_calls_network_or_current_store(tmp_path, monkeypatch):
    import socket
    import urllib.request

    session, path = sessions.persist_research_session(**setup(tmp_path))

    def forbidden(*args, **kwargs):
        raise AssertionError("offline replay accessed live state")

    monkeypatch.setattr(sessions, "_load_current_universe_state_locked", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)
    monkeypatch.setattr(cli, "verify_opendart_reported_fields", forbidden)
    assert sessions.replay_research_session(path).content == session.content


def test_baseline_retains_pack_even_without_discovery(tmp_path, capsys):
    original = source(tmp_path / "source")
    pack = model()
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack.payload()))
    assert cli.main(args(original, tmp_path / "store") + ["--pack", str(pack_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    session = sessions.replay_research_session(Path(output["session_path"]))
    assert session.rounds == []
    assert session.payload["knowledge_packs"]["000660"] == pack.payload()


@pytest.mark.parametrize("component", ["binding", "rule", "snapshot_scope", "schema"])
def test_semantic_input_mix_is_recomputed_not_trusted(tmp_path, component):
    session, path = sessions.persist_research_session(**setup(tmp_path))
    payload = session.payload
    if component == "binding":
        payload["binding_policies"]["000660"][0]["unit"] = "foreign_unit"
    elif component == "rule":
        payload["candidate_rules"][0]["minimum_absolute_delta"] = 1000
    elif component == "snapshot_scope":
        payload["knowledge_packs"]["foreign_company"] = payload["knowledge_packs"].pop("000660")
    else:
        payload["schema_version"] = True
    with pytest.raises(ValueError):
        sessions.replay_research_session(forged(path, payload))


@pytest.mark.parametrize("replacement", ["bytes", "symlink", "fifo"])
def test_stage_substitution_is_rejected_before_final_link(tmp_path, monkeypatch, replacement):
    options = setup(tmp_path)
    original = sessions._write_immutable

    def substituted(path, content):
        original(path, content)
        if "acl-session-write-" not in str(path):
            return
        path.unlink()
        if replacement == "bytes":
            path.write_bytes(b"substituted bytes")
        elif replacement == "symlink":
            alternate = tmp_path / "external.json"
            alternate.write_bytes(content)
            path.symlink_to(alternate)
        else:
            os.mkfifo(path)

    monkeypatch.setattr(sessions, "_write_immutable", substituted)
    with pytest.raises((ValueError, OSError)):
        sessions.persist_research_session(**options)
    assert not list((tmp_path / sessions.REPOSITORY).glob("*.json"))
