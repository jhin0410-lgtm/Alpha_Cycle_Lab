from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.expectation_gap_contract import ExpectationSemantics
from alpha_cycle.intelligence.expectation_gap_decision_evidence import kis_expectation_semantics
from alpha_cycle.intelligence.expectation_state import (
    CertifiedExpectationObservation,
    ExpectationKind,
    ExpectationMetric,
    ExpectationStateSnapshot,
    build_expectation_revisions,
    persist_expectation_state,
)

_KST = ZoneInfo("Asia/Seoul")


def _semantics(*, prior_available: bool = False) -> ExpectationSemantics:
    return ExpectationSemantics(
        provider_id="certified_market_estimates",
        provider_semantics_certified=True,
        target_period_semantics_certified=True,
        metric_semantics_certified=True,
        aggregation_semantics_certified=True,
        observation_timestamp_certified=True,
        provider_vintage_certified=True,
        comparable_prior_snapshot_available=prior_available,
        comparable_snapshot_scope_certified=True,
        revision_calculation_certified=True,
        numeric_evidence_available=True,
        source_scope="documented PIT multi-analyst expectation source",
    )


def _observation(
    *,
    value: float = 100.0,
    observed_at: datetime | None = None,
    semantics: ExpectationSemantics | None = None,
    kind: ExpectationKind = ExpectationKind.MARKET_CONSENSUS,
    consensus_certified: bool = True,
    producer_identity: str | None = None,
) -> CertifiedExpectationObservation:
    return CertifiedExpectationObservation(
        security_id="000660",
        metric=ExpectationMetric.OPERATING_INCOME,
        target_period="FY2026",
        target_period_end=date(2026, 12, 31),
        expectation_kind=kind,
        value=value,
        unit="KRW_million",
        observed_at=observed_at or datetime(2026, 8, 22, 16, 0, tzinfo=_KST),
        source_evidence_id="a" * 64,
        semantics=semantics or _semantics(),
        market_consensus_certified=consensus_certified,
        producer_identity=producer_identity,
        aggregation_method="mean" if kind is ExpectationKind.MARKET_CONSENSUS else "not_applicable",
        sample_count=18 if kind is ExpectationKind.MARKET_CONSENSUS else None,
        dispersion=7.5 if kind is ExpectationKind.MARKET_CONSENSUS else None,
    )


def _snapshot(
    observation: CertifiedExpectationObservation,
    *,
    captured_at: datetime | None = None,
    evaluation_date: date | None = None,
) -> ExpectationStateSnapshot:
    return ExpectationStateSnapshot(
        captured_at=captured_at or datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        evaluation_date=evaluation_date or date(2026, 8, 22),
        observations=(observation,),
        source_snapshot_ids=("b" * 64,),
    )


def test_certified_consensus_level_is_accepted() -> None:
    observation = _observation()
    assert observation.level_readiness.numeric_level_enabled
    assert observation.market_consensus_certified
    assert observation.expectation_kind is ExpectationKind.MARKET_CONSENSUS


def test_market_consensus_label_requires_independent_certification() -> None:
    with pytest.raises(ValueError, match="market_consensus label requires"):
        _observation(consensus_certified=False)


def test_single_broker_requires_producer_identity() -> None:
    with pytest.raises(ValueError, match="producer_identity"):
        _observation(
            kind=ExpectationKind.SINGLE_BROKER,
            consensus_certified=False,
        )
    observation = _observation(
        kind=ExpectationKind.SINGLE_BROKER,
        consensus_certified=False,
        producer_identity="Broker A",
    )
    assert observation.producer_identity == "Broker A"


def test_current_kis_semantics_cannot_enter_numeric_expectation_state() -> None:
    semantics = kis_expectation_semantics(
        raw_artifact_available=True,
        prior_snapshot_available=True,
    )
    with pytest.raises(ValueError, match="numeric expectation level is blocked"):
        _observation(semantics=semantics, consensus_certified=False)


