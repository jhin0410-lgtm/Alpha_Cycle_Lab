from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.kis_forward_estimates import (
    OWNER_ACCOUNT_ID,
    build_semantic_binding,
    normalize_forward_estimates,
)
from alpha_cycle.kis_forward_estimate_cli import run_normalization

GENERAL_ID = "1" * 64
OWNER_ID = "2" * 64
EVIDENCE_EXPECTATION_ID = "3" * 64
VALUATION_ID = "4" * 64
SOURCE_EXPECTATION_ID = "5" * 64


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _verified_result(row: int) -> dict[str, object]:
    return {
        "status": "unique_historical_actual_match",
        "output_name": "output2",
        "row_number_1_based": row,
        "scale_to_krw": 100_000_000.0,
        "year_to_field": {"2023": "data1", "2024": "data2", "2025": "data3"},
        "forecast_period_labels": ["2026.12E", "2027.12E"],
        "forecast_fields_positional": ["data4", "data5"],
        "forecast_values_published": False,
    }


def _crosscheck_pointers(root: Path) -> tuple[Path, Path]:
    general_dir = root / "general" / "artifact"
    owner_dir = root / "owner" / "artifact"
    general = {
        "artifact_id": GENERAL_ID,
        "status": "historical_actual_crosscheck_partial",
        "expectation_snapshot_id": EVIDENCE_EXPECTATION_ID,
        "valuation_snapshot_id": VALUATION_ID,
        "metric_results": {
            "revenue": _verified_result(1),
            "operating_income": _verified_result(3),
            "net_income": {"status": "no_verified_match"},
        },
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "decision_score_enabled": False,
    }
    owner = {
        "artifact_id": OWNER_ID,
        "status": "owner_net_income_historical_match_verified",
        "expectation_snapshot_id": EVIDENCE_EXPECTATION_ID,
        "valuation_snapshot_id": VALUATION_ID,
        "authoritative_reference_account_id": OWNER_ACCOUNT_ID,
        "metric_result": _verified_result(5),
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "decision_score_enabled": False,
    }
    general_path = general_dir / "crosscheck.json"
    owner_path = owner_dir / "crosscheck.json"
    _write_json(general_path, general)
    _write_json(owner_path, owner)
    general_pointer = root / "general" / "latest.json"
    owner_pointer = root / "owner" / "latest.json"
    _write_json(
        general_pointer,
        {"artifact_id": GENERAL_ID, "crosscheck_path": str(general_path)},
    )
    _write_json(
        owner_pointer,
        {"artifact_id": OWNER_ID, "crosscheck_path": str(owner_path)},
    )
    return general_pointer, owner_pointer


def _output2_rows(multiplier: float) -> list[dict[str, float]]:
    def row(values: tuple[float, float, float, float, float]) -> dict[str, float]:
        return {f"data{index}": value for index, value in enumerate(values, start=1)}

    return [
        row(tuple(multiplier * value for value in (100, 120, 150, 180, 210))),
        row(tuple(multiplier * value for value in (1, 1, 1, 1, 1))),
        row(tuple(multiplier * value for value in (10, 18, 30, 45, 60))),
        row(tuple(multiplier * value for value in (2, 2, 2, 2, 2))),
        row(tuple(multiplier * value for value in (7, 13, 22, 35, 48))),
        row(tuple(multiplier * value for value in (3, 3, 3, 3, 3))),
    ]


