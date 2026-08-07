"""Tests for fail-closed single-broker expectation snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from alpha_cycle.intelligence.expectations import (
    ExpectationIntelligenceCollector,
    write_expectation_intelligence_snapshot,
)
from alpha_cycle.providers.kis_research import KisEstimatePerformEvidence

NOW = datetime(2026, 8, 7, 21, 0, tzinfo=ZoneInfo("Asia/Seoul"))


def _record(symbol: str, *, minute: int) -> KisEstimatePerformEvidence:
    payload = {
        "rt_cd": "0",
        "output1": {"sht_cd": symbol},
        "output2": [{"data1": "row", "data2": "1", "data3": "2", "data4": "3", "data5": "4"}],
        "output3": [{"data1": "indicator", "data2": "1", "data3": "2", "data4": "3", "data5": "4"}],
        "output4": [{"dt": "202512"}, {"dt": "202612E"}],
    }
    return KisEstimatePerformEvidence(
        symbol=symbol,
        retrieved_at=NOW + timedelta(minutes=minute),
        endpoint="/uapi/domestic-stock/v1/quotations/estimate-perform",
        tr_id="HHKST668300C0",
        source_scope="single_broker_research_estimate",
        raw_response_sha256=("a" if symbol == "000660" else "b") * 64,
        raw_payload=payload,
    )


class FakeClient:
    def estimate_perform(self, symbol: object) -> KisEstimatePerformEvidence:
        text = str(symbol)
        return _record(text, minute=1 if text == "000660" else 2)


def test_snapshot_never_certifies_consensus_or_revision(tmp_path: Path) -> None:
    snapshot = ExpectationIntelligenceCollector(FakeClient()).collect(  # type: ignore[arg-type]
        ["005930", "000660"]
    )

    assert snapshot.symbols == ("000660", "005930")
    assert snapshot.source_scope == "single_broker_research_estimate"
    payload = snapshot.payload_without_id()
    assert payload["consensus_certified"] is False
    assert payload["revision_certified"] is False
    assert payload["semantic_status"] == "raw_structure_only"
    assert len(snapshot.snapshot_id) == 64

    files = write_expectation_intelligence_snapshot(tmp_path, snapshot)
    destination = files[0].parent
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == snapshot.snapshot_id
    assert manifest["source_scope"] == "single_broker_research_estimate"
    assert manifest["consensus_certified"] is False
    assert manifest["revision_certified"] is False
    assert manifest["account_api_enabled"] is False
    assert manifest["holdings_api_enabled"] is False
    assert manifest["balance_api_enabled"] is False
    assert manifest["order_api_enabled"] is False

    structure = (destination / "structure.csv").read_text(encoding="utf-8")
    assert "202512" in structure
    assert "202612E" in structure
    raw = json.loads(
        (destination / "raw_estimate_perform.json").read_text(encoding="utf-8")
    )
    assert sorted(raw) == ["000660", "005930"]


def test_same_snapshot_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    snapshot = ExpectationIntelligenceCollector(FakeClient()).collect(  # type: ignore[arg-type]
        ["000660", "005930"]
    )

    first = write_expectation_intelligence_snapshot(tmp_path, snapshot)
    second = write_expectation_intelligence_snapshot(tmp_path, snapshot)

    assert first == second
    assert first[0].parent == second[0].parent
