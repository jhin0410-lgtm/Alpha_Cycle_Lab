"""One-command persisted-source bridge into the Decision System v2.1 lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundMode,
    ResearchRoundStatus,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.live_typed_source_manifest_v2_1 import (
    freeze_live_typed_source_manifest,
    load_live_typed_source_manifest,
    persist_live_typed_source_manifest,
)
from alpha_cycle.live_typed_thesis_bridge_v2_1 import produce_source_backed_theses
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_package_assembler_v2_1 import assemble_and_run_research_package
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request
from alpha_cycle.research_request_preflight_v2_1 import preflight_pending_request_theses

_RESULT_DIRECTORY = "live_typed_research_round_v2_1"


@dataclass(frozen=True)
class LiveTypedResearchRoundReceipt:
    payload_data: dict[str, object]
    result_path: Path

    def payload(self) -> dict[str, object]:
        return {**self.payload_data, "result_path": str(self.result_path)}


def run_live_typed_research_round(
    *,
    artifact_root: str | Path,
    mode: ResearchRoundMode,
    request_id: str,
    run_id: str,
    round_id: str,
    processed_at: datetime,
    security_ids: tuple[str, ...],
    horizon_trading_days: int,
    requested_lane: UnderwritingLane,
    request_text: str,
    manifest_path: str | Path | None = None,
    market_source_directory: str | Path | None = None,
    research_source_directory: str | Path | None = None,
    evaluation_date: date | None = None,
    research_cutoff_at: datetime | None = None,
) -> LiveTypedResearchRoundReceipt:
    """Run the bridge without collecting data or invoking any network provider."""

    _require_aware(processed_at, "processed_at")
    root = Path(artifact_root)
    if mode is ResearchRoundMode.REPLAY:
        if manifest_path is None:
            raise ValueError("REPLAY requires manifest_path")
        if any(item is not None for item in (market_source_directory, research_source_directory)):
            raise ValueError("REPLAY cannot select mutable source directories")
        manifest = load_live_typed_source_manifest(manifest_path)
    else:
        if manifest_path is not None:
            raise ValueError("PROSPECTIVE freezes source directories, not a prior manifest")
        if market_source_directory is None or research_source_directory is None:
            raise ValueError("PROSPECTIVE requires market and research source directories")
        if evaluation_date is None or research_cutoff_at is None:
            raise ValueError("PROSPECTIVE requires evaluation_date and research_cutoff_at")
        manifest = freeze_live_typed_source_manifest(
            artifact_root=root,
            source_directories={
                "market": market_source_directory,
                "research": research_source_directory,
            },
            evaluation_date=evaluation_date,
            research_cutoff_at=research_cutoff_at,
            frozen_at=research_cutoff_at,
        )
    if processed_at <= manifest.research_cutoff_at + timedelta(microseconds=2):
        raise ValueError(
            "processed_at must follow the research cutoff by more than two microseconds"
        )
    persisted_manifest = persist_live_typed_source_manifest(manifest, artifact_root=root)

    thesis_receipt = produce_source_backed_theses(
        manifest,
        artifact_root=root,
        security_ids=security_ids,
        horizon_trading_days=horizon_trading_days,
        captured_at=manifest.research_cutoff_at,
    )
    recorded_at = processed_at - timedelta(microseconds=2)
    preflight_at = processed_at - timedelta(microseconds=1)
    request_receipt = record_analysis_request(
        request_id=request_id,
        requested_at=manifest.frozen_at,
        recorded_at=recorded_at,
        evaluation_date=manifest.evaluation_date,
        horizon_trading_days=horizon_trading_days,
        security_ids=security_ids,
        mode=mode,
        requested_lane=requested_lane,
        request_text=request_text,
        artifact_root=root,
        tags=("live_typed_research_round_v2_1", f"source_manifest:{manifest.manifest_id}"),
    )
    preflight = preflight_pending_request_theses(
        request_id=request_id,
        run_id=f"{run_id}:preflight",
        processed_at=preflight_at,
        artifact_root=root,
        research_cutoff_at=manifest.research_cutoff_at,
    )
    assembly = None
    if preflight.ready_for_package_assembly:
        assembly = assemble_and_run_research_package(
            request_id=request_id,
            round_id=round_id,
            run_id=run_id,
            processed_at=processed_at,
            artifact_root=root,
        )
    observatory = load_latest_observatory_state(root)
    round_status = (
        assembly.orchestrated.snapshot.status
        if assembly is not None and assembly.orchestrated is not None
        else None
    )
    ready_statuses = {
        ResearchRoundStatus.PROSPECTIVE_READY_FOR_REGISTRATION,
        ResearchRoundStatus.PROSPECTIVE_REGISTERED,
        ResearchRoundStatus.REPLAY_READY,
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "mode": mode.value,
        "request_id": request_id,
        "request_snapshot_id": request_receipt.request.snapshot_id,
        "source_manifest_id": manifest.manifest_id,
        "source_manifest_path": str(persisted_manifest),
        "thesis": thesis_receipt.payload(),
        "preflight": preflight.payload(),
        "assembly": assembly.payload() if assembly is not None else None,
        "research_round_status": round_status.value if round_status is not None else None,
        "observatory_ledger_snapshot_id": observatory.snapshot_id if observatory else None,
        "ready": round_status in ready_statuses,
        "network_collection_enabled": False,
        "provider_authority_certified": False,
        "valuation_authority_certified": False,
        "target_price_enabled": False,
        "optimal_position_size_enabled": False,
        "automatic_execution_enabled": False,
    }
    result_path = _persist_result(root, payload)
    return LiveTypedResearchRoundReceipt(payload, result_path)


def _persist_result(root: Path, payload: dict[str, object]) -> Path:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    result_id = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    directory = root / _RESULT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result_id}.json"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded + "\n":
            raise ValueError("existing live typed result conflicts with content identity")
        return path
    fd, name = tempfile.mkstemp(prefix=f".{result_id}.", suffix=".tmp", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


__all__ = ["LiveTypedResearchRoundReceipt", "run_live_typed_research_round"]
