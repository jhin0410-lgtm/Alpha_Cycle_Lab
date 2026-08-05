"""Integrity tests for decision evidence envelope publication."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from alpha_cycle.intelligence.decision_provenance import (
    build_decision_evidence_envelope,
    write_decision_evidence_envelope,
)
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)

DECISION_ID = "d" * 64
MARKET_ID = "b" * 64


def _decision_directory(root: Path) -> Path:
    directory = root / "decision"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": DECISION_ID,
                "market_snapshot_id": MARKET_ID,
            }
        ),
        encoding="utf-8",
    )
    return directory


def _consistency(root: Path) -> MarketConsistencyProvenance:
    return MarketConsistencyProvenance(
        assessment_id="a" * 64,
        result_id="c" * 64,
        checked_at_utc="2026-08-05T04:00:00+00:00",
        raw_status="passed",
        classification="equivalent_scope_observed",
        historical_scope_status="comparable",
        market_snapshot_id=MARKET_ID,
        kiwoom_snapshot_id="e" * 64,
        expected_symbols=("000660", "005930", "005935"),
        live_quote_status="passed",
        historical_verified=True,
        live_price_certified=True,
        decision_integration_eligible=True,
        assessment_path=str(root / "assessment.json"),
        result_path=str(root / "result.json"),
        warnings=("validated",),
    )


def test_envelope_id_excludes_machine_specific_navigation_paths(
    tmp_path: Path,
) -> None:
    captured = datetime(2026, 8, 5, 5, tzinfo=UTC)
    first_root = tmp_path / "machine-a"
    second_root = tmp_path / "machine-b"
    first = build_decision_evidence_envelope(
        _decision_directory(first_root),
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=_consistency(first_root),
        now=captured,
    )
    second = build_decision_evidence_envelope(
        _decision_directory(second_root),
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=_consistency(second_root),
        now=captured,
    )

    assert first.decision_directory != second.decision_directory
    assert first.consistency is not None
    assert second.consistency is not None
    assert first.consistency.result_path != second.consistency.result_path
    assert first.envelope_id == second.envelope_id
    assert first.identity_payload() == second.identity_payload()
    assert first.payload_without_id() != second.payload_without_id()


def test_concurrent_identical_envelope_writers_converge_on_one_artifact(
    tmp_path: Path,
) -> None:
    envelope = build_decision_evidence_envelope(
        _decision_directory(tmp_path),
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=_consistency(tmp_path),
        now=datetime(2026, 8, 5, 5, tzinfo=UTC),
    )
    output = tmp_path / "envelopes"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(write_decision_evidence_envelope, output, envelope)
            for _ in range(2)
        ]
        results = [future.result(timeout=10) for future in futures]

    assert results[0] == results[1]
    manifest_path, report_path = results[0]
    assert manifest_path.is_file()
    assert report_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["envelope_id"] == envelope.envelope_id
    assert len([item for item in output.iterdir() if item.is_dir()]) == 1
    assert not list(output.glob(".*.tmp"))


def test_naive_envelope_clock_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_decision_evidence_envelope(
            _decision_directory(tmp_path),
            decision_snapshot_id=DECISION_ID,
            market_snapshot_id=MARKET_ID,
            consistency=_consistency(tmp_path),
            now=datetime(2026, 8, 5, 5),
        )


def test_consistency_paths_can_change_without_changing_identity(tmp_path: Path) -> None:
    consistency = _consistency(tmp_path)
    relocated = replace(
        consistency,
        assessment_path=str(tmp_path / "other" / "assessment.json"),
        result_path=str(tmp_path / "other" / "result.json"),
    )
    captured = datetime(2026, 8, 5, 5, tzinfo=UTC)
    directory = _decision_directory(tmp_path / "decision-root")
    first = build_decision_evidence_envelope(
        directory,
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=consistency,
        now=captured,
    )
    second = build_decision_evidence_envelope(
        directory,
        decision_snapshot_id=DECISION_ID,
        market_snapshot_id=MARKET_ID,
        consistency=relocated,
        now=captured,
    )

    assert first.envelope_id == second.envelope_id
