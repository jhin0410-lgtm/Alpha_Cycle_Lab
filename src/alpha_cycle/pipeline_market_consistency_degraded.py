"""Compose the exact market gate with strictly validated degraded modes."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, cast

from alpha_cycle import pipeline_market_consistency as strict_gate
from alpha_cycle.adjusted_market_consistency_compat import (
    adjusted_market_consistency_runtime,
)
from alpha_cycle.intelligence.adjustment_basis_market_provenance import (
    load_adjustment_basis_primary_source_provenance,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)
from alpha_cycle.intelligence.primary_source_market_provenance import (
    load_primary_source_market_provenance,
)

_LOADER_ATTRIBUTE = "load_market_consistency_provenance"
_DEGRADED_GATE_LOCK = threading.Lock()


def run_pipeline_market_consistency_gate(
    *,
    output_root: str | Path,
    market_directory: str | Path,
    decision_symbols: tuple[str, ...],
    **kwargs: Any,
) -> strict_gate.PipelineMarketConsistencyGate:
    """Run the exact gate and preserve primary research only for proven mismatches.

    The strict equivalent-scope loader is always attempted first.  Degraded primary
    provenance is accepted only for either the existing strict venue-scope pattern or
    the narrower case where the pinned Toss snapshot is adjusted while the linked
    legacy Kiwoom corroboration snapshot is unadjusted.  Pointer stability, content
    IDs, account/order boundaries, and exact source paths remain enforced by the
    underlying gate and the selected provenance loader.
    """

    with _DEGRADED_GATE_LOCK:
        original_loader: Any = getattr(strict_gate, _LOADER_ATTRIBUTE)

        def composed_loader(
            root: str | Path,
            *,
            market_snapshot_id: str,
            decision_symbols: tuple[str, ...],
        ) -> MarketConsistencyProvenance:
            try:
                return cast(
                    MarketConsistencyProvenance,
                    original_loader(
                        root,
                        market_snapshot_id=market_snapshot_id,
                        decision_symbols=decision_symbols,
                    ),
                )
            except (OSError, TypeError, ValueError) as strict_failure:
                try:
                    return load_primary_source_market_provenance(
                        root,
                        market_snapshot_id=market_snapshot_id,
                        decision_symbols=decision_symbols,
                    )
                except (OSError, TypeError, ValueError):
                    try:
                        return load_adjustment_basis_primary_source_provenance(
                            root,
                            market_snapshot_id=market_snapshot_id,
                            decision_symbols=decision_symbols,
                        )
                    except (OSError, TypeError, ValueError) as basis_failure:
                        raise strict_failure from basis_failure

        setattr(strict_gate, _LOADER_ATTRIBUTE, composed_loader)
        try:
            with adjusted_market_consistency_runtime():
                return strict_gate.run_pipeline_market_consistency_gate(
                    output_root=output_root,
                    market_directory=market_directory,
                    decision_symbols=decision_symbols,
                    **kwargs,
                )
        finally:
            setattr(strict_gate, _LOADER_ATTRIBUTE, original_loader)


PipelineMarketConsistencyGate = strict_gate.PipelineMarketConsistencyGate

__all__ = [
    "PipelineMarketConsistencyGate",
    "run_pipeline_market_consistency_gate",
]
