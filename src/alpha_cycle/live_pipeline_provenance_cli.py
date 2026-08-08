"""Live pipeline entry point with exact market-consistency provenance gating."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from alpha_cycle import live_pipeline_cli as live
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
_STATUS_ATTRIBUTE = "_write_status"
_GATED_RERUN_COMMAND = "python -m alpha_cycle.live_pipeline_provenance_cli"


def _rewrite_status_ascii_safe(
    destination: Path,
    payload: Mapping[str, object],
) -> Path:
    """Keep the latest-run pointer safe for Windows PowerShell 5.1 default decoding."""

    temporary = destination.with_name(f".{destination.name}.ascii.tmp")
    temporary.write_text(
        json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True),
        encoding="ascii",
    )
    temporary.replace(destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    """Run the existing live pipeline with a fail-closed pre-decision gate."""

    with PIPELINE_PATCH_LOCK:
        runtime = PipelineDecisionProvenanceRuntime(live.DEFAULT_DECISION_SYMBOLS)
        original_build: Any = getattr(live, _BUILD_ATTRIBUTE)
        original_write: Any = getattr(live, _WRITE_ATTRIBUTE)
        original_execute: Any = getattr(live, _EXECUTE_ATTRIBUTE)
        original_status_writer: Any = getattr(live, _STATUS_ATTRIBUTE)

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

        def gated_status_writer(
            output_root: Path,
            payload: Mapping[str, object],
        ) -> Path:
            mutable_payload: Mapping[str, object] = payload
            if isinstance(payload, dict):
                payload["provenance_gate_enabled"] = True
                if "rerun_command" in payload:
                    payload["rerun_command"] = _GATED_RERUN_COMMAND
                mutable_payload = payload
            destination = cast(Path, original_status_writer(output_root, mutable_payload))
            return _rewrite_status_ascii_safe(destination, mutable_payload)

        setattr(live, _BUILD_ATTRIBUTE, gated_build)
        setattr(live, _WRITE_ATTRIBUTE, gated_write)
        setattr(live, _EXECUTE_ATTRIBUTE, gated_execute)
        setattr(live, _STATUS_ATTRIBUTE, gated_status_writer)
        try:
            return live.main(argv)
        finally:
            setattr(live, _BUILD_ATTRIBUTE, original_build)
            setattr(live, _WRITE_ATTRIBUTE, original_write)
            setattr(live, _EXECUTE_ATTRIBUTE, original_execute)
            setattr(live, _STATUS_ATTRIBUTE, original_status_writer)


if __name__ == "__main__":
    raise SystemExit(main())
