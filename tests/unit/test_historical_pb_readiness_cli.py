from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.historical_pb_readiness_cli import inspect_historical_pb_readiness


def _artifact(tmp_path: Path) -> Path:
    directory = tmp_path / "artifact"
    directory.mkdir()
    summary = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "observation_count": 481,
                "first_date": "2024-08-14",
                "last_date": "2026-08-10",
                "latest_pb": 6.15,
                "pb_min": 1.62,
                "pb_p25": 2.13,
                "pb_median": 2.45,
                "pb_p75": 3.10,
                "pb_max": 6.50,
                "latest_pb_percentile": 98.5,
                "band_status": "observational_1y_ready",
            },
            {
                "ticker": "005930",
                "observation_count": 209,
                "first_date": "2024-08-14",
                "last_date": "2026-05-14",
                "latest_pb": 4.37,
                "pb_min": 0.87,
                "pb_p25": 1.01,
                "pb_median": 1.19,
                "pb_p75": 1.55,
                "pb_max": 4.40,
                "latest_pb_percentile": 100.0,
                "band_status": "insufficient_history",
            },
        ]
    )
    summary.to_csv(directory / "historical_pb_summary.csv", index=False)
    artifact_id = "a" * 64
    manifest = {
        "status": "historical_pb_observational_evidence_built",
        "artifact_id": artifact_id,
        "evaluation_date": "2026-08-10",
        "warnings": [
            "005930: historical P/B skipped dates: unresolved_share_count:우선주=58",
            "000660: historical P/B skipped dates: share_report_unavailable=119",
        ],
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    pointer = {
        "status": "historical_pb_observational_evidence_built",
        "artifact_id": artifact_id,
        "artifact_directory": str(directory),
        "manifest_path": str(directory / "manifest.json"),
        "summary_path": str(directory / "historical_pb_summary.csv"),
        "evaluation_date": "2026-08-10",
        "historical_vintage_certified": False,
        "point_in_time_backtest_eligible": False,
        "fair_value_estimate_enabled": False,
        "target_price_enabled": False,
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    pointer_path = tmp_path / "latest.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return pointer_path


def test_readiness_distinguishes_current_and_stale_observations(tmp_path: Path) -> None:
    payload = inspect_historical_pb_readiness(_artifact(tmp_path))

    assert payload["status"] == "historical_pb_readiness_inspected"
    assert payload["all_symbols_current_on_evaluation_date"] is False
    assert payload["all_symbols_current_observational_band_usable"] is False
    symbols = {row["ticker"]: row for row in payload["symbols"]}

    hynix = symbols["000660"]
    assert hynix["latest_observation_lag_days"] == 0
    assert hynix["current_observation_available"] is True
    assert hynix["historical_band_history_ready"] is True
    assert hynix["current_observational_band_usable"] is True

    samsung = symbols["005930"]
    assert samsung["latest_observation_lag_days"] == 88
    assert samsung["current_observation_available"] is False
    assert samsung["historical_band_history_ready"] is False
    assert samsung["current_observational_band_usable"] is False
    assert "unresolved_share_count:우선주=58" in samsung["builder_warnings"][0]
    assert payload["decision_score_enabled"] is False


def test_readiness_requires_non_scoring_pointer_boundary(tmp_path: Path) -> None:
    pointer_path = _artifact(tmp_path)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["decision_score_enabled"] = True
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    with pytest.raises(ValueError, match="decision_score_enabled=false"):
        inspect_historical_pb_readiness(pointer_path)
