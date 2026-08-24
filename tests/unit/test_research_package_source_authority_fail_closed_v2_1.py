"""Adversarial regressions for unavailable valuation/consensus source authority."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from runpy import run_path

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


def test_removed_normalized_source_envelope_cannot_reintroduce_check_then_reopen_path() -> None:
    assert (
        importlib.util.find_spec(
            "alpha_cycle.intelligence.research_source_evidence_v2_1"
        )
        is None
    )
