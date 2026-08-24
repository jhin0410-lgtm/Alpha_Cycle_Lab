from __future__ import annotations

import errno
import os
import shutil
from dataclasses import replace
from pathlib import Path
from runpy import run_path

import pytest

import alpha_cycle.research_package_assembler_v2_1 as assembler
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OpportunityCandidateSnapshot,
    OpportunityResearchClass,
)
from alpha_cycle.intelligence.valuation import (
    _valuation_metrics,
    write_valuation_evidence_snapshot,
)
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_package_source_revalidation_v2_1 import (
    load_canonical_valuation_evidence,
)

_FIXTURE = run_path(str(Path(__file__).with_name("test_research_package_assembler_v2_1.py")))
_components = _FIXTURE["_components"]
_persist_components = _FIXTURE["_persist_components"]
_prepare_ready_request = _FIXTURE["_prepare_ready_request"]
NOW = _FIXTURE["NOW"]
EVAL = _FIXTURE["EVAL"]
GUARDRAIL = _FIXTURE["GUARDRAIL"]


def _candidate() -> OpportunityCandidateSnapshot:
    return OpportunityCandidateSnapshot(
        captured_at=NOW,
        evaluation_date=EVAL,
        security_id="000660",
        thesis_snapshot_id="a" * 64,
        underwriting_readiness_snapshot_id="b" * 64,
        payoff_surface_snapshot_id="c" * 64,
        horizon_trading_days=120,
        research_class=OpportunityResearchClass.DEEP_READY,
        bear_return_lower=-0.30,
        base_return_lower=0.10,
        base_return_upper=0.30,
        bull_return_upper=0.60,
        nearest_catalyst_id="fixture-catalyst",
        nearest_catalyst_days=30,
        nearest_catalyst_evidence_refs=("fixture-evidence",),
        comparison_blockers=(),
        flags=(),
        guardrail_evidence_id=GUARDRAIL,
    )


def test_valuation_market_cap_is_recomputed_from_security_rows(tmp_path: Path) -> None:
    theses = _prepare_ready_request(tmp_path)
    valuation = _components(theses[0], 0)[12]
    forged_values = valuation.security_values.copy()
    forged_values.loc[:, "security_market_value"] = (
        forged_values["security_market_value"].astype(float) * 2.0
    )
    forged_metrics = _valuation_metrics(forged_values, valuation.financial_history)
    forged = replace(
        valuation,
        security_values=forged_values,
        valuation_metrics=forged_metrics,
    )
    write_valuation_evidence_snapshot(tmp_path / "valuation_evidence", forged)

    assert forged.snapshot_id != valuation.snapshot_id
    assert load_canonical_valuation_evidence(tmp_path, forged.snapshot_id) is None


def test_pointer_ownership_retains_linked_temp_inode_not_foreign_equal_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate()
    real_link = os.link
    linked_inode: int | None = None
    foreign_inode: int | None = None
    raced = False

    def racing_link(src, dst, *args, **kwargs):
        nonlocal linked_inode, foreign_inode, raced
        result = real_link(src, dst, *args, **kwargs)
        destination = Path(dst)
        if destination.name == "latest_opportunity_candidate.json" and not raced:
            raced = True
            linked_inode = Path(src).stat().st_ino
            payload = destination.read_bytes()
            destination.unlink()
            destination.write_bytes(payload)
            foreign_inode = destination.stat().st_ino
            assert foreign_inode != linked_inode
        return result

    monkeypatch.setattr(os, "link", racing_link)
    publication = assembler._persist_owned_opportunity_snapshot(candidate, output_root=tmp_path)
    assert publication.pointer_inode == linked_inode
    assert publication.pointer_inode != foreign_inode
    assert assembler._pointer_version_is_current(publication) is False
    foreign = publication.pointer.read_bytes()
    cleanup_errors: list[BaseException] = []
    assembler._rollback_owned_opportunity_publication(publication, cleanup_errors)
    assert cleanup_errors == []
    assert publication.pointer.read_bytes() == foreign


