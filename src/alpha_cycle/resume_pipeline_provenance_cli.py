"""Resume pipeline entry point with exact market-consistency provenance gating."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast

from alpha_cycle import live_pipeline_cli as live
from alpha_cycle import resume_pipeline_cli as resume
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.pipeline_decision_provenance import (
    PipelineDecisionProvenanceRuntime,
)

_BUILD_ATTRIBUTE = "build_investment_decision_snapshot"
_WRITE_ATTRIBUTE = "write_investment_decision_snapshot"
_EXECUTE_ATTRIBUTE = "_execute"


def main(argv: list[str] | None = None) -> int:
    """Run resume valuation/decision only after exact snapshot corroboration."""

    runtime = PipelineDecisionProvenanceRuntime(live.DEFAULT_DECISION_SYMBOLS)
    original_build: Any = getattr(resume, _BUILD_ATTRIBUTE)
    original_write: Any = getattr(resume, _WRITE_ATTRIBUTE)
    original_execute: Any = getattr(resume, _EXECUTE_ATTRIBUTE)

    def gated_build(
        research_snapshot: str | Path,
        market_snapshot: str | Path,
        *args: Any,
        **kwargs: Any,
    ) -> InvestmentDecisionSnapshot:
        try:
            return runtime.build(
                original_build,
                research_snapshot,
                market_snapshot,
                *args,
                **kwargs,
            )
        except (OSError, TypeError, ValueError) as exc:
            raise live.PipelineStageError("market_consistency", exc) from exc

    def gated_write(
        output_root: str | Path,
        snapshot: InvestmentDecisionSnapshot,
    ) -> tuple[Path, ...]:
        try:
            return runtime.write(original_write, output_root, snapshot)
        except (OSError, TypeError, ValueError) as exc:
            raise live.PipelineStageError("decision_provenance", exc) from exc

    def gated_execute(args: argparse.Namespace) -> dict[str, object]:
        runtime.reset()
        payload = cast(dict[str, object], original_execute(args))
        try:
            payload.update(runtime.status_payload())
        except (OSError, TypeError, ValueError) as exc:
            raise live.PipelineStageError("decision_provenance", exc) from exc
        return payload

    setattr(resume, _BUILD_ATTRIBUTE, gated_build)
    setattr(resume, _WRITE_ATTRIBUTE, gated_write)
    setattr(resume, _EXECUTE_ATTRIBUTE, gated_execute)
    try:
        return resume.main(argv)
    finally:
        setattr(resume, _BUILD_ATTRIBUTE, original_build)
        setattr(resume, _WRITE_ATTRIBUTE, original_write)
        setattr(resume, _EXECUTE_ATTRIBUTE, original_execute)


if __name__ == "__main__":
    raise SystemExit(main())
