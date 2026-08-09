"""Immutable KIS estimate-perform evidence without premature consensus semantics."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.providers.kis_research import (
    KIS_RESEARCH_SOURCE_SCOPE,
    KisEstimatePerformEvidence,
    KisResearchReadOnlyClient,
)

EXPECTATION_SNAPSHOT_SCHEMA_VERSION = 1


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _periods(record: KisEstimatePerformEvidence) -> list[str]:
    output4 = record.raw_payload.get("output4")
    if not isinstance(output4, list):
        return []
    periods: list[str] = []
    for row in output4:
        if not isinstance(row, dict):
            continue
        value = str(row.get("dt", "")).strip()
        if value:
            periods.append(value)
    return periods


def _output_row_count(payload: object, name: str) -> int:
    if not isinstance(payload, dict):
        raise ValueError("Expectation payload must be an object")
    value = payload.get(name)
    if not isinstance(value, list):
        raise ValueError(f"Expectation {name} must be an array")
    return len(value)


@dataclass(frozen=True)
class ExpectationIntelligenceSnapshot:
    captured_at: datetime
    provider: str
    source_scope: str
    records: tuple[KisEstimatePerformEvidence, ...]

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        if self.provider != "korea_investment_openapi":
            raise ValueError("Unexpected expectation provider")
        if self.source_scope != KIS_RESEARCH_SOURCE_SCOPE:
            raise ValueError("Unexpected expectation source scope")
        symbols = tuple(item.symbol for item in self.records)
        if not symbols:
            raise ValueError("Expectation snapshot requires at least one record")
        if symbols != tuple(sorted(set(symbols))):
            raise ValueError("Expectation records must be unique and sorted by symbol")

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(item.symbol for item in self.records)

    def payload_without_id(self) -> dict[str, object]:
        return {
            "schema_version": EXPECTATION_SNAPSHOT_SCHEMA_VERSION,
            "captured_at": self.captured_at.isoformat(),
            "provider": self.provider,
            "source_scope": self.source_scope,
            "consensus_certified": False,
            "revision_certified": False,
            "semantic_status": "raw_structure_only",
            "records": [record.as_dict() for record in self.records],
        }

    @property
    def snapshot_id(self) -> str:
        encoded = _canonical_json(self.payload_without_id()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ExpectationIntelligenceCollector:
    """Collect KIS estimate-perform evidence while keeping semantics unresolved."""

    def __init__(self, client: KisResearchReadOnlyClient) -> None:
        self.client = client

    def collect(
        self,
        symbols: list[str] | tuple[str, ...],
    ) -> ExpectationIntelligenceSnapshot:
        normalized = tuple(
            sorted(
                set(
                    str(value).strip()
                    for value in symbols
                    if str(value).strip()
                )
            )
        )
        if not normalized:
            raise ValueError("At least one expectation symbol is required")
        records = tuple(
            sorted(
                (self.client.estimate_perform(symbol) for symbol in normalized),
                key=lambda item: item.symbol,
            )
        )
        captured_at = max(record.retrieved_at for record in records)
        return ExpectationIntelligenceSnapshot(
            captured_at=captured_at,
            provider="korea_investment_openapi",
            source_scope=KIS_RESEARCH_SOURCE_SCOPE,
            records=records,
        )


def _structure_rows(snapshot: ExpectationIntelligenceSnapshot) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in snapshot.records:
        payload = record.raw_payload
        output1 = payload.get("output1")
        rows.append(
            {
                "symbol": record.symbol,
                "retrieved_at": record.retrieved_at.isoformat(),
                "source_scope": record.source_scope,
                "output1_shape": "array" if isinstance(output1, list) else "object",
                "output1_rows": len(output1) if isinstance(output1, list) else 1,
                "output2_rows": _output_row_count(payload, "output2"),
                "output3_rows": _output_row_count(payload, "output3"),
                "output4_rows": _output_row_count(payload, "output4"),
                "periods": json.dumps(_periods(record), ensure_ascii=False),
                "raw_response_sha256": record.raw_response_sha256,
                "semantic_status": "raw_structure_only",
                "consensus_certified": False,
                "revision_certified": False,
            }
        )
    return rows


def write_expectation_intelligence_snapshot(
    output_root: str | Path,
    snapshot: ExpectationIntelligenceSnapshot,
) -> tuple[Path, ...]:
    """Atomically persist a content-addressed expectation evidence snapshot."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    timestamp = snapshot.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory_name = f"{timestamp}__{snapshot.snapshot_id[:12]}"
    destination = root / directory_name
    expected_names = (
        "manifest.json",
        "structure.csv",
        "records.json",
        "raw_estimate_perform.json",
    )
    if destination.exists():
        manifest_path = destination / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Existing expectation snapshot directory is incomplete")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("snapshot_id") != snapshot.snapshot_id:
            raise ValueError("Existing expectation snapshot conflicts with requested snapshot")
        return tuple(destination / name for name in expected_names)

    temporary = root / f".{directory_name}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=False)
    try:
        rows = _structure_rows(snapshot)
        with (temporary / "structure.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        (temporary / "records.json").write_text(
            json.dumps(
                [record.as_dict() for record in snapshot.records],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (temporary / "raw_estimate_perform.json").write_text(
            json.dumps(
                {
                    record.symbol: dict(record.raw_payload)
                    for record in snapshot.records
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        manifest = {
            "schema_version": EXPECTATION_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "captured_at": snapshot.captured_at.isoformat(),
            "provider": snapshot.provider,
            "source_scope": snapshot.source_scope,
            "symbols": list(snapshot.symbols),
            "semantic_status": "raw_structure_only",
            "consensus_certified": False,
            "revision_certified": False,
            "account_api_enabled": False,
            "holdings_api_enabled": False,
            "balance_api_enabled": False,
            "order_api_enabled": False,
            "files": list(expected_names[1:]),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.rename(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return tuple(destination / name for name in expected_names)


__all__ = [
    "EXPECTATION_SNAPSHOT_SCHEMA_VERSION",
    "ExpectationIntelligenceCollector",
    "ExpectationIntelligenceSnapshot",
    "write_expectation_intelligence_snapshot",
]
