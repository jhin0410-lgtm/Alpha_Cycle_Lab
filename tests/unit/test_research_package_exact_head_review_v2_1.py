from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path
from runpy import run_path

import pytest

import alpha_cycle.research_package_assembler_v2_1 as assembler
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OpportunityCandidateSnapshot,
    OpportunityResearchClass,
)
from alpha_cycle.research_package_source_revalidation_v2_1 import (
    epistemic_package_sources_are_canonical,
    forward_valuation_sources_are_canonical,
    price_implied_sources_are_canonical,
)

_FIXTURE = run_path(
    str(Path(__file__).with_name("test_research_package_assembler_v2_1.py"))
)
_components = _FIXTURE["_components"]
_persist_components = _FIXTURE["_persist_components"]
_prepare_ready_request = _FIXTURE["_prepare_ready_request"]
NOW = _FIXTURE["NOW"]
EVAL = _FIXTURE["EVAL"]
GUARDRAIL = _FIXTURE["GUARDRAIL"]


def _materialized_sources(tmp_path: Path):
    theses = _prepare_ready_request(tmp_path)
    _persist_components(tmp_path, theses)
    components = _components(theses[0], 0)
    return theses[0], components


def test_epistemic_package_requires_real_counter_and_blind_spot_sources(tmp_path: Path) -> None:
    thesis, components = _materialized_sources(tmp_path)
    epistemic = components[11]
    forged = replace(epistemic, counter_thesis_snapshot_id="f" * 64)

    assert epistemic_package_sources_are_canonical(
        tmp_path, thesis=thesis, snapshot=epistemic
    ) is True
    assert epistemic_package_sources_are_canonical(
        tmp_path, thesis=thesis, snapshot=forged
    ) is False


def test_forward_valuation_requires_real_market_cap_source(tmp_path: Path) -> None:
    _thesis, components = _materialized_sources(tmp_path)
    expectations = components[8]
    forward = components[9]
    forged = replace(forward, valuation_evidence_snapshot_id="f" * 64)

    assert forward_valuation_sources_are_canonical(
        tmp_path, snapshot=forward, expectations=expectations
    ) is True
    assert forward_valuation_sources_are_canonical(
        tmp_path, snapshot=forged, expectations=expectations
    ) is False


def test_price_implied_requires_real_valuation_and_reference_frame(tmp_path: Path) -> None:
    _thesis, components = _materialized_sources(tmp_path)
    price_implied = components[10]
    forged = replace(price_implied, reference_frame_snapshot_id="f" * 64)

    assert price_implied_sources_are_canonical(tmp_path, snapshot=price_implied) is True
    assert price_implied_sources_are_canonical(tmp_path, snapshot=forged) is False


def test_conditional_pointer_publish_never_overwrites_concurrent_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pointer = tmp_path / "latest.json"
    pointer.write_bytes(b"old")
    expected_identity = assembler._capture_file_identity(pointer)
    replacement = assembler._write_owned_pointer_temp(tmp_path, pointer.name, b"ours")
    foreign = b"foreign"
    real_link = os.link

    def racing_link(src, dst, *args, **kwargs):
        if Path(dst) == pointer and Path(src) == replacement and not pointer.exists():
            pointer.write_bytes(foreign)
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    try:
        assert (
            assembler._replace_pointer_if_version_matches(
                replacement,
                pointer,
                expected_bytes=b"old",
                expected_identity=expected_identity,
            )
            is False
        )
        assert pointer.read_bytes() == foreign
    finally:
        replacement.unlink(missing_ok=True)


def test_owned_file_rollback_never_deletes_concurrent_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "round.json"
    path.write_bytes(b"owned")
    publication = assembler._capture_owned_file(path)
    real_replace = os.replace
    foreign = b"foreign-round"
    injected = False

    def racing_replace(src, dst, *args, **kwargs):
        nonlocal injected
        result = real_replace(src, dst, *args, **kwargs)
        if Path(src) == path and not injected:
            injected = True
            path.write_bytes(foreign)
        return result

    monkeypatch.setattr(os, "replace", racing_replace)
    assert assembler._unlink_owned_file_if_current(publication) is True
    assert path.read_bytes() == foreign
    assert hashlib.sha256(path.read_bytes()).hexdigest() != publication.sha256


def test_absent_pointer_link_loser_never_claims_foreign_equal_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = OpportunityCandidateSnapshot(
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
    real_link = os.link
    raced = False

    def racing_link(src, dst, *args, **kwargs):
        nonlocal raced
        destination = Path(dst)
        if destination.name == "latest_opportunity_candidate.json" and not raced:
            raced = True
            destination.write_bytes(Path(src).read_bytes())
            raise FileExistsError(destination)
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    publication = assembler._persist_owned_opportunity_snapshot(
        candidate, output_root=tmp_path
    )
    assert publication.pointer_inode == -1
    foreign_bytes = publication.pointer.read_bytes()
    cleanup_errors: list[BaseException] = []
    assembler._rollback_owned_opportunity_publication(publication, cleanup_errors)
    assert cleanup_errors == []
    assert publication.pointer.exists()
    assert publication.pointer.read_bytes() == foreign_bytes
    assert publication.directory.exists()
