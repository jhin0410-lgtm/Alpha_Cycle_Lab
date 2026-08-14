from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.semiconductor_earnings_transmission import (
    MINIMUM_TRANSMISSION_OBSERVATIONS,
    TRANSMISSION_HYPOTHESES,
    TRANSMISSION_LAGS,
    append_semiconductor_transmission_report,
    build_semiconductor_transmission_evidence,
    summarize_semiconductor_transmission,
)


def _write_kosis_pointer(tmp_path: Path, *, months: int = 72, pit: bool = False) -> Path:
    artifact_id = "a" * 64
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    start = pd.Period("2020-07", freq="M")
    monthly: list[dict[str, object]] = []
    for index in range(months):
        period = start + index
        trend = float(index)
        monthly.append(
            {
                "period": period.strftime("%Y%m"),
                "production_yoy_pct": trend * 0.8,
                "shipment_yoy_pct": trend,
                "inventory_yoy_pct": -trend * 0.4,
                "capacity_yoy_pct": trend * 0.3,
                "utilization_yoy_pct": trend * 0.7,
                "production_mom_sa_pct": 1.0,
                "shipment_mom_sa_pct": 1.1,
                "inventory_mom_sa_pct": -0.5,
                "utilization_mom_sa_pct": 0.8,
                "shipment_minus_inventory_yoy_pp": trend * 1.4,
                "production_minus_shipment_yoy_pp": -trend * 0.2,
                "inventory_vs_shipment_index_ratio": 100.0 - trend * 0.1,
            }
        )
    diagnostics = {"schema_version": 2, "monthly": monthly}
    diagnostics_path = artifact / "diagnostics.json"
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")
    manifest = {
        "artifact_id": artifact_id,
        "status": "semiconductor_history_captured",
        "captured_at": "2026-08-14T06:00:00+00:00",
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": pit,
        "decision_score_enabled": False,
    }
    manifest_path = artifact / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    pointer = {
        "artifact_id": artifact_id,
        "status": "semiconductor_history_captured",
        "manifest_path": str(manifest_path),
        "diagnostics_path": str(diagnostics_path),
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": pit,
        "decision_score_enabled": False,
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def _issuer_history(quarters: int = 16) -> pd.DataFrame:
    start = pd.Period("2022Q1", freq="Q")
    rows: list[dict[str, object]] = []
    for ticker, multiplier in (("000660", 1.2), ("005930", 0.8)):
        for index in range(quarters):
            quarter = start + index
            period_end = quarter.end_time.normalize()
            signal = float(index + 10)
            rows.append(
                {
                    "ticker": ticker,
                    "period_label": f"Q{quarter.quarter}",
                    "period_end": period_end.date().isoformat(),
                    "available_date": (period_end + pd.Timedelta(days=45)).date().isoformat(),
                    "revenue_yoy": signal * multiplier,
                    "operating_income_yoy": signal * multiplier * 1.5,
                    "operating_margin_change_yoy_pp": signal * multiplier * 0.3,
                }
            )
    return pd.DataFrame(rows)


def test_transmission_builds_all_declared_lags_without_score_or_forecast(tmp_path: Path) -> None:
    pointer = _write_kosis_pointer(tmp_path)
    evidence = build_semiconductor_transmission_evidence(
        pointer,
        _issuer_history(),
        evaluation_date=date(2026, 8, 14),
    )

    assert evidence.decision_score_enabled is False
    assert evidence.forecast_enabled is False
    assert evidence.causal_claim_enabled is False
    assert evidence.point_in_time_backtest_eligible is False
    assert evidence.historical_vintage_certified is False
    assert len(evidence.relationships) == 2 * len(TRANSMISSION_HYPOTHESES) * len(TRANSMISSION_LAGS)
    assert set(evidence.relationships["lag_quarters"].astype(int)) == set(TRANSMISSION_LAGS)
    assert evidence.relationships["decision_score_enabled"].eq(False).all()
    assert evidence.relationships["forecast_enabled"].eq(False).all()
    assert evidence.relationships["causal_claim_enabled"].eq(False).all()

    summary = summarize_semiconductor_transmission(evidence)
    assert len(summary) == 2 * len(TRANSMISSION_HYPOTHESES)
    assert summary["transmission_status"].eq("descriptive_history_ready").all()
    assert summary["ready_lag_count"].eq(len(TRANSMISSION_LAGS)).all()
    assert summary["strongest_observed_lag_quarters"].notna().all()

    report = append_semiconductor_transmission_report("# Base\n", evidence)
    assert "반도체 산업 → 기업 실적 transmission" in report
    assert "in-sample descriptive" in report
    assert "PIT backtest·forecast·causal claim" in report


def test_transmission_withholds_relationship_statistics_when_history_is_shallow(
    tmp_path: Path,
) -> None:
    pointer = _write_kosis_pointer(tmp_path, months=36)
    evidence = build_semiconductor_transmission_evidence(
        pointer,
        _issuer_history(quarters=8),
        evaluation_date=date(2026, 8, 14),
    )

    assert MINIMUM_TRANSMISSION_OBSERVATIONS == 12
    assert evidence.relationships["history_ready"].eq(False).all()
    assert evidence.relationships["pearson"].isna().all()
    assert evidence.relationships["spearman"].isna().all()
    assert evidence.relationships["expected_sign_supported"].isna().all()
    summary = summarize_semiconductor_transmission(evidence)
    assert summary["transmission_status"].eq("insufficient_history").all()
    assert summary["strongest_observed_lag_quarters"].isna().all()


def test_transmission_rejects_point_in_time_claim_on_revision_sensitive_kosis(
    tmp_path: Path,
) -> None:
    pointer = _write_kosis_pointer(tmp_path, pit=True)
    with pytest.raises(ValueError, match="point_in_time_backtest_eligible=false"):
        build_semiconductor_transmission_evidence(
            pointer,
            _issuer_history(),
            evaluation_date=date(2026, 8, 14),
        )
