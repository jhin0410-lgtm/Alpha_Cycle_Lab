from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_numeric_forecast import (
    build_locked_numeric_forecast,
    load_locked_numeric_forecast,
    load_numeric_forecast_contract,
    persist_locked_numeric_forecast,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_2026q3_prospective_feature import (
    FrozenProspectiveFeatureVector,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_selected_estimator_freeze import (
    FrozenSelectedEstimatorFullFit,
)

_KST = ZoneInfo("Asia/Seoul")


def _selected() -> FrozenSelectedEstimatorFullFit:
    return FrozenSelectedEstimatorFullFit(
        evidence_id="1" * 64,
        contract_evidence_id="2" * 64,
        execution_evidence_id="3" * 64,
        scope_evidence_id="4" * 64,
        combined_bundle_evidence_id="5" * 64,
        target_join_evidence_id="6" * 64,
        target_source_evidence_id="7" * 64,
        raw_target_capture_evidence_id="8" * 64,
        backtest_evidence_id="9" * 64,
        estimator_freeze_evidence_id="a" * 64,
        selected_candidate_id="lagged_gp_affine_ols",
        estimator="ordinary_least_squares",
        parameter_count=2,
        predictors=("lagged_company_gross_profit",),
        training_periods=tuple(
            f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3)
        ),
        training_row_count=20,
        scaling_ddof=0,
        predictor_means=(4_112_973.15,),
        predictor_scales=(3_276_259.848587155,),
        standardized_coefficients=(4_868_300.95, 3_608_978.2486053077),
        raw_unit_intercept=337_637.5345664583,
        raw_unit_coefficients=(1.101554337993561,),
        design_rank=2,
        residual_degrees_of_freedom=18,
        condition_number=1.0000000000000002,
        training_mae_krw_million=766_793.9968575586,
        training_rmse_krw_million=1_081_782.5124146359,
        historical_benchmark_mae_krw_million=1_677_703.75,
        historical_selected_candidate_mae_krw_million=1_249_345.1117558964,
        historical_relative_mae_improvement=0.25532436119553503,
    )


def _feature(selected: FrozenSelectedEstimatorFullFit) -> FrozenProspectiveFeatureVector:
    return FrozenProspectiveFeatureVector(
        evidence_id="b" * 64,
        contract_evidence_id="c" * 64,
        protocol_evidence_id="d" * 64,
        selected_estimator_evidence_id=selected.evidence_id,
        historical_execution_evidence_id=selected.execution_evidence_id,
        source_capture_evidence_id="e" * 64,
        target_period="2026Q3",
        source_period="2026Q2",
        forecast_origin=datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
        frozen_at=datetime(2026, 8, 22, 16, 4, 11, tzinfo=_KST),
        source_receipt_no="20260814003509",
        source_receipt_date=datetime(2026, 8, 14, tzinfo=_KST).date(),
        source_available_at=datetime(2026, 8, 14, 23, 59, 59, tzinfo=_KST),
        source_raw_payload_sha256="f" * 64,
        source_captured_payload_bytes_sha256="0" * 64,
        predictors=selected.predictors,
        feature_values=(65_991_356.0,),
    )


def test_numeric_forecast_replays_frozen_model_and_feature() -> None:
    contract = load_numeric_forecast_contract()
    selected = _selected()
    feature = _feature(selected)
    item = build_locked_numeric_forecast(
        contract,
        selected,
        feature,
        forecast_locked_at=datetime(2026, 8, 22, 16, 10, tzinfo=_KST),
    )
    assert item.selected_forecast_krw_million == pytest.approx(73_030_702.00644387)
    assert item.benchmark_forecast_krw_million == 65_991_356.0
    assert item.prediction_interval is None
    assert item.prospective_forecast_run is True
    assert item.numeric_forward_forecast_enabled is True
    assert item.q3_target_read is False
    assert item.q3_source_outcome_loaded is False
    assert item.q3_evaluated is False


def test_numeric_forecast_rejects_first_lock_after_origin() -> None:
    contract = load_numeric_forecast_contract()
    selected = _selected()
    feature = _feature(selected)
    with pytest.raises(ValueError, match="origin was missed"):
        build_locked_numeric_forecast(
            contract,
            selected,
            feature,
            forecast_locked_at=datetime(2026, 9, 1, 0, 0, tzinfo=_KST),
        )


def test_numeric_forecast_crosschecks_raw_and_standardized_representations() -> None:
    contract = load_numeric_forecast_contract()
    selected = replace(_selected(), raw_unit_coefficients=(1.2,))
    feature = _feature(selected)
    with pytest.raises(ValueError, match="representations disagree"):
        build_locked_numeric_forecast(
            contract,
            selected,
            feature,
            forecast_locked_at=datetime(2026, 8, 22, 16, 10, tzinfo=_KST),
        )


def test_numeric_forecast_persistence_is_content_addressed(tmp_path: Path) -> None:
    contract = load_numeric_forecast_contract()
    selected = _selected()
    feature = _feature(selected)
    item = build_locked_numeric_forecast(
        contract,
        selected,
        feature,
        forecast_locked_at=datetime(2026, 8, 22, 16, 10, tzinfo=_KST),
    )
    pointer = persist_locked_numeric_forecast(item, output=tmp_path)
    replayed = load_locked_numeric_forecast(pointer)
    assert replayed == item
    assert (tmp_path / f"numeric-forecast-{item.evidence_id}.json").is_file()
