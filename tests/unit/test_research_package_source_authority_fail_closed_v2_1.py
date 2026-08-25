"""Adversarial regressions for unavailable valuation/consensus source authority."""

from __future__ import annotations

import importlib.util
import os
import shutil
from datetime import timedelta
from pathlib import Path
from runpy import run_path

import pytest

import alpha_cycle.research_package_assembler_v2_1 as assembler
from alpha_cycle.intelligence.decision_view_v2_1 import build_decision_expectation_gap
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundMode,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import ResearchRunKind
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_package_assembler_v2_1 import assemble_and_run_research_package
from alpha_cycle.research_package_canonical_evidence_v2_1 import (
    decision_gap_bound_sources_are_canonical,
)
from alpha_cycle.research_package_source_revalidation_v2_1 import (
    forward_valuation_sources_are_canonical,
    price_implied_sources_are_canonical,
)

_FIXTURES = run_path(
    str(Path(__file__).with_name("_research_package_assembler_legacy_v2_1.py"))
)


def _deep_components():
    thesis = _FIXTURES["_thesis"]("000660")
    return _FIXTURES["_components"](thesis, 0)


def test_self_certified_consensus_cannot_establish_deep_forward_authority(
    tmp_path: Path,
) -> None:
    components = _deep_components()
    expectations = components[8]
    forward_valuation = components[9]

    observation = expectations.observations[0]
    assert observation.market_consensus_certified is True
    assert observation.semantics.provider_id == "provider-a"
    assert (
        forward_valuation_sources_are_canonical(
            tmp_path,
            snapshot=forward_valuation,
            expectations=expectations,
        )
        is False
    )


def test_self_consistent_valuation_cannot_establish_price_implied_authority(
    tmp_path: Path,
) -> None:
    components = _deep_components()
    price_implied = components[10]
    valuation = components[12]

    assert valuation.valuation_metrics["market_cap_complete"].astype(bool).all()
    assert price_implied_sources_are_canonical(tmp_path, snapshot=price_implied) is False


def test_self_certified_consensus_gap_has_no_provider_authority(tmp_path: Path) -> None:
    components = _deep_components()
    view = components[1]
    expectations = components[8]
    gap = build_decision_expectation_gap(
        view,
        expectations,
        captured_at=components[2].captured_at,
        evaluation_date=components[2].evaluation_date,
    )
    _FIXTURES["persist_expectation_state"](
        expectations,
        output_root=tmp_path / "expectation_state",
    )

    assert gap.consensus_gaps
    assert not decision_gap_bound_sources_are_canonical(tmp_path, view=view, gap=gap)


