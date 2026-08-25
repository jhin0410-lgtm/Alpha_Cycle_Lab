"""Fail-closed source-chain revalidation for Decision System v2.1 packages.

The established v2.1 canonical replay remains available for source contracts that have an
independent authority boundary.  The valuation-authority v2.1 boundary can now replay canonical
market/company actuals and persist exact blockers, but the available share-count and complete
capital-structure inputs remain non-authoritative.  Certified market consensus also remains
unavailable.  Until an authority artifact has an eligible method, valuation-derived Deep evidence
must not satisfy the package merge gate.
"""

from __future__ import annotations

from pathlib import Path

import alpha_cycle.research_package_source_revalidation_legacy_v2_1 as _legacy
from alpha_cycle.intelligence.expectation_state import ExpectationStateSnapshot
from alpha_cycle.intelligence.forward_valuation import ForwardValuationStateSnapshot
from alpha_cycle.intelligence.price_implied_requirement import PriceImpliedRequirementSnapshot
from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot
from alpha_cycle.provider_forward_authority_v2_1 import (
    PROVIDER_ID,
    ProviderForwardAuthorityError,
    provider_authority_can_certify_expectation,
    replay_persisted_kis_provider_authority,
)

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


def expectation_sources_are_canonical(
    root: str | Path,
    *,
    snapshot: ExpectationStateSnapshot,
) -> bool:
    """Require provider-specific raw replay for every typed expectation observation."""

    repository = Path(root) / "provider_forward_authority_v2_1"
    if repository.is_symlink() or not repository.is_dir():
        return False
    for observation in snapshot.observations:
        if observation.provider_id != PROVIDER_ID:
            return False
        try:
            matches = tuple(
                path
                for path in repository.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and path.name.endswith(f"__{observation.source_evidence_id[:12]}")
            )
        except OSError:
            return False
        if len(matches) != 1:
            return False
        try:
            authority = replay_persisted_kis_provider_authority(
                matches[0],
                evaluation_date=snapshot.evaluation_date,
                maximum_research_cutoff_at=snapshot.captured_at,
                expected_artifact_id=observation.source_evidence_id,
            )
        except (OSError, TypeError, ProviderForwardAuthorityError, ValueError):
            return False
        if not provider_authority_can_certify_expectation(
            authority,
            provider_id=observation.provider_id,
            security_id=observation.security_id,
            metric=observation.metric.value,
            target_period=observation.target_period,
            market_consensus_certified=observation.market_consensus_certified,
        ):
            return False
    return True


def price_implied_sources_are_canonical(
    root: str | Path,
    *,
    snapshot: PriceImpliedRequirementSnapshot,
) -> bool:
    """Fail closed while current valuation-authority artifacts have no eligible method.

    The v2.1 authority repository records why the inputs are blocked; a caller-created
    PriceImpliedRequirementSnapshot cannot promote that negative result into source authority.
    """

    _ = root, snapshot
    return False


__all__ = [
    "ResearchPackageSourceRevalidationError",
    "epistemic_package_sources_are_canonical",
    "expectation_sources_are_canonical",
    "forward_valuation_sources_are_canonical",
    "load_canonical_blind_spot",
    "load_canonical_counter_thesis",
    "load_canonical_valuation_evidence",
    "load_canonical_valuation_reference_frame",
    "price_implied_sources_are_canonical",
]