def test_snapshot_rejects_future_or_historical_leakage() -> None:
    observation = _observation(
        observed_at=datetime(2026, 8, 23, 9, 0, tzinfo=_KST),
    )
    with pytest.raises(ValueError, match="after snapshot capture"):
        _snapshot(observation)

    historical_target = replace(_observation(), target_period_end=date(2025, 12, 31))
    with pytest.raises(ValueError, match="target must not already be historical"):
        _snapshot(historical_target)


def test_snapshot_is_content_addressed_and_order_independent() -> None:
    operating = _observation()
    revenue = replace(
        operating,
        metric=ExpectationMetric.REVENUE,
        value=200.0,
        source_evidence_id="c" * 64,
    )
    first = ExpectationStateSnapshot(
        captured_at=datetime(2026, 8, 22, 17, 0, tzinfo=_KST),
        evaluation_date=date(2026, 8, 22),
        observations=(operating, revenue),
        source_snapshot_ids=("b" * 64, "d" * 64),
    )
    second = ExpectationStateSnapshot(
        captured_at=first.captured_at,
        evaluation_date=first.evaluation_date,
        observations=(revenue, operating),
        source_snapshot_ids=("d" * 64, "b" * 64),
    )
    assert first.snapshot_id == second.snapshot_id


def test_revision_requires_two_comparable_certified_vintages() -> None:
    prior_observation = _observation(
        value=90.0,
        observed_at=datetime(2026, 8, 15, 16, 0, tzinfo=_KST),
    )
    prior = _snapshot(
        prior_observation,
        captured_at=datetime(2026, 8, 15, 17, 0, tzinfo=_KST),
        evaluation_date=date(2026, 8, 15),
    )
    current = _snapshot(_observation(value=100.0))
    revisions = build_expectation_revisions(prior, current)
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision.absolute_change == 10.0
    assert revision.relative_change == pytest.approx(10.0 / 90.0)
    assert revision.revision_readiness.numeric_revision_enabled


def test_revision_stays_blocked_when_provider_vintage_is_not_certified() -> None:
    uncertified_vintage = replace(_semantics(), provider_vintage_certified=False)
    prior_observation = _observation(
        value=90.0,
        observed_at=datetime(2026, 8, 15, 16, 0, tzinfo=_KST),
        semantics=uncertified_vintage,
    )
    current_observation = _observation(value=100.0, semantics=uncertified_vintage)
    prior = _snapshot(
        prior_observation,
        captured_at=datetime(2026, 8, 15, 17, 0, tzinfo=_KST),
        evaluation_date=date(2026, 8, 15),
    )
    current = _snapshot(current_observation)
    assert build_expectation_revisions(prior, current) == ()


def test_semantic_or_aggregation_drift_prevents_revision() -> None:
    prior_observation = _observation(
        value=90.0,
        observed_at=datetime(2026, 8, 15, 16, 0, tzinfo=_KST),
    )
    prior = _snapshot(
        prior_observation,
        captured_at=datetime(2026, 8, 15, 17, 0, tzinfo=_KST),
        evaluation_date=date(2026, 8, 15),
    )
    current_observation = replace(_observation(), aggregation_method="median")
    current = _snapshot(current_observation)
    with pytest.raises(ValueError, match="aggregation-method drift"):
        build_expectation_revisions(prior, current)


def test_persistence_keeps_content_addressed_snapshot_and_latest_pointer(tmp_path: Path) -> None:
    snapshot = _snapshot(_observation())
    pointer = persist_expectation_state(snapshot, output_root=tmp_path)
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_payload["snapshot_id"] == snapshot.snapshot_id
    directory = Path(pointer_payload["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == snapshot.snapshot_id
    assert manifest["consensus_observation_count"] == 1
    assert manifest["order_api_enabled"] is False
    first_contents = (directory / "expectations.json").read_bytes()
    persist_expectation_state(snapshot, output_root=tmp_path)
    assert (directory / "expectations.json").read_bytes() == first_contents
