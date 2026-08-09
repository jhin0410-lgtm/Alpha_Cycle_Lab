from __future__ import annotations

import json
from pathlib import Path

import pytest

from alpha_cycle.kis_expectation_inventory_cli import inspect_expectation_snapshot
from alpha_cycle.providers.kis_research import KIS_RESEARCH_SOURCE_SCOPE


def _write_snapshot(tmp_path: Path, *, sensitive: bool = False) -> Path:
    root = tmp_path / "expectation-intelligence"
    directory = root / "20260809T130000000000Z__abcdef123456"
    directory.mkdir(parents=True)
    snapshot_id = "a" * 64
    manifest = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "captured_at": "2026-08-09T22:00:00+09:00",
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
    payload = {
        symbol: {
            "rt_cd": "0",
            "output1": {"sht_cd": symbol, "item_kor_nm": "회사"},
            "output2": [
                {"data1": "매출액", "data2": "1", "data3": "2"},
                {"data1": "영업이익", "data2": "3", "data3": "4"},
            ],
            "output3": [{"data1": "EPS", "data2": "10", "data3": "11"}],
            "output4": [{"dt": "202512"}, {"dt": "202612E"}],
        }
        for symbol in ("000660", "005930")
    }
    if sensitive:
        payload["000660"]["output1"]["access_token"] = "should-not-exist"
    (directory / "raw_estimate_perform.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def test_inspector_reports_keys_labels_and_periods_without_numeric_estimates(
    tmp_path: Path,
) -> None:
    root = _write_snapshot(tmp_path)

    result = inspect_expectation_snapshot(root)

    assert result["status"] == "expectation_inventory_inspected"
    assert result["source_scope"] == KIS_RESEARCH_SOURCE_SCOPE
    assert result["consensus_certified"] is False
    assert result["revision_certified"] is False
    assert result["decision_score_enabled"] is False
    outputs = result["outputs"]
    assert isinstance(outputs, dict)
    hynix = outputs["000660"]
    assert isinstance(hynix, dict)
    output2 = hynix["output2"]
    output4 = hynix["output4"]
    assert output2["row_count"] == 2
    assert output2["keys"] == ["data1", "data2", "data3"]
    assert output2["data1_labels"] == ["매출액", "영업이익"]
    assert "1" not in json.dumps(result, ensure_ascii=False)
    assert output4["period_labels"] == ["202512", "202612E"]


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
