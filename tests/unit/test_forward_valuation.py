from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from alpha_cycle.intelligence.expectation_gap_contract import ExpectationSemantics
from alpha_cycle.intelligence.expectation_state import (
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
)
from alpha_cycle.intelligence.forward_valuation import (
    ForwardValuationMetric,
    ForwardValuationStatus,
    build_forward_valuation_state,
    persist_forward_valuation_state,
)
from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot

_KST = ZoneInfo("Asia/Seoul")


def _semantics(provider: str = "certified_consensus") -> ExpectationSemantics:
    return ExpectationSemantics(
        provider_id=provider,
        provider_semantics_certified=True,
        target_period_semantics_certified=True,
        metric_semantics_certified=True,
        aggregation_semantics_certified=True,
        observation_timestamp_certified=True,
        provider_vintage_certified=True,
        comparable_prior_snapshot_available=False,
        comparable_snapshot_scope_certified=True,
        revision_calculation_certified=True,
        numeric_evidence_available=True,
        source_scope="documented PIT estimate source",
    )


def _expectation(
    *,
    metric: ExpectationMetric = ExpectationMetric.NET_INCOME,
    value: float = 10_000.0,
    unit: str = "KRW_million",
    provider: str = "certified_consensus",
) -> CertifiedExpectationObservation:
    return CertifiedExpectationObservation(
        security_id="000660",
        metric=metric,
        target_period="FY2026",
        target_period_end=date(2026, 12, 31),
        expectation_kind=ExpectationKind.MARKET_CONSENSUS,
        value=value,
        unit=unit,
        observed_at=datetime(2026, 8, 22, 16, 0, tzinfo=_KST),
        source_evidence_id=("a" if provider == "certified_consensus" else "c") * 64,
        semantics=_semantics(provider),
        market_consensus_certified=True,
        aggregation_method="mean",
        sample_count=20,
    )


def _expectation_state(
    observations: tuple[CertifiedExpectationObservation, ...],
) -> ExpectationStateSnapshot:
    return ExpectationStateSnapshot(
        captured_at=datetime(2026, 8, 22, 16, 30, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        observations=observations,
        source_snapshot_ids=("d" * 64,),
    )


def _valuation(*, market_cap: float | None = 100_000_000_000.0, complete: bool = True) -> ValuationEvidenceSnapshot:
    metrics = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "market_cap_complete": complete,
                "market_cap": market_cap,
                "annual_net_income": 1.0,
                "annual_revenue": 1.0,
                "pe": 100_000_000_000.0 if complete else None,
                "ps": 100_000_000_000.0 if complete else None,
            }
        ]
    )
    return ValuationEvidenceSnapshot(
        captured_at=datetime(2026, 8, 22, 16, 45, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        research_snapshot_id="e" * 64,
        market_snapshot_id="f" * 64,
        history_years=5,
        shares=pd.DataFrame(),
        security_values=pd.DataFrame(),
        financial_history=pd.DataFrame(),
        valuation_metrics=metrics,
        raw_valuation={},
    )


def test_forward_pe_uses_certified_net_income_and_pit_market_cap() -> None:
    state = build_forward_valuation_state(
        _valuation(),
        _expectation_state((_expectation(),)),
    )
    observation = state.observations[0]
    assert observation.status is ForwardValuationStatus.AVAILABLE
    assert observation.valuation_metric is ForwardValuationMetric.FORWARD_PE
    assert observation.expectation_value_krw == 10_000_000_000.0
    assert observation.multiple == pytest.approx(10.0)


def test_forward_ps_uses_explicit_currency_unit_conversion() -> None:
    revenue = _expectation(
        metric=ExpectationMetric.REVENUE,
        value=50.0,
        unit="KRW_billion",
    )
    state = build_forward_valuation_state(_valuation(), _expectation_state((revenue,)))
    observation = state.observations[0]
    assert observation.valuation_metric is ForwardValuationMetric.FORWARD_PS
    assert observation.expectation_value_krw == 50_000_000_000.0
    assert observation.multiple == pytest.approx(2.0)


def test_missing_forward_metric_never_falls_back_to_trailing_actual() -> None:
    operating_income = _expectation(metric=ExpectationMetric.OPERATING_INCOME)
    state = build_forward_valuation_state(
        _valuation(),
        _expectation_state((operating_income,)),
    )
    observation = state.observations[0]
    assert observation.status is ForwardValuationStatus.UNSUPPORTED_EXPECTATION_METRIC
    assert observation.valuation_metric is None
    assert observation.multiple is None


def test_missing_complete_market_cap_keeps_forward_multiple_unavailable() -> None:
    state = build_forward_valuation_state(
        _valuation(market_cap=80_000_000_000.0, complete=False),
        _expectation_state((_expectation(),)),
    )
    observation = state.observations[0]
    assert observation.status is ForwardValuationStatus.MARKET_CAP_UNAVAILABLE
    assert observation.market_cap_krw is None
    assert observation.multiple is None


def test_non_positive_expected_net_income_does_not_create_pe() -> None:
    state = build_forward_valuation_state(
        _valuation(),
        _expectation_state((_expectation(value=-100.0),)),
    )
    observation = state.observations[0]
    assert observation.status is ForwardValuationStatus.NON_POSITIVE_EXPECTATION
    assert observation.multiple is None


def test_multiple_certified_providers_remain_separate_instead_of_silent_average() -> None:
    first = _expectation(value=10_000.0)
    second = _expectation(value=12_000.0, provider="second_consensus")
    state = build_forward_valuation_state(
        _valuation(),
        _expectation_state((first, second)),
    )
    assert len(state.observations) == 2
    by_provider = {item.expectation_provider_id: item for item in state.observations}
    assert by_provider["certified_consensus"].multiple == pytest.approx(10.0)
    assert by_provider["second_consensus"].multiple == pytest.approx(100.0 / 12.0)


def test_evaluation_date_mismatch_fails_closed() -> None:
    expectations = replace(
        _expectation_state((_expectation(),)),
        evaluation_date=date(2026, 8, 21),
    )
    with pytest.raises(ValueError, match="same evaluation date"):
        build_forward_valuation_state(_valuation(), expectations)


def test_unknown_unit_fails_instead_of_guessing_conversion() -> None:
    with pytest.raises(ValueError, match="unsupported expectation currency/unit"):
        build_forward_valuation_state(
            _valuation(),
            _expectation_state((_expectation(unit="KRW_100million"),)),
        )


def test_persistence_binds_both_source_snapshot_ids(tmp_path: Path) -> None:
    state = build_forward_valuation_state(
        _valuation(),
        _expectation_state((_expectation(),)),
    )
    pointer = persist_forward_valuation_state(state, output_root=tmp_path)
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    directory = Path(pointer_payload["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == state.snapshot_id
    assert manifest["valuation_evidence_snapshot_id"] == state.valuation_evidence_snapshot_id
    assert manifest["expectation_state_snapshot_id"] == state.expectation_state_snapshot_id
    assert manifest["available_multiple_count"] == 1
    assert manifest["fair_value_enabled"] is False
    assert manifest["target_price_enabled"] is False
    assert manifest["order_api_enabled"] is False
