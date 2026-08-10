from __future__ import annotations

import json
from pathlib import Path

import pytest

from alpha_cycle.kis_expectation_inventory_cli import inspect_expectation_snapshot
from alpha_cycle.providers.kis_research import KIS_RESEARCH_SOURCE_SCOPE


def _write_snapshot(tmp_path: Path, *, sensitive: bool = False) -> Path:
    root = tmp_path / "expectation-intelligence"
    directory = root / "20260810T043313144358Z__abcdef123456"
    directory.mkdir(parents=True)
    snapshot_id = "a" * 64
    manifest = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "captured_at": "2026-08-10T13:33:13+09:00",
        "provider": "korea_investment_openapi",
        "source_scope": KIS_RESEARCH_SOURCE_SCOPE,
        "symbols": ["000660", "005930"],
        "semantic_status": "raw_structure_only",
        "consensus_certified": False,
        "revision_certified": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    periods = ["2023.12", "2024.12", "2025.12", "2026.12E", "2027.12E"]
    payload = {
        "000660": {
            "rt_cd": "0",
            "output1": {
                "sht_cd": "000660",
                "item_kor_nm": "SK하이닉스",
                "capital": "1",
                "estdate": "2",
                "forn_item_lmtrt": "3",
                "name1": "x",
                "name2": "y",
                "rcmd_name": "z",
            },
            "output2": [
                {
                    "data1": "327657.123456",
                    "data2": "2",
                    "data3": "3",
                    "data4": "4",
                    "data5": "5",
                }
                for _ in range(6)
            ],
            "output3": [
                {
                    "data1": "59434.654321",
                    "data2": "2",
                    "data3": "3",
                    "data4": "4",
                    "data5": "5",
                }
                for _ in range(3)
            ],
            "output4": [{"dt": period} for period in periods],
        },
        "005930": {
            "rt_cd": "0",
            "output1": {
                "sht_cd": "005930",
                "item_kor_nm": "삼성전자",
                "capital": "1",
                "estdate": "2",
                "forn_item_lmtrt": "3",
                "name1": "x",
                "name2": "y",
                "rcmd_name": "z",
            },
            "output2": [
                {
                    "data1": "2589355.246810",
                    "data2": "2",
                    "data3": "3",
                    "data4": "4",
                    "data5": "5",
                }
                for _ in range(6)
            ],
            "output3": [
                {
                    "data1": "452335.135790",
                    "data2": "2",
                    "data3": "3",
                    "data4": "4",
                    "data5": "5",
                }
                for _ in range(8)
            ],
            "output4": [{"dt": period} for period in periods],
        },
    }
    if sensitive:
        payload["000660"]["output1"]["access_token"] = "should-not-exist"
    (directory / "raw_estimate_perform.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def test_inspector_reports_live_shape_without_any_data_values(tmp_path: Path) -> None:
    root = _write_snapshot(tmp_path)

    result = inspect_expectation_snapshot(root)

    assert result["status"] == "expectation_inventory_inspected"
    assert result["source_scope"] == KIS_RESEARCH_SOURCE_SCOPE
    assert result["provider_semantics_certified"] is False
    assert result["consensus_certified"] is False
    assert result["revision_certified"] is False
    assert result["decision_score_enabled"] is False
    assert result["numeric_values_exposed"] is False

    inventory = result["symbol_inventory"]
    assert isinstance(inventory, dict)
    hynix = inventory["000660"]
    samsung = inventory["005930"]
    assert isinstance(hynix, dict)
    assert isinstance(samsung, dict)
    assert hynix["period_axis"] == [
        "2023.12",
        "2024.12",
        "2025.12",
        "2026.12E",
        "2027.12E",
    ]
    assert hynix["period_axis_count"] == 5

    hynix_outputs = hynix["outputs"]
    samsung_outputs = samsung["outputs"]
    assert hynix_outputs["output2"]["row_count"] == 6
    assert hynix_outputs["output3"]["row_count"] == 3
    assert samsung_outputs["output3"]["row_count"] == 8
    assert hynix_outputs["output2"]["data_value_fields"] == [
        "data1",
        "data2",
        "data3",
        "data4",
        "data5",
    ]
    assert hynix_outputs["output2"]["data_value_field_count"] == 5
    assert hynix_outputs["output2"]["numeric_values_exposed"] is False

    observations = hynix["matrix_observations"]
    assert observations["output2"]["period_axis_cardinality_matches"] is True
    assert observations["output3"]["period_axis_cardinality_matches"] is True
    assert observations["output2"]["column_period_alignment_certified"] is False
    assert observations["output2"]["row_semantics_certified"] is False
    assert observations["output2"]["financial_metric_semantics_certified"] is False

    rendered = json.dumps(result, ensure_ascii=False)
    for private_value in (
        "327657.123456",
        "59434.654321",
        "2589355.246810",
        "452335.135790",
    ):
        assert private_value not in rendered


def test_inspector_fails_closed_on_sensitive_looking_response_key(tmp_path: Path) -> None:
    root = _write_snapshot(tmp_path, sensitive=True)

    with pytest.raises(ValueError, match="sensitive-looking key"):
        inspect_expectation_snapshot(root)


def test_inspector_requires_all_non_scoring_manifest_flags(tmp_path: Path) -> None:
    root = _write_snapshot(tmp_path)
    directory = next(root.iterdir())
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["consensus_certified"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="consensus_certified=false"):
        inspect_expectation_snapshot(root)
