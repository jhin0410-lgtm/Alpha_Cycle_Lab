from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from alpha_cycle.kis_expectation_semantic_crosscheck_cli import run_crosscheck
from alpha_cycle.providers.kis_research import KIS_RESEARCH_SOURCE_SCOPE

SYMBOLS = ("000660", "005930")
PERIODS = ("2023.12", "2024.12", "2025.12", "2026.12E", "2027.12E")

ACTUALS = {
    "000660": {
        "revenue": (
            32_765_700_000_000.0,
            66_193_000_000_000.0,
            92_100_000_000_000.0,
        ),
        "operating_income": (
            -7_730_300_000_000.0,
            23_467_000_000_000.0,
            38_200_000_000_000.0,
        ),
        "net_income": (
            -9_112_400_000_000.0,
            19_797_000_000_000.0,
            31_500_000_000_000.0,
        ),
    },
    "005930": {
        "revenue": (
            258_935_500_000_000.0,
            300_870_900_000_000.0,
            333_600_000_000_000.0,
        ),
        "operating_income": (
            6_567_000_000_000.0,
            32_726_000_000_000.0,
            44_100_000_000_000.0,
        ),
        "net_income": (
            14_473_400_000_000.0,
            34_451_000_000_000.0,
            38_700_000_000_000.0,
        ),
    },
}


def _data_row(
    values: tuple[float, float, float],
    *,
    forecast_a: float,
    forecast_b: float,
) -> dict[str, str]:
    scaled = [value / 1e8 for value in values]
    return {
        "data1": str(scaled[0]),
        "data2": str(scaled[1]),
        "data3": str(scaled[2]),
        "data4": str(forecast_a),
        "data5": str(forecast_b),
    }


def _random_row(seed: float) -> dict[str, str]:
    return {
        "data1": str(seed + 11.0),
        "data2": str(seed + 23.0),
        "data3": str(seed + 47.0),
        "data4": str(seed + 89.0),
        "data5": str(seed + 131.0),
    }


def _write_expectation(root: Path, *, shuffle_revenue: bool = False) -> Path:
    directory = root / "20260810T043313144358Z__b5c6cd763004"
    directory.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "snapshot_id": "b" * 64,
        "captured_at": "2026-08-10T13:33:13+09:00",
        "provider": "korea_investment_openapi",
        "source_scope": KIS_RESEARCH_SOURCE_SCOPE,
        "symbols": list(SYMBOLS),
        "semantic_status": "raw_structure_only",
        "consensus_certified": False,
        "revision_certified": False,
        "account_api_enabled": False,
        "holdings_api_enabled": False,
        "balance_api_enabled": False,
        "order_api_enabled": False,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    raw: dict[str, object] = {}
    for symbol in SYMBOLS:
        revenue = _data_row(
            ACTUALS[symbol]["revenue"],
            forecast_a=4_000_001,
            forecast_b=4_000_002,
        )
        if shuffle_revenue:
            revenue["data1"], revenue["data2"] = revenue["data2"], revenue["data1"]
        output2 = [
            revenue,
            _random_row(1_000.0),
            _data_row(
                ACTUALS[symbol]["operating_income"],
                forecast_a=5_000_001,
                forecast_b=5_000_002,
            ),
            _random_row(2_000.0),
            _data_row(
                ACTUALS[symbol]["net_income"],
                forecast_a=6_000_001,
                forecast_b=6_000_002,
            ),
            _random_row(3_000.0),
        ]
        output3_count = 3 if symbol == "000660" else 8
        raw[symbol] = {
            "rt_cd": "0",
            "output1": {"sht_cd": symbol},
            "output2": output2,
            "output3": [
                _random_row(10_000.0 + index * 1_000.0)
                for index in range(output3_count)
            ],
            "output4": [{"dt": period} for period in PERIODS],
        }
    (directory / "raw_estimate_perform.json").write_text(
        json.dumps(raw),
        encoding="utf-8",
    )
    return directory


