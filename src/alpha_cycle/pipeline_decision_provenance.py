"""Shared runtime state for gated live and resumed investment decisions."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_provenance import DecisionEvidenceEnvelope
from alpha_cycle.intelligence.decision_publication import (
    publish_decision_with_evidence,
)
from alpha_cycle.intelligence.kiwoom_primary_market import PRIMARY_PROVIDER
from alpha_cycle.intelligence.kiwoom_primary_provenance import (
    run_kiwoom_primary_market_gate,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)
from alpha_cycle.pipeline_market_consistency_degraded import (
    run_pipeline_market_consistency_gate,
)

DecisionBuilder = Callable[..., InvestmentDecisionSnapshot]
DecisionWriter = Callable[
    [str | Path, InvestmentDecisionSnapshot],
    tuple[Path, ...],
]
PIPELINE_PATCH_LOCK = threading.Lock()


class PipelineMarketEvidenceGate(Protocol):
    raw_result_path: Path
    assessment_path: Path
    provenance: MarketConsistencyProvenance


def _market_provider(directory: Path) -> str | None:
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        payload: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return str(cast(dict[str, object], payload).get("provider", "")).strip() or None


@dataclass
class PipelineDecisionProvenanceRuntime:
    """Hold exact gate and envelope evidence during one CLI execution."""

    decision_symbols: tuple[str, ...]
    gate: PipelineMarketEvidenceGate | None = None
    envelope: DecisionEvidenceEnvelope | None = None
    envelope_files: tuple[Path, Path] | None = None

    def reset(self) -> None:
        self.gate = None
        self.envelope = None
        self.envelope_files = None

    def prepare(self, market_snapshot: str | Path) -> None:
        """Run the provider-specific exact-snapshot provenance gate."""

        market_directory = Path(market_snapshot).resolve(strict=True)
        if len(market_directory.parents) < 2:
            raise ValueError(
                f"Cannot derive pipeline output root from market snapshot: {market_directory}"
            )
        output_root = market_directory.parents[1]
        if _market_provider(market_directory) == PRIMARY_PROVIDER:
            self.gate = run_kiwoom_primary_market_gate(
                output_root=output_root,
                market_directory=market_directory,
                decision_symbols=self.decision_symbols,
            )
        else:
            self.gate = run_pipeline_market_consistency_gate(
                output_root=output_root,
                market_directory=market_directory,
                decision_symbols=self.decision_symbols,
            )

    def build(
        self,
        original: DecisionBuilder,
        research_snapshot: str | Path,
        market_snapshot: str | Path,
        *args: Any,
        **kwargs: Any,
    ) -> InvestmentDecisionSnapshot:
        """Prepare market provenance and then call an unwrapped decision builder."""

        self.prepare(market_snapshot)
        return original(
            research_snapshot,
            market_snapshot,
            *args,
            **kwargs,
        )

    def write(
        self,
        original: DecisionWriter,
        output_root: str | Path,
        snapshot: InvestmentDecisionSnapshot,
    ) -> tuple[Path, ...]:
        """Stage the envelope and expose the decision directory only after success."""

        if self.gate is None:
            raise ValueError("Market consistency gate did not run before decision write")
        publication = publish_decision_with_evidence(
            decision_output_root=output_root,
            provenance_output_root=Path(output_root).parent / "decision-provenance",
            snapshot=snapshot,
            consistency=self.gate.provenance,
            decision_writer=original,
        )
        self.envelope = publication.envelope
        self.envelope_files = publication.envelope_files
        return publication.decision_files

    def status_payload(self) -> dict[str, object]:
        """Return fields added to the existing live/resume status payload."""

        if self.gate is None or self.envelope is None or self.envelope_files is None:
            raise ValueError("Decision provenance runtime did not complete")
        provenance = self.gate.provenance
        return {
            "market_consistency_result_id": provenance.result_id,
            "market_consistency_assessment_id": provenance.assessment_id,
            "market_consistency_raw_status": provenance.raw_status,
            "market_consistency_classification": provenance.classification,
            "market_consistency_result_path": str(
                self.gate.raw_result_path.resolve()
            ),
            "market_consistency_assessment_path": str(
                self.gate.assessment_path.resolve()
            ),
            "market_provenance_status": provenance.mode,
            "historical_market_evidence_verified": provenance.historical_verified,
            "reference_price_cross_provider_certified": (
                provenance.live_price_certified
            ),
            "decision_evidence_envelope_id": self.envelope.envelope_id,
            "decision_evidence_envelope_path": str(
                self.envelope_files[0].parent.resolve()
            ),
            "market_consistency_warnings": list(provenance.warnings),
            "automatic_provider_substitution_enabled": False,
            "account_api_enabled": False,
            "order_api_enabled": False,
        }


__all__ = [
    "PIPELINE_PATCH_LOCK",
    "PipelineDecisionProvenanceRuntime",
    "PipelineMarketEvidenceGate",
]
