from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.forecast_ledger import (
    DiagnosticAvailability,
    ForecasterKind,
    ForecastRegistrationMode,
    OrdinalAssessment,
    PrimaryErrorMetric,
    build_forecast_evaluation,
    build_forecast_outcome,
    build_forecast_registration,
    persist_forecast_evaluation,
    persist_forecast_outcome,
    persist_forecast_registration,
    summarize_forecast_dependencies,
)

_KST = ZoneInfo("Asia/Seoul")
_FORECAST_EVIDENCE = "1fd34ba0f43bc2fbc296a6823f2f313296955d8a3860994b7757eb6e23dad468"
_FEATURE_EVIDENCE = "139d50940b27582dbaa9206989439c7b9253d75d65e12e45bcb7a14512214bda"
_ESTIMATOR_EVIDENCE = "4ddf0e7206fcbb6a58ba2e7fcb93b48bf79195171dfc96a894481dbfa612a2d1"
_OUTCOME_EVIDENCE = "d" * 64


def _registration(**overrides: object):
    values: dict[str, object] = {
        "forecast_id": "generic-test-forecast",
        "registered_at": datetime(2026, 8, 22, 16, 52, tzinfo=_KST),
        "ledger_recorded_at": datetime(2026, 8, 22, 17, 30, tzinfo=_KST),
        "forecast_origin": datetime(2026, 8, 31, 23, 59, 59, tzinfo=_KST),
        "information_cutoff": datetime(2026, 8, 22, 16, 4, tzinfo=_KST),
        "security_id": "000660",
        "target_variable": "company_gross_profit_krw_million",
        "target_date": date(2026, 9, 30),
        "horizon_label": "2026Q3",
        "forecast_value": 73_030_702.00644387,
        "unit": "KRW_million",
        "range_lower": None,
        "range_upper": None,
        "direction": None,
        "direction_reference_value": None,
        "direction_flat_tolerance": 0.0,
        "confidence": OrdinalAssessment.LOW,
        "confidence_rationale": (
            "The frozen forecast is valid but the prospective input is extremely OOD."
        ),
        "forecaster_kind": ForecasterKind.MODEL,
        "model_family": "lagged_gp_affine_ols",
        "driver_refs": ("lagged_company_gross_profit",),
        "regime_tags": ("memory-upcycle", "extreme-scale-shift"),
        "decision_relevance": OrdinalAssessment.HIGH,
        "difficulty": OrdinalAssessment.HIGH,
        "baseline_refs": (),
        "dependency_cluster_id": "SKHYNIX_MEMORY_EARNINGS_2026Q3",
        "source_evidence_ids": (
            _FORECAST_EVIDENCE,
            _FEATURE_EVIDENCE,
            _ESTIMATOR_EVIDENCE,
        ),
        "registration_mode": ForecastRegistrationMode.EXTERNAL_FROZEN_REFERENCE,
        "primary_error_metric": PrimaryErrorMetric.ABSOLUTE_ERROR,
    }
    values.update(overrides)
    return build_forecast_registration(**values)


def _outcome(registration, *, actual: float = 70_000_000.0):
    return build_forecast_outcome(
        registration,
        captured_at=datetime(2026, 11, 1, 10, 5, tzinfo=_KST),
        outcome_observed_at=datetime(2026, 11, 1, 10, 0, tzinfo=_KST),
        actual_value=actual,
        source_evidence_ids=(_OUTCOME_EVIDENCE,),
    )


def test_locked_skhynix_q3_forecast_can_be_referenced_without_rewriting_it() -> None:
    registration = _registration(
        forecast_id="skhynix-company-gp-2026q3-selected",
        registered_at=datetime(2026, 8, 22, 16, 52, 7, 618525, tzinfo=_KST),
        ledger_recorded_at=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
        information_cutoff=datetime(2026, 8, 22, 16, 4, 11, 189026, tzinfo=_KST),
    )
    assert registration.forecast_value == 73_030_702.00644387
    assert registration.source_evidence_ids[0] == _FORECAST_EVIDENCE
    assert registration.registration_mode is ForecastRegistrationMode.EXTERNAL_FROZEN_REFERENCE
    payload = registration.payload_without_id()
    assert payload["outcome_observed"] is False
    assert payload["evaluation_run"] is False
    assert payload["order_api_enabled"] is False


def test_external_import_records_original_freeze_and_later_ledger_time_separately() -> None:
    registration = _registration(
        ledger_recorded_at=datetime(2026, 9, 5, 12, 0, tzinfo=_KST),
    )
    assert registration.registered_at < registration.forecast_origin
    assert registration.ledger_recorded_at > registration.forecast_origin
    assert registration.registration_mode is ForecastRegistrationMode.EXTERNAL_FROZEN_REFERENCE


def test_native_registration_cannot_be_written_after_forecast_origin() -> None:
    with pytest.raises(ValueError, match="native ledger registration cannot occur after"):
        _registration(
            registration_mode=ForecastRegistrationMode.NATIVE_PROSPECTIVE,
            ledger_recorded_at=datetime(2026, 9, 1, 0, 1, tzinfo=_KST),
        )


def test_information_cutoff_and_registration_must_be_prospective() -> None:
    with pytest.raises(ValueError, match="information_cutoff"):
        _registration(
            information_cutoff=datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        )
    with pytest.raises(ValueError, match="no later than forecast_origin"):
        _registration(
            registered_at=datetime(2026, 9, 1, 0, 0, tzinfo=_KST),
            ledger_recorded_at=datetime(2026, 9, 1, 0, 0, tzinfo=_KST),
        )


