"""Resume pipeline entry point with exact market-consistency provenance gating."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from alpha_cycle import live_pipeline_cli as live
from alpha_cycle import resume_pipeline_cli as resume
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_publication import (
    DecisionProvenancePublicationError,
)
from alpha_cycle.pipeline_decision_provenance import (
    PIPELINE_PATCH_LOCK,
    PipelineDecisionProvenanceRuntime,
)

_BUILD_ATTRIBUTE = "build_investment_decision_snapshot"
_WRITE_ATTRIBUTE = "write_investment_decision_snapshot"
_EXECUTE_ATTRIBUTE = "_execute"
_FIND_MARKET_ATTRIBUTE = "_find_market_directory"
_TOSS_PROVIDER = "tossinvest-readonly"
MarketFinder = Callable[
    [Path, str],
    tuple[Path, Mapping[str, object]] | None,
]


def _find_toss_resume_market(
    original: MarketFinder,
    root: Path,
    snapshot_id: str,
) -> tuple[Path, Mapping[str, object]] | None:
    """Keep the generic resume path bound to Toss-origin market snapshots.

    Kiwoom-primary snapshots are intentionally resumed only through their dedicated
    fresh-export pipeline, which installs a different provenance gate. Returning
    ``None`` here lets the normal resume search continue to older linked research
    snapshots rather than sending Kiwoom evidence into the Toss consistency gate.
    """

    found = original(root, snapshot_id)
    if found is None:
        return None
    market_directory, manifest = found
    if str(manifest.get("provider", "")) != _TOSS_PROVIDER:
        return None
    return market_directory, manifest


def main(argv: list[str] | None = None) -> int:
    """Run resume valuation/decision only after exact snapshot corroboration."""

    with PIPELINE_PATCH_LOCK:
        runtime = PipelineDecisionProvenanceRuntime(live.DEFAULT_DECISION_SYMBOLS)
        original_build: Any = getattr(resume, _BUILD_ATTRIBUTE)
        original_write: Any = getattr(resume, _WRITE_ATTRIBUTE)
        original_execute: Any = getattr(resume, _EXECUTE_ATTRIBUTE)
        original_find_market: Any = getattr(resume, _FIND_MARKET_ATTRIBUTE)

        def provider_bound_find_market(
            root: Path,
            snapshot_id: str,
        ) -> tuple[Path, Mapping[str, object]] | None:
            return _find_toss_resume_market(
                cast(MarketFinder, original_find_market),
                root,
                snapshot_id,
            )

        def gated_build(
            research_snapshot: str | Path,
            market_snapshot: str | Path,
            *args: Any,
            **kwargs: Any,
        ) -> InvestmentDecisionSnapshot:
            try:
                runtime.prepare(market_snapshot)
            except (OSError, TypeError, ValueError) as exc:
                raise live.PipelineStageError("market_consistency", exc) from exc
            return cast(
                InvestmentDecisionSnapshot,
                original_build(
                    research_snapshot,
                    market_snapshot,
                    *args,
                    **kwargs,
                ),
            )

        def gated_write(
            output_root: str | Path,
            snapshot: InvestmentDecisionSnapshot,
        ) -> tuple[Path, ...]:
            try:
                return runtime.write(original_write, output_root, snapshot)
            except DecisionProvenancePublicationError as exc:
                raise live.PipelineStageError("decision_provenance", exc) from exc

        def gated_execute(args: argparse.Namespace) -> dict[str, object]:
            runtime.reset()
            payload = cast(dict[str, object], original_execute(args))
            try:
                payload.update(runtime.status_payload())
            except (OSError, TypeError, ValueError) as exc:
                raise live.PipelineStageError("decision_provenance", exc) from exc
            return payload

        setattr(resume, _FIND_MARKET_ATTRIBUTE, provider_bound_find_market)
        setattr(resume, _BUILD_ATTRIBUTE, gated_build)
        setattr(resume, _WRITE_ATTRIBUTE, gated_write)
        setattr(resume, _EXECUTE_ATTRIBUTE, gated_execute)
        try:
            return resume.main(argv)
        finally:
            setattr(resume, _FIND_MARKET_ATTRIBUTE, original_find_market)
            setattr(resume, _BUILD_ATTRIBUTE, original_build)
            setattr(resume, _WRITE_ATTRIBUTE, original_write)
            setattr(resume, _EXECUTE_ATTRIBUTE, original_execute)


if __name__ == "__main__":
    raise SystemExit(main())
