"""Tests for local KOSIS parameter-inventory inspection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alpha_cycle.kosis_industry_inventory_cli import inspect_latest_inventory


def _write_artifact(
    tmp_path: Path,
    *,
    scoring: bool = False,
    schema_version: int = 2,
) -> Path:
    artifact_directory = tmp_path / "쿠쿠" / "artifact"
    artifact_directory.mkdir(parents=True)
    if schema_version == 2:
        items = [
            {
                "item_id": "T002",
                "item_name": "출하량",
                "unit_variant_count": 1,
                "units": [{"unit_id": "IDX", "unit_name": "2020=100"}],
            },
            {
                "item_id": "T001",
                "item_name": "생산량",
                "unit_variant_count": 2,
                "units": [
                    {"unit_id": "U001", "unit_name": "개"},
                    {"unit_id": "U002", "unit_name": "천개"},
                ],
            },
        ]
    else:
        items = [
            {
                "item_id": "T002",
                "item_name": "출하량",
                "unit_id": "U001",
                "unit_name": "개",
            },
            {
                "item_id": "T001",
                "item_name": "생산량",
                "unit_id": "U001",
                "unit_name": "개",
            },
        ]
    inventory = {
        "inventory_schema_version": schema_version,
        "classification_count": 3,
        "classifications": [
            {
                "classification_ids": ["A001"],
                "classification_object_names": ["품목"],
                "classification_names": ["석탄"],
            },
            {
                "classification_ids": ["S001"],
                "classification_object_names": ["산업별"],
                "classification_names": ["반도체 제조업"],
            },
            {
                "classification_ids": ["S002"],
                "classification_object_names": ["품목"],
                "classification_names": ["D램"],
            },
        ],
        "item_count": 2,
        "items": items,
        "period_count": 1,
        "periods": ["202606"],
        "source_change_dates": ["20260731"],
        "missing_last_changed_rows": 0,
    }
    (artifact_directory / "parameter_inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False),
        encoding="utf-8",
    )
    pointer = {
        "artifact_id": "artifact-123",
        "artifact_directory": str(artifact_directory.resolve()),
        "status": "parameter_data_captured",
        "org_id": "101",
        "table_id": "DT_TEST",
        "table_name": "테스트 표",
        "periods": ["202606"],
        "revision_sensitive": True,
        "historical_vintage_certified": False,
        "industry_cycle_certified": False,
        "decision_score_enabled": scoring,
    }
    pointer_path = tmp_path / "latest_kosis_industry_parameters.json"
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=True),
        encoding="utf-8",
    )
    return pointer_path


def test_inspect_latest_inventory_returns_items_and_semiconductor_matches(
    tmp_path: Path,
) -> None:
    pointer_path = _write_artifact(tmp_path)

    result = inspect_latest_inventory(pointer_path=pointer_path)

    assert result["status"] == "inventory_inspected"
    assert result["artifact_id"] == "artifact-123"
    assert result["table_name"] == "테스트 표"
    assert result["inventory_schema_version"] == 2
    assert result["legacy_single_unit_summary"] is False
    assert result["item_count"] == 2
    assert result["classification_count"] == 3
    assert result["matched_classification_count"] == 2
    items = result["items"]
    assert isinstance(items, list)
    assert [row["item_id"] for row in items] == ["T001", "T002"]
    assert items[0]["unit_variant_count"] == 2
    assert items[0]["units"] == [
        {"unit_id": "U001", "unit_name": "개"},
        {"unit_id": "U002", "unit_name": "천개"},
    ]
    matched = result["matched_classifications"]
    assert isinstance(matched, list)
    assert [row["classification_ids"] for row in matched] == [["S001"], ["S002"]]
    assert result["decision_score_enabled"] is False


def test_inspect_latest_inventory_reads_legacy_single_unit_artifact(
    tmp_path: Path,
) -> None:
    pointer_path = _write_artifact(tmp_path, schema_version=1)

    result = inspect_latest_inventory(pointer_path=pointer_path)

    assert result["inventory_schema_version"] == 1
    assert result["legacy_single_unit_summary"] is True
    items = result["items"]
    assert isinstance(items, list)
    assert items[0]["unit_variant_count"] == 1
    assert items[0]["units"] == [{"unit_id": "U001", "unit_name": "개"}]


def test_inspect_latest_inventory_supports_custom_match_terms(tmp_path: Path) -> None:
    pointer_path = _write_artifact(tmp_path)

    result = inspect_latest_inventory(
        pointer_path=pointer_path,
        match_terms=("석탄",),
    )

    assert result["matched_classification_count"] == 1
    matched = result["matched_classifications"]
    assert isinstance(matched, list)
    assert matched[0]["classification_ids"] == ["A001"]


def test_inspect_latest_inventory_rejects_scoring_pointer(tmp_path: Path) -> None:
    pointer_path = _write_artifact(tmp_path, scoring=True)

    with pytest.raises(ValueError, match="non-scoring"):
        inspect_latest_inventory(pointer_path=pointer_path)