def test_unproven_deep_authority_blocks_before_orchestration(tmp_path: Path) -> None:
    theses = _FIXTURES["_prepare_ready_request"](tmp_path)
    _FIXTURES["_persist_components"](tmp_path, theses)

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-unproven-source-authority",
        run_id="package-unproven-source-authority",
        processed_at=_FIXTURES["NOW"] + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.full_package_ready is False
    assert receipt.orchestrated is None
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    assert any(
        blocker.code == "underwriting_persisted_evidence_canonical_mismatch"
        for blocker in receipt.blockers
    )
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_self_certified_consensus_cannot_publish_through_fast_lane(
    tmp_path: Path,
) -> None:
    now = _FIXTURES["NOW"]
    evaluation_date = _FIXTURES["EVAL"]
    _FIXTURES["record_analysis_request"](
        request_id="fast-self-certified-consensus",
        requested_at=now,
        recorded_at=now + timedelta(seconds=1),
        evaluation_date=evaluation_date,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.FAST,
        request_text="Fast package must not trust self-certified consensus.",
        artifact_root=tmp_path,
    )
    theses = tuple(_FIXTURES["_thesis"](item) for item in ("000660", "005930"))
    for thesis in theses:
        _FIXTURES["persist_investment_thesis"](thesis, artifact_root=tmp_path)
    preflight = _FIXTURES["preflight_pending_request_theses"](
        request_id="fast-self-certified-consensus",
        run_id="fast-thesis-ready",
        processed_at=now + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    assert preflight.ready_for_package_assembly is True

    for offset, thesis in enumerate(theses):
        components = _FIXTURES["_components"](thesis, offset)
        payoff, view = components[0], components[1]
        registrations, selection_rule = components[4], components[5]
        context, causal_graph, expectations = components[6], components[7], components[8]
        epistemic = components[11]
        gap = build_decision_expectation_gap(
            view,
            expectations,
            captured_at=components[2].captured_at,
            evaluation_date=evaluation_date,
        )
        underwriting = _FIXTURES["build_underwriting_readiness"](
            thesis,
            context,
            lane=UnderwritingLane.FAST,
            captured_at=components[3].captured_at,
            evaluation_date=evaluation_date,
            forecasts=registrations,
            causal_graph=causal_graph,
            expectations=expectations,
            payoff_surface=payoff,
            epistemic_defense=epistemic,
        )
        _FIXTURES["persist_decision_view_selection_rule"](
            selection_rule, output_root=tmp_path
        )
        for registration in registrations:
            _FIXTURES["persist_forecast_registration"](
                registration, output_root=tmp_path
            )
        _FIXTURES["persist_underwriting_context"](context, output_root=tmp_path)
        _FIXTURES["persist_semiconductor_causal_graph"](
            causal_graph,
            output_root=tmp_path / "semiconductor_causal_graph",
        )
        _FIXTURES["persist_expectation_state"](
            expectations,
            output_root=tmp_path / "expectation_state",
        )
        _FIXTURES["persist_epistemic_defense_package"](
            epistemic, output_root=tmp_path
        )
        _FIXTURES["persist_payoff_surface"](
            payoff, output_root=tmp_path / "payoff_surface"
        )
        _FIXTURES["persist_decision_view"](view, output_root=tmp_path)
        _FIXTURES["persist_decision_expectation_gap"](gap, output_root=tmp_path)
        _FIXTURES["persist_underwriting_readiness"](
            underwriting, output_root=tmp_path
        )

    receipt = assemble_and_run_research_package(
        request_id="fast-self-certified-consensus",
        round_id="round-fast-self-certified-consensus",
        run_id="package-fast-self-certified-consensus",
        processed_at=now + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.full_package_ready is False
    assert receipt.orchestrated is None
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    assert any(
        item.code == "decision_gap_persisted_source_binding_mismatch"
        for item in receipt.blockers
    ), {item.code for item in receipt.blockers}
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_self_authored_price_implied_gap_cannot_publish_through_fast_lane(
    tmp_path: Path,
) -> None:
    now = _FIXTURES["NOW"]
    evaluation_date = _FIXTURES["EVAL"]
    _FIXTURES["record_analysis_request"](
        request_id="fast-self-authored-price-gap",
        requested_at=now,
        recorded_at=now + timedelta(seconds=1),
        evaluation_date=evaluation_date,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        mode=ResearchRoundMode.PROSPECTIVE,
        requested_lane=UnderwritingLane.FAST,
        request_text="Fast package must not trust self-authored price-implied gaps.",
        artifact_root=tmp_path,
    )
    theses = tuple(_FIXTURES["_thesis"](item) for item in ("000660", "005930"))
    for thesis in theses:
        _FIXTURES["persist_investment_thesis"](thesis, artifact_root=tmp_path)
    preflight = _FIXTURES["preflight_pending_request_theses"](
        request_id="fast-self-authored-price-gap",
        run_id="fast-price-thesis-ready",
        processed_at=now + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    assert preflight.ready_for_package_assembly is True

    for offset, thesis in enumerate(theses):
        components = _FIXTURES["_components"](thesis, offset)
        payoff, view = components[0], components[1]
        registrations, selection_rule = components[4], components[5]
        context, causal_graph = components[6], components[7]
        expectations = components[8]
        price_implied, epistemic = components[10], components[11]
        gap = build_decision_expectation_gap(
            view,
            expectations,
            captured_at=components[2].captured_at,
            evaluation_date=evaluation_date,
            price_implied=price_implied,
        )
        # The typed gap schema always includes consensus evidence; this regression also
        # binds independently self-authored price-implied evidence while underwriting
        # intentionally does not claim that price snapshot as an authority source.
        assert gap.consensus_gaps
        assert gap.price_implied_gaps
        underwriting = _FIXTURES["build_underwriting_readiness"](
            thesis,
            context,
            lane=UnderwritingLane.FAST,
            captured_at=components[3].captured_at,
            evaluation_date=evaluation_date,
            forecasts=registrations,
            causal_graph=causal_graph,
            expectations=expectations,
            payoff_surface=payoff,
            epistemic_defense=epistemic,
        )
        assert underwriting.price_implied_requirement_snapshot_id is None
        _FIXTURES["persist_decision_view_selection_rule"](
            selection_rule, output_root=tmp_path
        )
        for registration in registrations:
            _FIXTURES["persist_forecast_registration"](
                registration, output_root=tmp_path
            )
        _FIXTURES["persist_underwriting_context"](context, output_root=tmp_path)
        _FIXTURES["persist_semiconductor_causal_graph"](
            causal_graph,
            output_root=tmp_path / "semiconductor_causal_graph",
        )
        _FIXTURES["persist_expectation_state"](
            expectations,
            output_root=tmp_path / "expectation_state",
        )
        _FIXTURES["persist_price_implied_requirement"](
            price_implied,
            output_root=tmp_path,
        )
        assert not decision_gap_bound_sources_are_canonical(
            tmp_path,
            view=view,
            gap=gap,
        )
        _FIXTURES["persist_epistemic_defense_package"](
            epistemic, output_root=tmp_path
        )
        _FIXTURES["persist_payoff_surface"](
            payoff, output_root=tmp_path / "payoff_surface"
        )
        _FIXTURES["persist_decision_view"](view, output_root=tmp_path)
        _FIXTURES["persist_decision_expectation_gap"](gap, output_root=tmp_path)
        _FIXTURES["persist_underwriting_readiness"](
            underwriting, output_root=tmp_path
        )

    receipt = assemble_and_run_research_package(
        request_id="fast-self-authored-price-gap",
        round_id="round-fast-self-authored-price-gap",
        run_id="package-fast-self-authored-price-gap",
        processed_at=now + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.full_package_ready is False
    assert receipt.orchestrated is None
    assert receipt.run is not None
    assert receipt.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED
    assert any(
        item.code == "decision_gap_persisted_source_binding_mismatch"
        for item in receipt.blockers
    ), {item.code for item in receipt.blockers}
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_repository_validation_failure_is_current_structured_blocker(
    tmp_path: Path,
) -> None:
    theses = _FIXTURES["_prepare_ready_request"](tmp_path)
    _FIXTURES["_persist_components"](tmp_path, theses)
    manifest = next((tmp_path / "payoff_surface").glob("*/manifest.json"))
    manifest.write_text("{malformed", encoding="utf-8")

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-malformed-repository",
        run_id="package-malformed-repository",
        processed_at=_FIXTURES["NOW"] + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.orchestrated is None
    assert [(item.component, item.code) for item in receipt.blockers] == [
        (
            "research_package_repository",
            "persisted_research_package_repository_validation_failed",
        )
    ]
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_invalid_utf8_repository_data_is_current_structured_blocker(
    tmp_path: Path,
) -> None:
    theses = _FIXTURES["_prepare_ready_request"](tmp_path)
    _FIXTURES["_persist_components"](tmp_path, theses)
    manifest = next((tmp_path / "payoff_surface").glob("*/manifest.json"))
    manifest.write_bytes(b"\xff\xfe\xfa")

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-invalid-utf8-repository",
        run_id="package-invalid-utf8-repository",
        processed_at=_FIXTURES["NOW"] + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.orchestrated is None
    assert [item.code for item in receipt.blockers] == [
        "persisted_research_package_repository_validation_failed"
    ]
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_duplicate_repository_identity_is_current_structured_blocker(
    tmp_path: Path,
) -> None:
    theses = _FIXTURES["_prepare_ready_request"](tmp_path)
    _FIXTURES["_persist_components"](tmp_path, theses)
    repository = tmp_path / "payoff_surface"
    original = next(path for path in repository.iterdir() if path.is_dir())
    duplicate = repository / f"{original.name}-duplicate"
    shutil.copytree(original, duplicate)

    receipt = assemble_and_run_research_package(
        request_id="typed-package-round",
        round_id="round-duplicate-repository",
        run_id="package-duplicate-repository",
        processed_at=_FIXTURES["NOW"] + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert receipt.orchestrated is None
    assert any(
        item.code == "persisted_research_package_repository_validation_failed"
        for item in receipt.blockers
    )
    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert {row.state for row in state.inbox} == {"pre_orchestration_blocked"}


def test_descriptor_bound_pointer_cannot_publish_foreign_temp_inode(
    tmp_path: Path,
) -> None:
    if os.name == "nt":
        pytest.skip("descriptor-relative publication is POSIX-only")
    repository = tmp_path / "opportunity_candidate"
    repository.mkdir()
    directory_fd = os.open(repository, assembler._directory_open_flags())
    temporary_fd: int | None = None
    try:
        temporary_fd, identity, cleanup_name = assembler._write_owned_pointer_temp_at(
            directory_fd,
            "latest_opportunity_candidate.json",
            b'{"owned":true}\n',
        )
        foreign = repository / ".latest_opportunity_candidate.json.foreign.owned.tmp"
        foreign.write_bytes(b'{"foreign":true}\n')
        foreign_inode = foreign.stat().st_ino

        assembler._link_open_file_at(
            temporary_fd,
            directory_fd,
            "latest_opportunity_candidate.json",
        )

        pointer = repository / "latest_opportunity_candidate.json"
        assert pointer.read_bytes() == b'{"owned":true}\n'
        assert pointer.stat().st_ino == identity[0]
        assert pointer.stat().st_ino != foreign_inode
        if cleanup_name is not None:
            assert assembler._unlink_pointer_if_version_matches_at(
                directory_fd,
                cleanup_name,
                expected_bytes=b'{"owned":true}\n',
                expected_identity=identity,
            )
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        os.close(directory_fd)


def test_named_descriptor_pointer_fallback_works_without_o_tmpfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name == "nt":
        pytest.skip("descriptor-relative publication is POSIX-only")
    repository = tmp_path / "opportunity_candidate"
    repository.mkdir()
    directory_fd = os.open(repository, assembler._directory_open_flags())
    temporary_fd: int | None = None
    cleanup_name: str | None = None
    content = b'{"fallback":true}\n'
    monkeypatch.setattr(assembler.os, "O_TMPFILE", 0, raising=False)
    try:
        temporary_fd, identity, cleanup_name = assembler._write_owned_pointer_temp_at(
            directory_fd,
            "latest_opportunity_candidate.json",
            content,
        )
        assert cleanup_name is not None
        assembler._link_open_file_at(
            temporary_fd,
            directory_fd,
            "latest_opportunity_candidate.json",
        )
        pointer = repository / "latest_opportunity_candidate.json"
        assert pointer.read_bytes() == content
        assert pointer.stat().st_ino == identity[0]
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if cleanup_name is not None:
            (repository / cleanup_name).unlink(missing_ok=True)
        os.close(directory_fd)


def test_unsupported_descriptor_backend_fails_before_pointer_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name == "nt":
        pytest.skip("descriptor-relative publication is POSIX-only")
    repository = tmp_path / "opportunity_candidate"
    repository.mkdir()
    directory_fd = os.open(repository, assembler._directory_open_flags())
    monkeypatch.setattr(assembler.os, "O_TMPFILE", 0, raising=False)

    def unsupported(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("descriptor-stable pointer linking is unavailable")

    monkeypatch.setattr(assembler, "_link_open_file_at", unsupported)
    try:
        with pytest.raises(
            RuntimeError,
            match="descriptor-stable pointer linking is unavailable",
        ):
            assembler._probe_descriptor_pointer_publication_at(directory_fd)
    finally:
        os.close(directory_fd)

    assert tuple(repository.iterdir()) == ()


def test_removed_normalized_source_envelope_cannot_reintroduce_check_then_reopen_path() -> None:
    assert (
        importlib.util.find_spec(
            "alpha_cycle.intelligence.research_source_evidence_v2_1"
        )
        is None
    )