def _expectation_snapshot(root: Path, *, structural_break: bool = False) -> Path:
    directory = root / "20260810T060000000000Z__555555555555"
    manifest = {
        "schema_version": 1,
        "snapshot_id": SOURCE_EXPECTATION_ID,
        "captured_at": "2026-08-10T15:00:00+09:00",
        "provider": "korea_investment_openapi",
        "source_scope": "kis_estimate_perform_raw_unclassified",
        "symbols": ["000660", "005930"],
        "semantic_status": "raw_structure_only",
        "consensus_certified": False,
        "revision_certified": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    raw: dict[str, object] = {}
    for symbol, multiplier in (("000660", 1.0), ("005930", 10.0)):
        rows = _output2_rows(multiplier)
        if structural_break and symbol == "005930":
            rows[0].pop("data5")
        raw[symbol] = {
            "output1": {},
            "output2": rows,
            "output3": [],
            "output4": [
                {"dt": "2023.12"},
                {"dt": "2024.12"},
                {"dt": "2025.12"},
                {"dt": "2026.12E"},
                {"dt": "2027.12E"},
            ],
        }
    _write_json(directory / "manifest.json", manifest)
    _write_json(directory / "raw_estimate_perform.json", raw)
    return directory


def test_binding_and_forward_normalization_support_new_structurally_compatible_snapshot(
    tmp_path: Path,
) -> None:
    general_pointer, owner_pointer = _crosscheck_pointers(tmp_path)
    expectation_dir = _expectation_snapshot(tmp_path / "expectations")
    binding = build_semantic_binding(
        general_crosscheck_pointer=general_pointer,
        owner_crosscheck_pointer=owner_pointer,
    )

    snapshot_id, captured_at, forward, summary = normalize_forward_estimates(
        expectation_directory=expectation_dir,
        binding=binding,
    )

    assert snapshot_id == SOURCE_EXPECTATION_ID
    assert captured_at.isoformat() == "2026-08-10T15:00:00+09:00"
    assert len(forward) == 12
    assert set(forward["metric"]) == {
        "revenue",
        "operating_income",
        "net_income_attributable_to_owners",
    }
    revenue_2026 = forward.loc[
        (forward["symbol"] == "000660")
        & (forward["metric"] == "revenue")
        & (forward["period_label"] == "2026.12E")
    ].iloc[0]
    assert revenue_2026["value_krw"] == 18_000_000_000.0
    assert revenue_2026["previous_value_krw"] == 15_000_000_000.0
    assert revenue_2026["growth_from_previous_pct"] == pytest.approx(20.0)
    assert bool(revenue_2026["growth_comparable"]) is True
    summary_row = summary.loc[
        (summary["symbol"] == "000660")
        & (summary["period_label"] == "2026.12E")
    ].iloc[0]
    assert summary_row["operating_margin_pct"] == pytest.approx(25.0)
    assert summary_row["owner_net_margin_pct"] == pytest.approx(19.44444444)


def test_forward_normalization_fails_closed_when_kis_data_shape_changes(tmp_path: Path) -> None:
    general_pointer, owner_pointer = _crosscheck_pointers(tmp_path)
    expectation_dir = _expectation_snapshot(
        tmp_path / "expectations",
        structural_break=True,
    )
    binding = build_semantic_binding(
        general_crosscheck_pointer=general_pointer,
        owner_crosscheck_pointer=owner_pointer,
    )

    with pytest.raises(ValueError, match="DATA structure changed"):
        normalize_forward_estimates(
            expectation_directory=expectation_dir,
            binding=binding,
        )


def test_binding_rejects_crosschecks_from_different_expectation_snapshots(
    tmp_path: Path,
) -> None:
    general_pointer, owner_pointer = _crosscheck_pointers(tmp_path)
    owner = json.loads(Path(json.loads(owner_pointer.read_text())["crosscheck_path"]).read_text())
    owner["expectation_snapshot_id"] = "6" * 64
    _write_json(Path(json.loads(owner_pointer.read_text())["crosscheck_path"]), owner)

    with pytest.raises(ValueError, match="different KIS expectation snapshots"):
        build_semantic_binding(
            general_crosscheck_pointer=general_pointer,
            owner_crosscheck_pointer=owner_pointer,
        )


def test_cli_writes_private_forward_artifact_without_consensus_or_revision_claims(
    tmp_path: Path,
) -> None:
    general_pointer, owner_pointer = _crosscheck_pointers(tmp_path)
    expectation_root = tmp_path / "expectations"
    _expectation_snapshot(expectation_root)
    output_root = tmp_path / "forward"

    pointer = run_normalization(
        expectation_root=expectation_root,
        general_crosscheck_pointer=general_pointer,
        owner_crosscheck_pointer=owner_pointer,
        output_root=output_root,
        now=datetime(2026, 8, 10, 6, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "forward_estimate_levels_normalized"
    assert pointer["source_expectation_snapshot_id"] == SOURCE_EXPECTATION_ID
    assert pointer["historical_semantic_crosscheck_verified"] is True
    assert pointer["forward_values_normalized"] is True
    assert pointer["estimate_snapshot_change_available"] is False
    assert pointer["provider_semantics_certified"] is False
    assert pointer["consensus_certified"] is False
    assert pointer["revision_certified"] is False
    assert pointer["decision_score_enabled"] is False
    manifest = json.loads(Path(str(pointer["manifest_path"])).read_text(encoding="utf-8"))
    assert manifest["point_in_time_backtest_eligible"] is False
    frame = pd.read_csv(Path(str(pointer["forward_estimates_path"])))
    assert len(frame) == 12
    assert set(frame["period_label"]) == {"2026.12E", "2027.12E"}
