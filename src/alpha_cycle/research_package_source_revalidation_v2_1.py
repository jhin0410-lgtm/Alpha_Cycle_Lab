"""Hardened source-chain revalidation for Decision System v2.1 packages.

The pre-hardening implementation is preserved byte-for-byte in
``research_package_source_revalidation_legacy_v2_1``.  This module keeps those canonical typed
reconstructions, then adds the final independent-source gate required for valuation and certified
market-consensus evidence.
"""

from __future__ import annotations

from pathlib import Path

from alpha_cycle.intelligence.expectation_state import ExpectationStateSnapshot
from alpha_cycle.intelligence.forward_valuation import ForwardValuationStateSnapshot
from alpha_cycle.intelligence.research_source_evidence_v2_1 import (
    ResearchSourceEvidenceError,
    certified_expectation_sources_are_canonical,
    load_persisted_valuation_source,
    rebuild_valuation_evidence_from_source,
)
from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot
from alpha_cycle.research_package_integrity_v2_1 import require_trusted_artifact_root
import alpha_cycle.research_package_source_revalidation_legacy_v2_1 as _legacy

ResearchPackageSourceRevalidationError = _legacy.ResearchPackageSourceRevalidationError
epistemic_package_sources_are_canonical = _legacy.epistemic_package_sources_are_canonical
load_canonical_blind_spot = _legacy.load_canonical_blind_spot
load_canonical_counter_thesis = _legacy.load_canonical_counter_thesis
load_canonical_valuation_reference_frame = _legacy.load_canonical_valuation_reference_frame

_base_load_canonical_valuation_evidence = _legacy.load_canonical_valuation_evidence


def _find_bound_upstream_directory(
    root: Path,
    *,
    repository_names: tuple[str, ...],
    snapshot_id: str,
) -> Path | None:
    """Resolve exactly one trusted upstream snapshot by its persisted manifest identity."""

    resolved_root = require_trusted_artifact_root(root)
    matches: list[Path] = []
    for repository_name in repository_names:
        repository = root / repository_name
        if not repository.exists():
            continue
        if repository.is_symlink() or not repository.is_dir():
            raise ResearchPackageSourceRevalidationError(
                f"{repository_name} repository must be a regular directory"
            )
        resolved_repository = repository.resolve()
        if resolved_repository.parent != resolved_root:
            raise ResearchPackageSourceRevalidationError(
                f"{repository_name} repository escapes artifact_root"
            )
        for candidate in repository.iterdir():
            if candidate.is_symlink() or not candidate.is_dir():
                raise ResearchPackageSourceRevalidationError(
                    f"{repository_name} snapshot must be a regular directory"
                )
            if candidate.resolve().parent != resolved_repository:
                raise ResearchPackageSourceRevalidationError(
                    f"{repository_name} snapshot escapes repository"
                )
            manifest_path = candidate / "manifest.json"
            if not manifest_path.is_file():
                continue
            manifest = _legacy._read_json_regular(manifest_path, root)
            if str(manifest.get("snapshot_id", "")) == snapshot_id:
                matches.append(candidate)
    if len(matches) > 1:
        raise ResearchPackageSourceRevalidationError(
            "upstream snapshot identity is ambiguous across trusted repositories"
        )
    return matches[0] if matches else None


def _valuation_sources_are_canonical(
    root: Path,
    snapshot: ValuationEvidenceSnapshot,
) -> bool:
    """Rebuild valuation from a separately persisted input capture and bound upstream bytes."""

    if not isinstance(snapshot.raw_valuation, dict):
        return False
    source_id = str(snapshot.raw_valuation.get("source_valuation_snapshot_id", "")).strip()
    if len(source_id) != 64 or any(
        character not in "0123456789abcdef" for character in source_id
    ):
        return False
    try:
        source = load_persisted_valuation_source(root, source_id)
        if source is None:
            return False
        if (
            source.research_snapshot_id != snapshot.research_snapshot_id
            or source.market_snapshot_id != snapshot.market_snapshot_id
            or source.evaluation_date != snapshot.evaluation_date
            or source.history_years != snapshot.history_years
            or source.captured_at > snapshot.captured_at
        ):
            return False
        research_directory = _find_bound_upstream_directory(
            root,
            repository_names=("research-intelligence", "research_intelligence", "research"),
            snapshot_id=source.research_snapshot_id,
        )
        market_directory = _find_bound_upstream_directory(
            root,
            repository_names=("market-intelligence", "market_intelligence", "market"),
            snapshot_id=source.market_snapshot_id,
        )
        if research_directory is None or market_directory is None:
            return False
        rebuilt = rebuild_valuation_evidence_from_source(
            source,
            research_snapshot=research_directory,
            market_snapshot=market_directory,
            captured_at=snapshot.captured_at,
        )
    except (
        OSError,
        ResearchPackageSourceRevalidationError,
        ResearchSourceEvidenceError,
        TypeError,
        ValueError,
    ):
        return False
    return bool(
        rebuilt.snapshot_id == snapshot.snapshot_id
        and rebuilt.payload_without_id() == snapshot.payload_without_id()
    )


def load_canonical_valuation_evidence(
    root: Path,
    snapshot_id: str,
) -> ValuationEvidenceSnapshot | None:
    """Load structurally canonical valuation evidence and require independent source replay."""

    snapshot = _base_load_canonical_valuation_evidence(root, snapshot_id)
    if snapshot is None:
        return None
    return snapshot if _valuation_sources_are_canonical(root, snapshot) else None


# The legacy forward/price-implied rebuilds resolve this module global at call time.  Repoint their
# module global to the hardened loader so both chains inherit valuation-source replay without
# duplicating the established canonical builder logic.
_legacy.load_canonical_valuation_evidence = load_canonical_valuation_evidence


def forward_valuation_sources_are_canonical(
    root: str | Path,
    *,
    snapshot: ForwardValuationStateSnapshot,
    expectations: ExpectationStateSnapshot,
) -> bool:
    """Require provider-source replay before rebuilding forward valuation."""

    if not certified_expectation_sources_are_canonical(
        root,
        expectations.observations,
        expectations.source_snapshot_ids,
        captured_at=expectations.captured_at,
    ):
        return False
    return _legacy.forward_valuation_sources_are_canonical(
        root,
        snapshot=snapshot,
        expectations=expectations,
    )


def price_implied_sources_are_canonical(*args: object, **kwargs: object) -> bool:
    """Delegate to the canonical builder with the hardened valuation loader installed."""

    return bool(_legacy.price_implied_sources_are_canonical(*args, **kwargs))


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
