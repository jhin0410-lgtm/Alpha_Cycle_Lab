"""Compose the exact market gate with a strictly validated degraded mode."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from alpha_cycle import pipeline_market_consistency as strict_gate
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
    """Run the exact gate and preserve research for one strict scope mismatch.

    The existing strict loader remains the first path. A degraded provenance object is
    considered only when the stored assessment proves the complete venue-scope pattern.
    The exact gate still performs its own pointer-stability, result-ID, assessment-ID,
    and path checks around whichever provenance object is returned.
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
                return original_loader(
                    root,
                    market_snapshot_id=market_snapshot_id,
                    decision_symbols=decision_symbols,
                )
            except (OSError, TypeError, ValueError) as strict_failure:
                try:
                    return load_primary_source_market_provenance(
                        root,
                        market_snapshot_id=market_snapshot_id,
                        decision_symbols=decision_symbols,
                    )
                except (OSError, TypeError, ValueError) as degraded_failure:
                    raise strict_failure from degraded_failure

        setattr(strict_gate, _LOADER_ATTRIBUTE, composed_loader)
        try:
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