def _write_valuation(root: Path) -> Path:
    directory = root / "20260809T220000000000Z__cccccccccccc"
    directory.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "snapshot_id": "c" * 64,
        "captured_at": "2026-08-09T22:00:00+00:00",
        "evaluation_date": "2026-08-09",
        "history_years": 3,
        "symbols": list(SYMBOLS),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    rows: list[dict[str, object]] = []
    for symbol in SYMBOLS:
        values = ACTUALS[symbol]
        rows.extend(
            [
                {
                    "ticker": symbol,
                    "business_year": 2024,
                    "period_label": "FY",
                    "revenue": values["revenue"][1],
                    "revenue_prior_same": values["revenue"][0],
                    "operating_income": values["operating_income"][1],
                    "operating_income_prior_same": values["operating_income"][0],
                    "net_income": values["net_income"][1],
                    "net_income_prior_same": values["net_income"][0],
                },
                {
                    "ticker": symbol,
                    "business_year": 2025,
                    "period_label": "FY",
                    "revenue": values["revenue"][2],
                    "revenue_prior_same": values["revenue"][1],
                    "operating_income": values["operating_income"][2],
                    "operating_income_prior_same": values["operating_income"][1],
                    "net_income": values["net_income"][2],
                    "net_income_prior_same": values["net_income"][1],
                },
            ]
        )
    pd.DataFrame(rows).to_csv(directory / "financial_history.csv", index=False)
    return directory


def test_crosscheck_finds_three_unique_historical_actual_rows(tmp_path: Path) -> None:
    expectation_root = tmp_path / "expectation-intelligence"
    valuation_root = tmp_path / "valuation-intelligence"
    output_root = tmp_path / "crosscheck"
    _write_expectation(expectation_root)
    _write_valuation(valuation_root)

    pointer = run_crosscheck(
        expectation_root=expectation_root,
        valuation_root=valuation_root,
        output_root=output_root,
        now=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )

    assert pointer["status"] == "historical_actual_crosscheck_complete"
    assert pointer["verified_candidate_count"] == 3
    artifact = json.loads(
        Path(str(pointer["crosscheck_path"])).read_text(encoding="utf-8")
    )
    assert artifact["actual_reference_policy"] == (
        "prefer_following_fy_prior_same_then_direct_fy"
    )
    assert artifact["actual_reference_basis"]["000660"]["2023"]["revenue"] == (
        "2024_FY_prior_same"
    )
    assert artifact["actual_reference_basis"]["000660"]["2024"]["revenue"] == (
        "2025_FY_prior_same"
    )
    assert artifact["actual_reference_basis"]["000660"]["2025"]["revenue"] == (
        "2025_FY_current"
    )
    assert artifact["provider_semantics_certified"] is False
    assert artifact["consensus_certified"] is False
    assert artifact["revision_certified"] is False
    assert artifact["point_in_time_backtest_eligible"] is False
    assert artifact["forecast_values_published"] is False
    assert artifact["decision_score_enabled"] is False

    metrics = artifact["metric_results"]
    assert metrics["revenue"]["status"] == "unique_historical_actual_match"
    assert metrics["revenue"]["output_name"] == "output2"
    assert metrics["revenue"]["row_number_1_based"] == 1
    assert metrics["operating_income"]["row_number_1_based"] == 3
    assert metrics["net_income"]["row_number_1_based"] == 5
    for metric in ("revenue", "operating_income", "net_income"):
        assert metrics[metric]["scale_to_krw"] == 1e8
        assert metrics[metric]["year_to_field"] == {
            "2023": "data1",
            "2024": "data2",
            "2025": "data3",
        }
        assert metrics[metric]["forecast_period_labels"] == [
            "2026.12E",
            "2027.12E",
        ]
        assert metrics[metric]["forecast_fields_positional"] == ["data4", "data5"]
        assert metrics[metric]["forecast_values_published"] is False

    rendered = json.dumps(artifact)
    for hidden_forecast in ("4000001", "5000001", "6000001"):
        assert hidden_forecast not in rendered
    pointer_path = output_root / "latest_kis_expectation_semantic_crosscheck.json"
    assert pointer_path.read_bytes().isascii()


def test_crosscheck_rejects_nonpositional_best_mapping_as_verified(tmp_path: Path) -> None:
    expectation_root = tmp_path / "expectation-intelligence"
    valuation_root = tmp_path / "valuation-intelligence"
    output_root = tmp_path / "crosscheck"
    _write_expectation(expectation_root, shuffle_revenue=True)
    _write_valuation(valuation_root)

    pointer = run_crosscheck(
        expectation_root=expectation_root,
        valuation_root=valuation_root,
        output_root=output_root,
        now=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
    )

    artifact = json.loads(
        Path(str(pointer["crosscheck_path"])).read_text(encoding="utf-8")
    )
    assert pointer["status"] == "historical_actual_crosscheck_partial"
    assert artifact["metric_results"]["revenue"]["status"] == "no_verified_match"
    verified_metrics = {item["metric"] for item in artifact["verified_candidates"]}
    assert "revenue" not in verified_metrics
    assert {"operating_income", "net_income"}.issubset(verified_metrics)
