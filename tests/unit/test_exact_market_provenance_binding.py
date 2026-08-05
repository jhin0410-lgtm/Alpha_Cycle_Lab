"""Functional regression tests for exact market-provenance binding."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from alpha_cycle import pipeline_market_consistency as pipeline
from alpha_cycle.intelligence.market_consistency_provenance import (
    MarketConsistencyProvenance,
)
from alpha_cycle.market_consistency_cli import ConsistencyError, ConsistencyResult
from alpha_cycle.market_consistency_runner_cli import MarketScopeAssessment

RESULT_ID = "a" * 64
ASSESSMENT_ID = "b" * 64
MARKET_ID = "c" * 64


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _case(
    root: Path,
) -> tuple[
    ConsistencyResult,
    Path,
    MarketScopeAssessment,
    Path,
    MarketConsistencyProvenance,
]:
    result_path = root / "market-source-consistency" / "case" / "consistency.json"
    assessment_path = result_path.parent / "market_scope_assessment.json"
    _write_json(result_path, {"result_id": RESULT_ID})
    _write_json(assessment_path, {"assessment_id": ASSESSMENT_ID})
    raw_pointer = {
        "result_id": RESULT_ID,
        "assessment_id": ASSESSMENT_ID,
        "result_path": str(result_path.resolve()),
        "assessment_path": str(assessment_path.resolve()),
    }
    scope_pointer = {
        "assessment_id": ASSESSMENT_ID,
        "raw_result_path": str(result_path.resolve()),
        "assessment_path": str(assessment_path.resolve()),
    }
    _write_json(root / "latest_market_consistency.json", raw_pointer)
    _write_json(root / "latest_market_scope_assessment.json", scope_pointer)

    raw_result = cast(
        ConsistencyResult,
        SimpleNamespace(result_id=RESULT_ID, toss_snapshot_id=MARKET_ID),
    )
    assessment = cast(
        MarketScopeAssessment,
        SimpleNamespace(assessment_id=ASSESSMENT_ID),
    )
    provenance = cast(
        MarketConsistencyProvenance,
        SimpleNamespace(
            result_id=RESULT_ID,
            assessment_id=ASSESSMENT_ID,
            result_path=str(result_path.resolve()),
            assessment_path=str(assessment_path.resolve()),
        ),
    )
    return raw_result, result_path, assessment, assessment_path, provenance


def test_exact_loader_uses_canonical_artifact_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_result, result_path, assessment, assessment_path, provenance = _case(tmp_path)
    calls: list[Path] = []

    def fake_loader(
        root: str | Path,
        *,
        market_snapshot_id: str,
        decision_symbols: tuple[str, ...],
    ) -> MarketConsistencyProvenance:
        calls.append(Path(root))
        assert market_snapshot_id == MARKET_ID
        assert decision_symbols == ("000660", "005930")
        return provenance

    monkeypatch.setattr(pipeline, "load_market_consistency_provenance", fake_loader)
    loaded = pipeline._load_exact_provenance(
        root=tmp_path,
        raw_result=raw_result,
        raw_result_path=result_path,
        assessment=assessment,
        assessment_path=assessment_path,
        decision_symbols=("000660", "005930"),
    )

    assert loaded is provenance
    assert calls == [tmp_path]
    assert not list(tmp_path.glob("pipeline-provenance-*"))


def test_exact_loader_rejects_pointer_changes_during_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_result, result_path, assessment, assessment_path, provenance = _case(tmp_path)

    def mutating_loader(
        root: str | Path,
        *,
        market_snapshot_id: str,
        decision_symbols: tuple[str, ...],
    ) -> MarketConsistencyProvenance:
        del market_snapshot_id, decision_symbols
        pointer_path = Path(root) / "latest_market_consistency.json"
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
        payload["result_id"] = "d" * 64
        _write_json(pointer_path, payload)
        return provenance

    monkeypatch.setattr(pipeline, "load_market_consistency_provenance", mutating_loader)
    with pytest.raises(
        ConsistencyError,
        match="latest raw pointer changed while provenance was loading",
    ):
        pipeline._load_exact_provenance(
            root=tmp_path,
            raw_result=raw_result,
            raw_result_path=result_path,
            assessment=assessment,
            assessment_path=assessment_path,
            decision_symbols=("000660", "005930"),
        )
