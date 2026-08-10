from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.kis_forward_estimate_revision_cli import run_revision_tracker


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _binding(*, revenue_row: int = 1) -> dict[str, object]:
    return {
        "binding_version": 1,
        "verified_symbols": ["000660", "005930"],
        "period_field_policy": "output4_positional_data_columns",
        "metrics": [
            {
                "metric": "net_income_attributable_to_owners",
                "output_name": "output2",
                "row_number_1_based": 5,
                "scale_to_krw": 100_000_000.0,
            },
            {
                "metric": "operating_income",
                "output_name": "output2",
                "row_number_1_based": 3,
                "scale_to_krw": 100_000_000.0,
            },
            {
                "metric": "revenue",
                "output_name": "output2",
                "row_number_1_based": revenue_row,
                "scale_to_krw": 100_000_000.0,
            },
        ],
        "owner_reference_account_id": "ifrs-full_ProfitLossAttributableToOwnersOfParent",
    }


def _frame(values: tuple[float, float, float]) -> pd.DataFrame:
    rows = []
    for metric, value in zip(
        ("revenue", "operating_income", "net_income_attributable_to_owners"),
        values,
        strict=True,
    ):
        rows.append(
            {
                "symbol": "000660",
                "metric": metric,
                "period_label": "2026.12E",
                "fiscal_year": 2026,
                "value_krw": value,
                "unit": "KRW",
                "historical_semantic_crosscheck_verified": True,
                "provider_semantics_certified": False,
                "consensus_certified": False,
                "revision_certified": False,
                "decision_score_enabled": False,
            }
        )
    return pd.DataFrame(rows)


def _artifact(
    root: Path,
    *,
    directory_name: str,
    artifact_digit: str,
    source_digit: str,
    captured_at: str,
    values: tuple[float, float, float],
    revenue_row: int = 1,
) -> Path:
    directory = root / directory_name
    artifact_id = artifact_digit * 64
    source_id = source_digit * 64
    manifest = {
        "schema_version": 1,
        "artifact_id": artifact_id,
        "status": "forward_estimate_levels_normalized",
        "captured_at": captured_at,
        "source_expectation_snapshot_id": source_id,
        "source_expectation_captured_at": captured_at,
        "historical_semantic_crosscheck_verified": True,
        "forward_values_normalized": True,
        "provider_semantics_certified": False,
        "consensus_certified": False,
        "revision_certified": False,
        "point_in_time_backtest_eligible": False,
        "decision_score_enabled": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    _write_json(directory / "manifest.json", manifest)
    _write_json(directory / "semantic_binding.json", _binding(revenue_row=revenue_row))
    _frame(values).to_csv(directory / "forward_estimates.csv", index=False)
    return directory


def test_revision_tracker_reports_baseline_only_for_one_distinct_source_snapshot(
    tmp_path: Path,
) -> None:
    forward_root = tmp_path / "forward"
    _artifact(
        forward_root,
        directory_name="20260810T010000000000Z__aaaaaaaaaaaa",
        artifact_digit="a",
        source_digit="1",
        captured_at="2026-08-10T10:00:00+09:00",
        values=(100.0, 20.0, 15.0),
    )

    pointer = run_revision_tracker(
        forward_root=forward_root,
        output_root=tmp_path / "changes",
        now=datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "estimate_change_baseline_only"
    assert pointer["distinct_source_snapshot_count"] == 1
    assert pointer["estimate_snapshot_change_verified"] is False
    assert pointer["consensus_revision_certified"] is False
    frame = pd.read_csv(Path(str(pointer["estimate_changes_path"])))
    assert frame.empty


def test_revision_tracker_compares_two_distinct_snapshots_without_materiality_threshold(
    tmp_path: Path,
) -> None:
    forward_root = tmp_path / "forward"
    _artifact(
        forward_root,
        directory_name="20260810T010000000000Z__aaaaaaaaaaaa",
        artifact_digit="a",
        source_digit="1",
        captured_at="2026-08-10T10:00:00+09:00",
        values=(100.0, 200.0, 300.0),
    )
    _artifact(
        forward_root,
        directory_name="20260811T010000000000Z__bbbbbbbbbbbb",
        artifact_digit="b",
        source_digit="2",
        captured_at="2026-08-11T10:00:00+09:00",
        values=(110.0, 180.0, 300.0),
    )

    pointer = run_revision_tracker(
        forward_root=forward_root,
        output_root=tmp_path / "changes",
        now=datetime(2026, 8, 11, 2, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "estimate_snapshot_change_available"
    assert pointer["distinct_source_snapshot_count"] == 2
    assert pointer["estimate_snapshot_change_verified"] is True
    assert pointer["consensus_certified"] is False
    assert pointer["consensus_revision_certified"] is False
    frame = pd.read_csv(Path(str(pointer["estimate_changes_path"])))
    directions = frame.set_index("metric")["direction"].to_dict()
    assert directions == {
        "net_income_attributable_to_owners": "unchanged",
        "operating_income": "down",
        "revenue": "up",
    }
    changes = frame.set_index("metric")["percent_change"].to_dict()
    assert changes["revenue"] == pytest.approx(10.0)
    assert changes["operating_income"] == pytest.approx(-10.0)
    assert changes["net_income_attributable_to_owners"] == pytest.approx(0.0)


def test_revision_tracker_deduplicates_repeated_normalizations_of_same_source_snapshot(
    tmp_path: Path,
) -> None:
    forward_root = tmp_path / "forward"
    _artifact(
        forward_root,
        directory_name="20260810T010000000000Z__aaaaaaaaaaaa",
        artifact_digit="a",
        source_digit="1",
        captured_at="2026-08-10T10:00:00+09:00",
        values=(100.0, 20.0, 15.0),
    )
    _artifact(
        forward_root,
        directory_name="20260810T020000000000Z__cccccccccccc",
        artifact_digit="c",
        source_digit="1",
        captured_at="2026-08-10T10:00:00+09:00",
        values=(100.0, 20.0, 15.0),
    )

    pointer = run_revision_tracker(
        forward_root=forward_root,
        output_root=tmp_path / "changes",
        now=datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "estimate_change_baseline_only"
    assert pointer["distinct_source_snapshot_count"] == 1


def test_revision_tracker_fails_closed_when_semantic_binding_changes(tmp_path: Path) -> None:
    forward_root = tmp_path / "forward"
    _artifact(
        forward_root,
        directory_name="20260810T010000000000Z__aaaaaaaaaaaa",
        artifact_digit="a",
        source_digit="1",
        captured_at="2026-08-10T10:00:00+09:00",
        values=(100.0, 20.0, 15.0),
    )
    _artifact(
        forward_root,
        directory_name="20260811T010000000000Z__bbbbbbbbbbbb",
        artifact_digit="b",
        source_digit="2",
        captured_at="2026-08-11T10:00:00+09:00",
        values=(110.0, 22.0, 16.0),
        revenue_row=2,
    )

    with pytest.raises(ValueError, match="semantic binding changed"):
        run_revision_tracker(
            forward_root=forward_root,
            output_root=tmp_path / "changes",
            now=datetime(2026, 8, 11, 2, 0, tzinfo=UTC),
        )
