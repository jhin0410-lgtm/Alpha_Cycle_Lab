from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_view_v2_1 import (
    DecisionViewSelectionMethod,
    build_decision_expectation_gap,
    build_decision_view,
    build_decision_view_selection_rule,
    persist_decision_expectation_gap,
    persist_decision_view,
    persist_decision_view_selection_rule,
)
from alpha_cycle.intelligence.expectation_state import (
    ExpectationKind,
    ExpectationMetric,
)
from alpha_cycle.intelligence.forecast_ledger import (
    ForecasterKind,
    ForecastRegistrationMode,
    ForecastRegistrationSnapshot,
    OrdinalAssessment,
    PrimaryErrorMetric,
)
from alpha_cycle.intelligence.price_implied_requirement import (
    PriceImpliedRequirementStatus,
    ReferenceFrameKind,
)

_KST = ZoneInfo("Asia/Seoul")
_GUARDRAILS = load_decision_system_v21_guardrails()
_A = "a" * 64
_B = "b" * 64
_C = "c" * 64
_D = "d" * 64


def _forecast(
    forecast_id: str,
    *,
    model_family: str,
    cluster: str,
    value: float,
) -> ForecastRegistrationSnapshot:
    return ForecastRegistrationSnapshot(
        forecast_id=forecast_id,
        registered_at=datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        ledger_recorded_at=datetime(2026, 8, 22, 17, 5, tzinfo=_KST),
        forecast_origin=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
        information_cutoff=datetime(2026, 8, 22, 16, 0, tzinfo=_KST),
        security_id="000660",
        target_variable="net_income",
        target_date=date(2026, 12, 31),
        horizon_label="FY2026",
        forecast_value=value,
        unit="KRW_million",
        range_lower=None,
        range_upper=None,
        direction=None,
        direction_reference_value=None,
        direction_flat_tolerance=0.0,
        confidence=OrdinalAssessment.MEDIUM,
        confidence_rationale="Prospective estimate with explicit model uncertainty.",
        forecaster_kind=ForecasterKind.MODEL,
        model_family=model_family,
        driver_refs=("driver:memory-cycle",),
        regime_tags=("memory-upcycle",),
        decision_relevance=OrdinalAssessment.HIGH,
        difficulty=OrdinalAssessment.HIGH,
        baseline_refs=(),
        dependency_cluster_id=cluster,
        source_evidence_ids=(_A,),
        registration_mode=ForecastRegistrationMode.NATIVE_PROSPECTIVE,
        primary_error_metric=PrimaryErrorMetric.ABSOLUTE_ERROR,
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
    )


def _rule(*, registered_at: datetime | None = None):
    return build_decision_view_selection_rule(
        rule_id="000660-fy2026-net-income-primary-view",
        registered_at=registered_at
        or datetime(2026, 8, 22, 15, 30, tzinfo=_KST),
        security_id="000660",
        target_variable="net_income",
        target_date=date(2026, 12, 31),
        unit="KRW_million",
        selected_forecaster_kind=ForecasterKind.MODEL,
        selected_model_family="model-a",
        rationale="Primary identity was chosen before forecast values were registered.",
        source_evidence_ids=(_B,),
    )


def _view(*, shared_cluster: bool = False):
    first = _forecast(
        "model-a-fy2026",
        model_family="model-a",
        cluster="shared" if shared_cluster else "cluster-a",
        value=22_000_000.0,
    )
    second = _forecast(
        "model-b-fy2026",
        model_family="model-b",
        cluster="shared" if shared_cluster else "cluster-b",
        value=20_000_000.0,
    )
    return build_decision_view(
        _rule(),
        (first, second),
        captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
    )


