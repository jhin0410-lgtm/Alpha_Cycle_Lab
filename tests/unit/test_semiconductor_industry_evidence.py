from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.semiconductor_cycle_proxy import SemiconductorCycleProxy
from alpha_cycle.intelligence.semiconductor_industry_evidence import (
    append_semiconductor_industry_evidence_report,
    attach_semiconductor_industry_to_records,
    attach_semiconductor_industry_to_scorecards,
    build_semiconductor_cycle_bridge,
    load_semiconductor_industry_evidence,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_artifact(
    tmp_path: Path,
    *,
    phase: str = "expansion_inventory_controlled",
    diagnostics_schema_version: int = 1,
) -> Path:
    directory = tmp_path / "artifact"
    directory.mkdir()
    latest = {
        "period": "202606",
        "heuristic_phase": phase,
        "production_yoy_pct": 2.247752,
        "shipment_yoy_pct": 3.113208,
        "inventory_yoy_pct": 3.016241,
        "capacity_yoy_pct": 8.654906,
        "utilization_yoy_pct": -6.953339,
        "production_mom_sa_pct": 4.495614,
        "shipment_mom_sa_pct": 11.652174,
        "inventory_mom_sa_pct": 2.806653,
        "utilization_mom_sa_pct": 2.714441,
        "shipment_minus_inventory_yoy_pp": 0.096966,
        "production_minus_shipment_yoy_pp": -0.865455,
        "inventory_vs_shipment_index_ratio": 40.622141,
    }
    diagnostics = {
        "schema_version": diagnostics_schema_version,
        "status": "heuristic_diagnostics_available",
        "latest": latest,
        "monthly": [latest],
        "heuristic_phase_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }
    diagnostics_hash = hashlib.sha256(_canonical_bytes(diagnostics)).hexdigest()
    manifest_without_id = {
        "schema_version": 1,
        "source": "kosis_openapi",
        "source_scope": "korean_semiconductor_cycle_history",
        "captured_at": datetime(2026, 8, 9, 12, 49, tzinfo=UTC).isoformat(),
        "requested_months": 180,
        "org_id": "101",
        "binding_verification": {},
        "series": [{"metric": f"metric_{index}"} for index in range(9)],
        "normalized_sha256": "0" * 64,
        "diagnostics_sha256": diagnostics_hash,
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "heuristic_phase_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
        "status": "semiconductor_history_captured",
    }
    artifact_id = hashlib.sha256(_canonical_bytes(manifest_without_id)).hexdigest()
    manifest = {**manifest_without_id, "artifact_id": artifact_id}
    diagnostics_path = directory / "diagnostics.json"
    manifest_path = directory / "manifest.json"
    diagnostics_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    pointer = {
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "diagnostics_path": str(diagnostics_path.resolve()),
        "status": "semiconductor_history_captured",
        "diagnostics_status": "heuristic_diagnostics_available",
        "latest_period": "202606",
        "requested_months": 180,
        "series_count": 9,
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "heuristic_phase_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer, ensure_ascii=True), encoding="utf-8")
    return pointer_path


def _proxy(state: str = "issuer_expansion_market_confirmed") -> SemiconductorCycleProxy:
    return SemiconductorCycleProxy(
        source_scope="issuer_observed_semiconductor_cycle_proxy",
        proxy_version=1,
        industry_cycle_certified=False,
        expected_tickers=("005930", "000660"),
        observed_tickers=("005930", "000660"),
        coverage_status="complete_issuer_proxy",
        cycle_proxy_state=state,
        issuer_rows=(),
        aggregate={},
    )


def test_loads_current_non_scoring_kosis_evidence(tmp_path: Path) -> None:
    pointer = _write_artifact(tmp_path)

    evidence = load_semiconductor_industry_evidence(
        pointer,
        evaluation_date=date(2026, 8, 9),
    )

    assert evidence.latest_period == "202606"
    assert evidence.period_age_months == 2
    assert evidence.heuristic_phase == "expansion_inventory_controlled"
    assert evidence.metrics["capacity_yoy_pct"] == pytest.approx(8.654906)
    assert evidence.point_in_time_backtest_eligible is False
    assert evidence.industry_cycle_certified is False
    assert evidence.decision_score_enabled is False


def test_loads_schema_v2_balanced_phase_as_non_scoring_expansion(tmp_path: Path) -> None:
    pointer = _write_artifact(
        tmp_path,
        phase="expansion_inventory_balanced",
        diagnostics_schema_version=2,
    )

    evidence = load_semiconductor_industry_evidence(
        pointer,
        evaluation_date=date(2026, 8, 9),
    )
    bridge = build_semiconductor_cycle_bridge(_proxy(), evidence)

    assert evidence.heuristic_phase == "expansion_inventory_balanced"
    assert bridge.industry_direction == "expansionary"
    assert bridge.alignment_state == "industry_issuer_expansion_aligned"
    assert evidence.decision_score_enabled is False


def test_rejects_unknown_diagnostics_schema(tmp_path: Path) -> None:
    pointer = _write_artifact(tmp_path, diagnostics_schema_version=999)

    with pytest.raises(ValueError, match="schema version is unsupported"):
        load_semiconductor_industry_evidence(
            pointer,
            evaluation_date=date(2026, 8, 9),
        )


def test_rejects_retroactive_use_before_capture_date(tmp_path: Path) -> None:
    pointer = _write_artifact(tmp_path)

    with pytest.raises(ValueError, match="before its capture date"):
        load_semiconductor_industry_evidence(
            pointer,
            evaluation_date=date(2026, 8, 8),
        )


def test_rejects_tampered_diagnostics(tmp_path: Path) -> None:
    pointer = _write_artifact(tmp_path)
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    diagnostics_path = Path(pointer_payload["diagnostics_path"])
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    diagnostics["latest"]["shipment_yoy_pct"] = 99.0
    diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="diagnostics hash"):
        load_semiconductor_industry_evidence(
            pointer,
            evaluation_date=date(2026, 8, 9),
        )


def test_expansion_alignment_and_score_invariance(tmp_path: Path) -> None:
    pointer = _write_artifact(tmp_path)
    evidence = load_semiconductor_industry_evidence(
        pointer,
        evaluation_date=date(2026, 8, 9),
    )
    proxy = _proxy()
    bridge = build_semiconductor_cycle_bridge(proxy, evidence)
    scorecards = pd.DataFrame(
        [
            {"ticker": "005930", "composite_score": 3.8},
            {"ticker": "000660", "composite_score": 4.1},
            {"ticker": "012345", "composite_score": 2.9},
        ]
    )

    enriched = attach_semiconductor_industry_to_scorecards(scorecards, proxy, bridge)

    assert list(enriched["composite_score"]) == [3.8, 4.1, 2.9]
    assert bridge.alignment_state == "industry_issuer_expansion_aligned"
    assert enriched.loc[0, "industry_evidence_available"]
    assert enriched.loc[1, "industry_evidence_available"]
    assert not enriched.loc[2, "industry_evidence_available"]
    assert not bool(enriched.loc[0, "industry_evidence_score_enabled"])
    assert enriched.loc[0, "industry_capacity_yoy_pct"] == pytest.approx(8.654906)

    records = pd.DataFrame(
        [
            {"ticker": "005930", "decision_state": "mixed_setup"},
            {"ticker": "000660", "decision_state": "positive_setup"},
            {"ticker": "012345", "decision_state": "avoid"},
        ]
    )
    attached = attach_semiconductor_industry_to_records(records, enriched)
    assert attached.loc[0, "industry_issuer_alignment"] == "industry_issuer_expansion_aligned"
    assert pd.isna(attached.loc[2, "industry_issuer_alignment"])


def test_report_states_alignment_and_non_scoring_boundary(tmp_path: Path) -> None:
    pointer = _write_artifact(tmp_path)
    evidence = load_semiconductor_industry_evidence(
        pointer,
        evaluation_date=date(2026, 8, 9),
    )
    bridge = build_semiconductor_cycle_bridge(_proxy(), evidence)

    report = append_semiconductor_industry_evidence_report("# Existing\n", bridge)

    assert "KOSIS 반도체 산업 사이클 증거" in report
    assert "industry_issuer_expansion_aligned" in report
    assert "capture date 이전 평가에 소급 적용할 수 없습니다" in report
    assert "의사결정 점수에는 반영하지 않습니다" in report


def test_package_routes_decisions_through_industry_wrapper() -> None:
    source = Path("src/alpha_cycle/intelligence/__init__.py").read_text(encoding="utf-8")
    assert "decision_industry_evidence_calibrated" in source
