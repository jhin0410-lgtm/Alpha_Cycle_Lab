from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest

import alpha_cycle.research_package_assembler_v2_1 as assembler
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OpportunityCandidateSnapshot,
    OpportunityResearchClass,
)
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state

_FIXTURE = run_path(str(Path(__file__).with_name("test_research_package_assembler_v2_1.py")))
_prepare_ready_request = _FIXTURE["_prepare_ready_request"]
_persist_components = _FIXTURE["_persist_components"]
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


def _replace_repository_with_external_symlink(
    repository: Path, outside: Path
) -> Path:
    displaced = repository.with_name(repository.name + "-displaced")
    repository.rename(displaced)
    try:
        repository.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation unavailable")
    return displaced


def test_pinned_content_repository_never_follows_replaced_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    publication_root = assembler._open_pinned_publication_root(root)
    repository = assembler._pin_publication_repository(
        publication_root, "research_round_v2_1"
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    displaced = _replace_repository_with_external_symlink(repository.public_path, outside)
    try:
        assembler._persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_round_v2_1",
            repository_root=repository.io_path,
            repository_fd=repository.fd,
            snapshot_id="f" * 64,
            payload_without_id={"value": 1},
        )
        assert list(outside.iterdir()) == []
        assert (displaced / f"{'f' * 64}.json").is_file()
        assert assembler._publication_namespace_is_current(publication_root) is False
    finally:
        assembler._close_pinned_publication_root(publication_root)


def test_pinned_opportunity_repository_never_follows_replaced_ancestor(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    publication_root = assembler._open_pinned_publication_root(root)
    repository = assembler._pin_publication_repository(
        publication_root, "opportunity_candidate"
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    displaced = _replace_repository_with_external_symlink(repository.public_path, outside)
    try:
        publication = assembler._persist_owned_opportunity_snapshot(
            _candidate(),
            output_root=publication_root.public_root,
            repository_root=repository.io_path,
            repository_fd=repository.fd,
        )
        assert list(outside.iterdir()) == []
        assert publication.directory.parent.samefile(displaced)
        assert assembler._publication_namespace_is_current(publication_root) is False
    finally:
        assembler._close_pinned_publication_root(publication_root)


def test_malformed_valuation_source_becomes_current_package_blocker(tmp_path: Path) -> None:
    theses = _prepare_ready_request(tmp_path)
    _persist_components(tmp_path, theses)
    manifest = next((tmp_path / "valuation_evidence").glob("*/manifest.json"))
    manifest.write_text("{not-json", encoding="utf-8")

    receipt = assembler.assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-malformed-valuation",
        run_id="run-malformed-valuation",
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


def test_malformed_decision_view_source_becomes_current_package_blocker(tmp_path: Path) -> None:
    theses = _prepare_ready_request(tmp_path)
    _persist_components(tmp_path, theses)
    payload = next(
        (tmp_path / "decision_view_selection_rule").glob(
            "*/decision_view_selection_rule.json"
        )
    )
    payload.write_text("{not-json", encoding="utf-8")

    receipt = assembler.assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-malformed-decision-view",
        run_id="run-malformed-decision-view",
        processed_at=NOW + _FIXTURE["timedelta"](minutes=2),
        artifact_root=tmp_path,
    )
    assert receipt.orchestrated is None
    assert any(
        blocker.code in {
            "decision_view_persisted_selection_invalid",
            "underwriting_decision_view_tournament_binding_mismatch",
        }
        for blocker in receipt.blockers
    )
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}