def test_existing_pointer_is_restored_when_no_replace_publication_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = tmp_path / "latest.json"
    pointer.write_bytes(b"old-pointer")
    identity = assembler._capture_file_identity(pointer)
    replacement = assembler._write_owned_pointer_temp(tmp_path, pointer.name, b"new-pointer")
    real_link = os.link
    failed_publication = False

    def failing_link(src, dst, *args, **kwargs):
        nonlocal failed_publication
        if Path(dst) == pointer and not pointer.exists() and not failed_publication:
            failed_publication = True
            raise OSError(errno.ENOSPC, "injected no space")
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", failing_link)
    try:
        with pytest.raises(OSError) as exc_info:
            assembler._replace_pointer_if_version_matches(
                replacement,
                pointer,
                expected_bytes=b"old-pointer",
                expected_identity=identity,
            )
        assert exc_info.value.errno == errno.ENOSPC
        assert pointer.read_bytes() == b"old-pointer"
    finally:
        replacement.unlink(missing_ok=True)


def test_opportunity_directory_foreign_replacement_survives_rollback(tmp_path: Path) -> None:
    publication = assembler._persist_owned_opportunity_snapshot(_candidate(), output_root=tmp_path)
    assert publication.directory_created is True
    shutil.rmtree(publication.directory)
    publication.directory.mkdir()
    marker = publication.directory / "foreign.txt"
    marker.write_text("foreign", encoding="utf-8")

    cleanup_errors: list[BaseException] = []
    assembler._rollback_owned_opportunity_publication(publication, cleanup_errors)
    assert cleanup_errors == []
    assert marker.read_text(encoding="utf-8") == "foreign"


def test_source_revalidation_trust_error_becomes_current_package_blocker(tmp_path: Path) -> None:
    theses = _prepare_ready_request(tmp_path)
    _persist_components(tmp_path, theses)
    source_repository = tmp_path / "valuation_evidence"
    duplicate_repository = tmp_path / "valuation"
    duplicate_repository.mkdir()
    source_directory = next(path for path in source_repository.iterdir() if path.is_dir())
    shutil.copytree(source_directory, duplicate_repository / source_directory.name)

    receipt = assembler.assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-source-revalidation-blocked",
        run_id="package-source-revalidation-blocked",
        processed_at=NOW + _FIXTURE["timedelta"](minutes=2),
        artifact_root=tmp_path,
    )
    assert receipt.orchestrated is None
    assert any(
        blocker.code == "underwriting_persisted_evidence_canonical_mismatch"
        for blocker in receipt.blockers
    )
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}


def test_old_predictable_opportunity_temp_symlink_is_never_followed(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlink unavailable")
    candidate = _candidate()
    root = tmp_path / "opportunity_candidate"
    root.mkdir()
    directory = assembler._opportunity_snapshot_directory(
        tmp_path,
        object_name="opportunity_candidate",
        captured_at=candidate.captured_at,
        snapshot_id=candidate.snapshot_id,
    )
    old_predictable = root / f".{directory.name}.{os.getpid()}.owned.tmp"
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "marker.txt"
    marker.write_text("unchanged", encoding="utf-8")
    try:
        old_predictable.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")

    publication = assembler._persist_owned_opportunity_snapshot(candidate, output_root=tmp_path)
    assert marker.read_text(encoding="utf-8") == "unchanged"
    assert publication.directory.is_dir()
    assert not publication.directory.is_symlink()


def test_creation_time_owned_writer_preserves_foreign_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_current = assembler._owned_file_is_current
    injected = False
    foreign = b'{"foreign":true}\n'

    def racing_current(publication):
        nonlocal injected
        if not injected:
            injected = True
            publication.path.unlink()
            publication.path.write_bytes(foreign)
        return real_current(publication)

    monkeypatch.setattr(assembler, "_owned_file_is_current", racing_current)
    with pytest.raises(RuntimeError, match="publication path changed"):
        assembler._persist_owned_content_addressed_json(
            root=tmp_path,
            repository_name="research_round_v2_1",
            snapshot_id="f" * 64,
            payload_without_id={"value": 1},
        )
    path = tmp_path / "research_round_v2_1" / f"{'f' * 64}.json"
    assert path.read_bytes() == foreign
