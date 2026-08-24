"""Adversarial regressions for unavailable valuation/consensus source authority."""

from __future__ import annotations

import importlib.util
from datetime import timedelta
from pathlib import Path
from runpy import run_path

from alpha_cycle.intelligence.research_run_ledger_v2_1 import ResearchRunKind
from alpha_cycle.research_package_assembler_v2_1 import assemble_and_run_research_package
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
    assert receipt.blockers
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
    assert not (tmp_path / "research_round_v2_1").exists()


def test_removed_normalized_source_envelope_cannot_reintroduce_check_then_reopen_path() -> None:
    assert (
        importlib.util.find_spec(
            "alpha_cycle.intelligence.research_source_evidence_v2_1"
        )
        is None
    )
