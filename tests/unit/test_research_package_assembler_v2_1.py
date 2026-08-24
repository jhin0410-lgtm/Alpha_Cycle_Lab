"""Assembler mechanics regressions isolated from the production source-authority gate.

The preserved legacy fixture exercises package assembly, persistence, rollback, and blocker
semantics.  Those tests predate an independently authoritative valuation/consensus acquisition
contract, so they use the established canonical derived-artifact replay locally.  Production
source-authority behavior is covered separately by adversarial fail-closed tests.
"""

from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest

import alpha_cycle.research_package_source_revalidation_legacy_v2_1 as _legacy_gate
import alpha_cycle.research_package_source_revalidation_v2_1 as _production_gate

_namespace = run_path(
    str(Path(__file__).with_name("_research_package_assembler_legacy_v2_1.py"))
)
for _name, _value in _namespace.items():
    if not _name.startswith("__"):
        globals()[_name] = _value


@pytest.fixture(autouse=True)
def _isolate_legacy_assembler_source_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep legacy assembler tests focused on their original non-authority invariants."""

    monkeypatch.setattr(
        _production_gate,
        "forward_valuation_sources_are_canonical",
        _legacy_gate.forward_valuation_sources_are_canonical,
    )
    monkeypatch.setattr(
        _production_gate,
        "price_implied_sources_are_canonical",
        _legacy_gate.price_implied_sources_are_canonical,
    )