def _expectations():
    first = SimpleNamespace(
        provider_id="provider-a",
        source_evidence_id=_A,
        observed_at=datetime(2026, 8, 22, 17, 30, tzinfo=_KST),
        security_id="000660",
        metric=ExpectationMetric.NET_INCOME,
        target_period_end=date(2026, 12, 31),
        unit="KRW_million",
        expectation_kind=ExpectationKind.MARKET_CONSENSUS,
        market_consensus_certified=True,
        value=20_000_000.0,
    )
    second = SimpleNamespace(
        provider_id="provider-b",
        source_evidence_id=_B,
        observed_at=datetime(2026, 8, 22, 17, 35, tzinfo=_KST),
        security_id="000660",
        metric=ExpectationMetric.NET_INCOME,
        target_period_end=date(2026, 12, 31),
        unit="KRW_million",
        expectation_kind=ExpectationKind.MARKET_CONSENSUS,
        market_consensus_certified=True,
        value=21_000_000.0,
    )
    non_consensus = SimpleNamespace(
        provider_id="single-broker",
        source_evidence_id=_C,
        observed_at=datetime(2026, 8, 22, 17, 40, tzinfo=_KST),
        security_id="000660",
        metric=ExpectationMetric.NET_INCOME,
        target_period_end=date(2026, 12, 31),
        unit="KRW_million",
        expectation_kind=ExpectationKind.SINGLE_BROKER,
        market_consensus_certified=False,
        value=25_000_000.0,
    )
    return SimpleNamespace(
        evaluation_date=date(2026, 8, 22),
        captured_at=datetime(2026, 8, 22, 17, 45, tzinfo=_KST),
        observations=(first, second, non_consensus),
        snapshot_id=_D,
    )


def _price_implied():
    observations = (
        SimpleNamespace(
            status=PriceImpliedRequirementStatus.AVAILABLE,
            implied_metric=ExpectationMetric.NET_INCOME,
            target_period_end=date(2026, 12, 31),
            implied_value_krw=21_000_000_000_000.0,
            reference_id="forward-pe-10x",
            reference_kind=ReferenceFrameKind.EXPLICIT_SCENARIO_ASSUMPTION,
            reference_multiple=10.0,
        ),
        SimpleNamespace(
            status=PriceImpliedRequirementStatus.AVAILABLE,
            implied_metric=ExpectationMetric.NET_INCOME,
            target_period_end=date(2026, 12, 31),
            implied_value_krw=24_000_000_000_000.0,
            reference_id="forward-pe-12x",
            reference_kind=ReferenceFrameKind.EXPLICIT_SCENARIO_ASSUMPTION,
            reference_multiple=12.0,
        ),
    )
    return SimpleNamespace(
        evaluation_date=date(2026, 8, 22),
        captured_at=datetime(2026, 8, 22, 18, 5, tzinfo=_KST),
        security_id="000660",
        guardrail_evidence_id=_GUARDRAILS.evidence_id,
        observations=observations,
        snapshot_id=_C,
    )


def test_selection_rule_is_content_addressed_and_non_scoring() -> None:
    rule = _rule()
    assert rule.selection_method is DecisionViewSelectionMethod.PINNED_FORECASTER_IDENTITY
    assert len(rule.snapshot_id) == 64
    payload = rule.payload_without_id()
    assert payload["forecast_value_inspection_allowed_before_rule_registration"] is False
    assert payload["most_bullish_forecast_selection_enabled"] is False
    assert payload["automatic_ensemble_weighting_enabled"] is False


