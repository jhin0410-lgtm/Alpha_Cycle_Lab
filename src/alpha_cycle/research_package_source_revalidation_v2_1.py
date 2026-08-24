"""Fail-closed source-chain revalidation for Decision System v2.1 packages.

The established v2.1 canonical replay remains available for source contracts that have an
independent authority boundary.  Valuation and certified market-consensus evidence do not yet
have that boundary: the attempted normalized source envelopes could be created from the derived
objects they were supposed to authenticate.  Until a production acquisition contract can replay
those inputs from independently authoritative provider evidence, valuation-derived Deep evidence
must not satisfy the package merge gate.
"""

from __future__ import annotations

from pathlib import Path

import alpha_cycle.research_package_source_revalidation_legacy_v2_1 as _legacy
from alpha_cycle.intelligence.expectation_state import ExpectationStateSnapshot
from alpha_cycle.intelligence.forward_valuation import ForwardValuationStateSnapshot
from alpha_cycle.intelligence.price_implied_requirement import PriceImpliedRequirementSnapshot
from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot

ResearchPackageSourceRevalidationError = _legacy.ResearchPackageSourceRevalidationError
epistemic_package_sources_are_canonical = _legacy.epistemic_package_sources_are_canonical
load_canonical_blind_spot = _legacy.load_canonical_blind_spot
load_canonical_counter_thesis = _legacy.load_canonical_counter_thesis
load_canonical_valuation_reference_frame = _legacy.load_canonical_valuation_reference_frame


def load_canonical_valuation_evidence(
    root: Path,
    snapshot_id: str,
) -> ValuationEvidenceSnapshot | None:
    """Load structural valuation evidence without promoting it to source authority."""

    return _legacy.load_canonical_valuation_evidence(root, snapshot_id)


def forward_valuation_sources_are_canonical(
    root: str | Path,
    *,
    snapshot: ForwardValuationStateSnapshot,
    expectations: ExpectationStateSnapshot,
) -> bool:
    """Fail closed until an independent provider authority can replay both inputs.

    A self-consistent valuation envelope and a self-declared certified expectation are not
    independent evidence.  Accepting either would let rewritten derived artifacts manufacture a
    Deep-comparable forward valuation, so the production package gate remains closed.
    """

    _ = root, snapshot, expectations
    return False


def price_implied_sources_are_canonical(
    root: str | Path,
    *,
    snapshot: PriceImpliedRequirementSnapshot,
) -> bool:
    """Fail closed until valuation inputs are replayable from independent source authority."""

    _ = root, snapshot
    return False


__all__ = [
    "ResearchPackageSourceRevalidationError",
    "epistemic_package_sources_are_canonical",
    "forward_valuation_sources_are_canonical",
    "load_canonical_blind_spot",
    "load_canonical_counter_thesis",
    "load_canonical_valuation_evidence",
    "load_canonical_valuation_reference_frame",
    "price_implied_sources_are_canonical",
]
