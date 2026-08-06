"""Live pipeline entry point with exact market-consistency provenance gating."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from alpha_cycle import live_pipeline_cli as live
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.intelligence.decision_publication import (
    DecisionProvenancePublicationError,
)
from alpha_cycle.intelligence.kiwoom_primary_market_loader import (
    existing_kiwoom_primary_files,
    load_kiwoom_primary_snapshot,
)
from alpha_cycle.intelligence.market import MarketIntelligenceSnapshot
from alpha_cycle.pipeline_decision_provenance import (
    PIPELINE_PATCH_LOCK,
    PipelineDecisionProvenanceRuntime,
)

_BUILD_ATTRIBUTE = "build_investment_decision_snapshot"
_WRITE_ATTRIBUTE = "write_investment_decision_snapshot"
_EXECUTE_ATTRIBUTE = "_execute"
_STATUS_ATTRIBUTE = "_write_status"
_TOSS_ATTRIBUTE = "TossInvestReadOnlyClient"
_COLLECTOR_ATTRIBUTE = "MarketIntelligenceCollector"
_MARKET_WRITER_ATTRIBUTE = "write_market_intelligence_snapshot"
_GATED_RERUN_COMMAND = "python -m alpha_cycle.live_pipeline_provenance_cli"
_PRIMARY_MARKET_ENV = "ALPHA_CYCLE_PRIMARY_MARKET_SNAPSHOT"
_PRIMARY_REASON_ENV = "ALPHA_CYCLE_PRIMARY_MARKET_REASON"


class _PinnedMarketClient:
    timeout_seconds: float = 15.0
    max_retries: int = 0


class _PinnedTossBoundary:
    @classmethod
    def from_env(cls) -> _PinnedMarketClient:
        return _PinnedMarketClient()


class _PinnedMarketCollector:
    def __init__(self, _client: object, *, snapshot: MarketIntelligenceSnapshot) -> None:
        self.snapshot = snapshot

    def collect(
        self,
        symbols: list[str] | tuple[str, ...],
        *,
        interval: str,
        count: int,
        adjusted: bool,
    ) -> MarketIntelligenceSnapshot:
        normalized = tuple(sorted(set(symbols)))
        if normalized != self.snapshot.symbols:
            raise ValueError("Pinned Kiwoom snapshot does not match the requested symbols")
        if interval != self.snapshot.interval or adjusted != self.snapshot.adjusted:
            raise ValueError("Pinned Kiwoom snapshot contract does not match the request")
        candle_counts = {
            symbol: sum(item.symbol == symbol for item in self.snapshot.candles)
            for symbol in self.snapshot.symbols
        }
        if any(value < count for value in candle_counts.values()):
            raise ValueError("Pinned Kiwoom snapshot has insufficient candle history")
        return self.snapshot


def _primary_market_path() -> Path | None:
    value = os.environ.get(_PRIMARY_MARKET_ENV, "").strip()
    return None if not value else Path(value).resolve(strict=True)


def main(argv: list[str] | None = None) -> int:
    """Run the existing live pipeline with a fail-closed pre-decision gate."""

    with PIPELINE_PATCH_LOCK:
        runtime = PipelineDecisionProvenanceRuntime(live.DEFAULT_DECISION_SYMBOLS)
        original_build: Any = getattr(live, _BUILD_ATTRIBUTE)
        original_write: Any = getattr(live, _WRITE_ATTRIBUTE)
        original_execute: Any = getattr(live, _EXECUTE_ATTRIBUTE)
        original_status_writer: Any = getattr(live, _STATUS_ATTRIBUTE)
        original_toss: Any = getattr(live, _TOSS_ATTRIBUTE)
        original_collector: Any = getattr(live, _COLLECTOR_ATTRIBUTE)
        original_market_writer: Any = getattr(live, _MARKET_WRITER_ATTRIBUTE)

        primary_directory = _primary_market_path()
        primary_snapshot: MarketIntelligenceSnapshot | None = None
        primary_files: tuple[Path, ...] | None = None
        primary_reason = os.environ.get(_PRIMARY_REASON_ENV, "").strip()
        if primary_directory is not None:
            if primary_reason != "tossinvest_ip_allowlist":
                raise ValueError("Unsupported primary market override reason")
            primary_snapshot = load_kiwoom_primary_snapshot(primary_directory)
            primary_files = existing_kiwoom_primary_files(primary_directory)

            class BoundPinnedCollector(_PinnedMarketCollector):
                def __init__(self, client: object) -> None:
                    assert primary_snapshot is not None
                    super().__init__(client, snapshot=primary_snapshot)

            def pinned_market_writer(
                output_root: str | Path,
                snapshot: MarketIntelligenceSnapshot,
            ) -> tuple[Path, ...]:
                assert primary_directory is not None
                assert primary_files is not None
                if snapshot.snapshot_id != primary_snapshot.snapshot_id:
                    raise ValueError("Pinned market snapshot changed before publication")
                expected_root = primary_directory.parent.resolve()
                if Path(output_root).resolve() != expected_root:
                    raise ValueError("Pinned market snapshot belongs to a different output root")
                return primary_files

            setattr(live, _TOSS_ATTRIBUTE, _PinnedTossBoundary)
            setattr(live, _COLLECTOR_ATTRIBUTE, BoundPinnedCollector)
            setattr(live, _MARKET_WRITER_ATTRIBUTE, pinned_market_writer)

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
            if primary_directory is not None:
                payload.update(
                    {
                        "market_provider": "kiwoom_openapi_plus_readonly_primary",
                        "market_provider_failover_reason": primary_reason,
                        "read_only_market_failover_used": True,
                        "cross_provider_price_certified": False,
                        "automatic_provider_substitution_enabled": False,
                        "account_api_enabled": False,
                        "order_api_enabled": False,
                    }
                )
            return payload

        def gated_status_writer(
            output_root: Path,
            payload: Mapping[str, object],
        ) -> Path:
            if isinstance(payload, dict):
                payload["provenance_gate_enabled"] = True
                if primary_directory is not None:
                    payload["market_provider"] = (
                        "kiwoom_openapi_plus_readonly_primary"
                    )
                    payload["market_provider_failover_reason"] = primary_reason
                    payload["read_only_market_failover_used"] = True
                    payload["cross_provider_price_certified"] = False
                    payload["automatic_provider_substitution_enabled"] = False
                    payload["account_api_enabled"] = False
                    payload["order_api_enabled"] = False
                if "rerun_command" in payload:
                    payload["rerun_command"] = _GATED_RERUN_COMMAND
            return cast(Path, original_status_writer(output_root, payload))

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
            setattr(live, _TOSS_ATTRIBUTE, original_toss)
            setattr(live, _COLLECTOR_ATTRIBUTE, original_collector)
            setattr(live, _MARKET_WRITER_ATTRIBUTE, original_market_writer)


if __name__ == "__main__":
    raise SystemExit(main())