def test_decision_view_selects_only_preregistered_identity() -> None:
    view = _view()
    assert view.selected_forecast_id == "model-a-fy2026"
    assert view.selected_forecast_value == 22_000_000.0
    assert view.tournament_dependency_overlap is False
    payload = view.payload_without_id()
    assert payload["ex_post_forecast_value_selection_enabled"] is False
    assert payload["market_consensus_claimed"] is False
    assert payload["target_price_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_decision_view_rejects_rule_after_or_at_forecast_registration() -> None:
    forecasts = (
        _forecast(
            "model-a-fy2026",
            model_family="model-a",
            cluster="cluster-a",
            value=22_000_000.0,
        ),
        _forecast(
            "model-b-fy2026",
            model_family="model-b",
            cluster="cluster-b",
            value=20_000_000.0,
        ),
    )
    for timestamp in (
        datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        datetime(2026, 8, 22, 17, 1, tzinfo=_KST),
    ):
        with pytest.raises(ValueError, match="registered before forecast values"):
            build_decision_view(
                _rule(registered_at=timestamp),
                forecasts,
                captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
                evaluation_date=date(2026, 8, 22),
            )


def test_tournament_blocks_duplicate_forecaster_identity_before_view_selection() -> None:
    forecasts = (
        _forecast(
            "model-a-1",
            model_family="model-a",
            cluster="cluster-a",
            value=22_000_000.0,
        ),
        _forecast(
            "model-a-2",
            model_family="model-a",
            cluster="cluster-b",
            value=21_500_000.0,
        ),
    )
    with pytest.raises(ValueError, match="forecast_tournament_requires_distinct_forecasters"):
        build_decision_view(
            _rule(),
            forecasts,
            captured_at=datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
            evaluation_date=date(2026, 8, 22),
        )


def test_expectation_gap_preserves_providers_and_price_references() -> None:
    result = build_decision_expectation_gap(
        _view(),
        _expectations(),  # type: ignore[arg-type]
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        price_implied=_price_implied(),  # type: ignore[arg-type]
    )
    assert [item.provider_id for item in result.consensus_gaps] == [
        "provider-a",
        "provider-b",
    ]
    assert result.consensus_gaps[0].absolute_gap == 2_000_000.0
    assert result.consensus_gaps[1].absolute_gap == 1_000_000.0
    assert [item.reference_id for item in result.price_implied_gaps] == [
        "forward-pe-10x",
        "forward-pe-12x",
    ]
    assert result.price_implied_gaps[0].decision_value_krw == 22_000_000_000_000.0
    assert result.price_implied_gaps[0].absolute_gap_krw == 1_000_000_000_000.0
    assert result.price_implied_gaps[1].absolute_gap_krw == -2_000_000_000_000.0
    payload = result.payload_without_id()
    assert payload["consensus_provider_aggregation_enabled"] is False
    assert payload["price_reference_aggregation_enabled"] is False
    assert payload["price_implied_market_expectation_claimed"] is False
    assert payload["decision_score_enabled"] is False
    assert payload["target_price_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_expectation_gap_requires_certified_consensus() -> None:
    expectations = _expectations()
    for observation in expectations.observations:
        observation.market_consensus_certified = False
    with pytest.raises(ValueError, match="no certified market consensus"):
        build_decision_expectation_gap(
            _view(),
            expectations,  # type: ignore[arg-type]
            captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
            evaluation_date=date(2026, 8, 22),
        )


def test_dependency_overlap_is_preserved_as_flag() -> None:
    result = build_decision_expectation_gap(
        _view(shared_cluster=True),
        _expectations(),  # type: ignore[arg-type]
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
    )
    assert "decision_view_tournament_dependency_overlap" in result.flags
    assert "price_implied_comparison_not_supplied" in result.flags


def test_decision_view_artifacts_persist_immutably(tmp_path) -> None:
    rule = _rule()
    view = _view()
    gap = build_decision_expectation_gap(
        view,
        _expectations(),  # type: ignore[arg-type]
        captured_at=datetime(2026, 8, 22, 18, 20, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        price_implied=_price_implied(),  # type: ignore[arg-type]
    )
    pointers = (
        (persist_decision_view_selection_rule(rule, output_root=tmp_path), rule.snapshot_id),
        (persist_decision_view(view, output_root=tmp_path), view.snapshot_id),
        (persist_decision_expectation_gap(gap, output_root=tmp_path), gap.snapshot_id),
    )
    for pointer, expected_id in pointers:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        assert payload["snapshot_id"] == expected_id
        snapshot_dir = tmp_path / payload["object_type"] / Path(payload["snapshot_path"]).name
        manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["immutable"] is True
        assert manifest["decision_score_enabled"] is False
        assert manifest["target_price_enabled"] is False
        assert manifest["automatic_execution_enabled"] is False
