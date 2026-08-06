"""Run the live research pipeline from a fresh read-only Kiwoom export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from alpha_cycle import live_pipeline_cli as live
from alpha_cycle import live_pipeline_provenance_cli as provenance_cli
from alpha_cycle import pipeline_decision_provenance as decision_runtime
from alpha_cycle.intelligence.kiwoom_primary_market import (
    build_kiwoom_primary_snapshot,
)
from alpha_cycle.intelligence.kiwoom_primary_provenance import (
    KiwoomPrimaryProvenance,
    load_kiwoom_primary_provenance,
)
from alpha_cycle.intelligence.market import MarketIntelligenceSnapshot
from alpha_cycle.pipeline_market_consistency import PipelineMarketConsistencyGate

_CLIENT_ATTRIBUTE = "TossInvestReadOnlyClient"
_COLLECTOR_ATTRIBUTE = "MarketIntelligenceCollector"
_GATE_ATTRIBUTE = "run_pipeline_market_consistency_gate"


@dataclass(frozen=True)
class _KiwoomPrimaryGate:
    provenance: KiwoomPrimaryProvenance
    raw_result_path: Path
    assessment_path: Path


class _NoTossClient:
    timeout_seconds: float = 15.0
    max_retries: int = 0

    @classmethod
    def from_env(cls) -> _NoTossClient:
        return cls()


class _KiwoomCollector:
    output_root: Path

    def __init__(self, _client: object) -> None:
        pass

    def collect(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        interval: str,
        count: int,
        adjusted: bool,
    ) -> MarketIntelligenceSnapshot:
        if interval != "1d":
            raise ValueError("Kiwoom primary fallback supports daily data only")
        expected = tuple(sorted(set(symbols)))
        if expected != tuple(sorted(live.DEFAULT_MARKET_SYMBOLS)):
            raise ValueError("Kiwoom primary fallback symbol set changed")

        # The legacy live-pipeline call currently passes its requested basis as a
        # parameter. The immutable Kiwoom manifest is the authoritative basis:
        # the adapter below fails closed unless opt10081 수정주가구분=1 and every
        # exported row is bound to adjustment evidence.
        snapshot = build_kiwoom_primary_snapshot(self.output_root, count=count)
        if not snapshot.adjusted:
            raise ValueError("Kiwoom primary fallback must publish adjusted candles")
        return snapshot


def _primary_gate(
    *,
    output_root: str | Path,
    market_directory: str | Path,
    decision_symbols: tuple[str, ...],
    **_kwargs: Any,
) -> PipelineMarketConsistencyGate:
    provenance = load_kiwoom_primary_provenance(
        market_directory,
        decision_symbols=decision_symbols,
    )
    source_path = Path(provenance.result_path).resolve(strict=True)
    gate = _KiwoomPrimaryGate(
        provenance=provenance,
        raw_result_path=source_path,
        assessment_path=source_path,
    )
    return cast(PipelineMarketConsistencyGate, gate)


def main(argv: list[str] | None = None) -> int:
    """Patch only the market source and provenance gate for one fallback execution."""

    parsed = live.build_parser().parse_args(argv)
    live._validate_args(parsed)
    _KiwoomCollector.output_root = Path(parsed.output)

    original_client: Any = getattr(live, _CLIENT_ATTRIBUTE)
    original_collector: Any = getattr(live, _COLLECTOR_ATTRIBUTE)
    original_gate: Any = getattr(decision_runtime, _GATE_ATTRIBUTE)
    setattr(live, _CLIENT_ATTRIBUTE, _NoTossClient)
    setattr(live, _COLLECTOR_ATTRIBUTE, _KiwoomCollector)
    setattr(decision_runtime, _GATE_ATTRIBUTE, _primary_gate)
    try:
        return provenance_cli.main(argv)
    finally:
        setattr(live, _CLIENT_ATTRIBUTE, original_client)
        setattr(live, _COLLECTOR_ATTRIBUTE, original_collector)
        setattr(decision_runtime, _GATE_ATTRIBUTE, original_gate)


if __name__ == "__main__":
    raise SystemExit(main())