def test_selected_and_persistence_forecasts_share_one_dependency_cluster() -> None:
    benchmark = _registration(
        forecast_id="skhynix-company-gp-2026q3-persistence",
        forecast_value=65_991_356.0,
        forecaster_kind=ForecasterKind.BENCHMARK,
        model_family="previous_reported_quarter_gross_profit_persistence",
        source_evidence_ids=(_FORECAST_EVIDENCE, _FEATURE_EVIDENCE),
    )
    selected = _registration(
        forecast_id="skhynix-company-gp-2026q3-selected",
        baseline_refs=(benchmark.snapshot_id,),
    )
    summary = summarize_forecast_dependencies((selected, benchmark))
    assert summary.raw_forecast_count == 2
    assert summary.independent_dependency_cluster_count == 1
    assert summary.cluster_counts == (("SKHYNIX_MEMORY_EARNINGS_2026Q3", 2),)
    assert summary.payload()["statistical_effective_sample_size_claimed"] is False


def test_outcome_is_separate_and_cannot_precede_target_date() -> None:
    registration = _registration()
    original_id = registration.snapshot_id
    outcome = _outcome(registration)
    assert outcome.registration_snapshot_id == original_id
    assert registration.snapshot_id == original_id
    assert outcome.snapshot_id != registration.snapshot_id
    with pytest.raises(ValueError, match="before target_date"):
        build_forecast_outcome(
            registration,
            captured_at=datetime(2026, 9, 20, 10, 5, tzinfo=_KST),
            outcome_observed_at=datetime(2026, 9, 20, 10, 0, tzinfo=_KST),
            actual_value=70_000_000.0,
            source_evidence_ids=(_OUTCOME_EVIDENCE,),
        )


def test_evaluation_computes_accuracy_without_composite_score() -> None:
    registration = _registration()
    outcome = _outcome(registration)
    evaluation = build_forecast_evaluation(
        registration,
        outcome,
        evaluated_at=datetime(2026, 11, 1, 10, 10, tzinfo=_KST),
    )
    expected_signed = registration.forecast_value - outcome.actual_value
    assert evaluation.accuracy.signed_error == pytest.approx(expected_signed)
    assert evaluation.accuracy.absolute_error == pytest.approx(abs(expected_signed))
    assert evaluation.primary_error_value == pytest.approx(abs(expected_signed))
    assert evaluation.calibration is DiagnosticAvailability.NOT_ESTIMABLE_SINGLE_FORECAST
    assert evaluation.information_gain is DiagnosticAvailability.NOT_EVALUATED_WITHOUT_BASELINE
    payload = evaluation.payload_without_id()
    assert payload["composite_forecast_score_enabled"] is False
    assert payload["composite_forecast_score"] is None


def test_baseline_information_gain_is_same_outcome_absolute_error_advantage() -> None:
    benchmark = _registration(
        forecast_id="benchmark",
        forecast_value=65_991_356.0,
        forecaster_kind=ForecasterKind.BENCHMARK,
        model_family="persistence",
    )
    selected = _registration(
        forecast_id="selected",
        baseline_refs=(benchmark.snapshot_id,),
    )
    selected_outcome = _outcome(selected)
    benchmark_outcome = replace(
        selected_outcome,
        registration_snapshot_id=benchmark.snapshot_id,
    )
    benchmark_eval = build_forecast_evaluation(
        benchmark,
        benchmark_outcome,
        evaluated_at=datetime(2026, 11, 1, 10, 10, tzinfo=_KST),
    )
    selected_eval = build_forecast_evaluation(
        selected,
        selected_outcome,
        evaluated_at=datetime(2026, 11, 1, 10, 11, tzinfo=_KST),
        baseline_evaluation=benchmark_eval,
    )
    expected = benchmark_eval.accuracy.absolute_error - selected_eval.accuracy.absolute_error
    assert selected_eval.absolute_error_advantage_vs_baseline == pytest.approx(expected)
    assert selected_eval.information_gain is DiagnosticAvailability.OBSERVED
    assert selected_eval.baseline_evaluation_refs == (benchmark_eval.snapshot_id,)


def test_primary_ape_fails_closed_when_actual_is_zero() -> None:
    registration = _registration(
        primary_error_metric=PrimaryErrorMetric.ABSOLUTE_PERCENTAGE_ERROR,
    )
    outcome = _outcome(registration, actual=0.0)
    with pytest.raises(ValueError, match="undefined when actual value is zero"):
        build_forecast_evaluation(
            registration,
            outcome,
            evaluated_at=datetime(2026, 11, 1, 10, 10, tzinfo=_KST),
        )


def test_persistence_keeps_registration_outcome_and_evaluation_in_separate_roots(
    tmp_path: Path,
) -> None:
    registration = _registration()
    outcome = _outcome(registration)
    evaluation = build_forecast_evaluation(
        registration,
        outcome,
        evaluated_at=datetime(2026, 11, 1, 10, 10, tzinfo=_KST),
    )

    registration_pointer = persist_forecast_registration(
        registration,
        output_root=tmp_path,
    )
    outcome_pointer = persist_forecast_outcome(outcome, output_root=tmp_path)
    evaluation_pointer = persist_forecast_evaluation(evaluation, output_root=tmp_path)

    assert registration_pointer.parent.name == "registration"
    assert outcome_pointer.parent.name == "outcome"
    assert evaluation_pointer.parent.name == "evaluation"

    registration_ref = json.loads(registration_pointer.read_text(encoding="utf-8"))
    registration_dir = Path(registration_ref["snapshot_path"])
    manifest = json.loads((registration_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == registration.snapshot_id
    assert manifest["outcome_observed"] is False
    assert manifest["evaluation_run"] is False
    assert manifest["order_api_enabled"] is False
