from __future__ import annotations

from datetime import UTC, datetime

import pytest

from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_capture import (
    capture_prospective_source_bytes,
    load_prospective_capture_ledger,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_feature_frontier import (
    load_ex_ante_feature_frontier,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_pit import (
    PointInTimeFeatureBundle,
    PointInTimeFeatureObservation,
    audit_point_in_time_feature_bundle,
)
from alpha_cycle.intelligence.sk_hynix_company_gp_ex_ante_protocol import (
    load_frozen_company_gp_ex_ante_protocol,
)


def _observation(
    *,
    feature_id: str = "lagged_company_gross_profit",
    provenance_class: str = "timestamped_immutable_filing",
    available_at: datetime = datetime(2025, 8, 1, tzinfo=UTC),
    captured_at: datetime | None = None,
    target_metric_in_payload: bool = False,
) -> PointInTimeFeatureObservation:
    return PointInTimeFeatureObservation(
        period_id="2025Q3",
        feature_id=feature_id,
        value=1_234_567.0,
        provenance_class=provenance_class,
        source_available_at=available_at,
        source_bytes_sha256="a" * 64,
        source_evidence_id="b" * 64,
        source_version_identity="receipt:20250731000001",
        direct_source_fact=True,
        deterministic_transform=False,
        target_metric_in_payload=target_metric_in_payload,
        captured_at=captured_at,
    )


def test_ex_ante_protocol_binds_v5_and_protects_q3() -> None:
    protocol = load_frozen_company_gp_ex_ante_protocol()

    assert protocol.protocol_version == "1.0-frozen-pre-pit-backtest"
    assert protocol.origin_for("2026Q3").isoformat() == "2026-08-31T23:59:59+09:00"
    assert protocol.origin_for("2026Q4").isoformat() == "2026-12-01T23:59:59+09:00"
    assert not protocol.q3_target_read
    assert not protocol.q3_source_outcome_loaded
    assert not protocol.q3_evaluated
    assert not protocol.numeric_forward_forecast_enabled


def test_feature_frontier_does_not_preclaim_historical_pit() -> None:
    frontier = load_ex_ante_feature_frontier()

    assert frontier.features
    assert not any(item.historical_pit_fit_eligible_now for item in frontier.features)
    memory = frontier.by_id()["memory_price_proxy"]
    assert not memory.prospective_capture_eligible
    assert memory.acceptable_provenance_classes == ()
    assert "current_quarter_company_gross_profit_actual" in frontier.forbidden_features


def test_pit_audit_accepts_timed_immutable_feature_without_target() -> None:
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()
    bundle = PointInTimeFeatureBundle(
        evidence_id="c" * 64,
        created_at=datetime(2026, 8, 18, tzinfo=UTC),
        observations=(_observation(),),
    )

    result = audit_point_in_time_feature_bundle(protocol, frontier, bundle)

    assert result.eligible_observation_count == 1
    assert result.rejected_observation_count == 0
    assert result.all_observations_point_in_time_eligible
    assert not result.target_join_allowed
    assert not result.estimator_fit_allowed
    assert not result.first_pit_backtest_run


def test_pit_audit_rejects_current_retrieval_and_target_leakage() -> None:
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()
    bundle = PointInTimeFeatureBundle(
        evidence_id="d" * 64,
        created_at=datetime(2026, 8, 18, tzinfo=UTC),
        observations=(
            _observation(
                provenance_class="current_retrieval_only",
                target_metric_in_payload=True,
            ),
        ),
    )

    result = audit_point_in_time_feature_bundle(protocol, frontier, bundle)

    assert result.rejected_observation_count == 1
    reasons = set(result.observation_audits[0].reasons)
    assert "current_retrieval_only_is_not_historical_pit_proof" in reasons
    assert "target_metric_present_in_feature_payload" in reasons


def test_prospective_capture_is_hash_chained_and_origin_bounded(tmp_path) -> None:
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()
    available = datetime(2026, 8, 18, 0, 0, tzinfo=UTC)
    captured = datetime(2026, 8, 18, 1, 0, tzinfo=UTC)

    first, reused = capture_prospective_source_bytes(
        protocol,
        frontier,
        period_id="2026Q3",
        feature_id="usdkrw_partial_quarter",
        source_id="ecos:test-series",
        source_available_at=available,
        raw_bytes=b"first-source-payload",
        observation_reference="2026Q3 partial-quarter FX snapshot",
        output_root=tmp_path,
        now=lambda: captured,
    )
    assert not reused
    assert first.sequence == 1
    assert first.eligible_for_frozen_origin

    repeated, reused_again = capture_prospective_source_bytes(
        protocol,
        frontier,
        period_id="2026Q3",
        feature_id="usdkrw_partial_quarter",
        source_id="ecos:test-series",
        source_available_at=available,
        raw_bytes=b"first-source-payload",
        observation_reference="2026Q3 partial-quarter FX snapshot",
        output_root=tmp_path,
        now=lambda: captured,
    )
    assert reused_again
    assert repeated.evidence_id == first.evidence_id

    second, reused_second = capture_prospective_source_bytes(
        protocol,
        frontier,
        period_id="2026Q3",
        feature_id="usdkrw_partial_quarter",
        source_id="ecos:test-series",
        source_available_at=available,
        raw_bytes=b"second-source-payload",
        observation_reference="2026Q3 revised capture before origin",
        output_root=tmp_path,
        now=lambda: captured,
    )
    assert not reused_second
    assert second.sequence == 2
    assert second.previous_receipt_evidence_id == first.evidence_id

    ledger = load_prospective_capture_ledger(
        protocol,
        frontier,
        output_root=tmp_path,
    )
    assert len(ledger.receipts) == 2

    blob_path = tmp_path / second.archive_relative_path
    blob_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="blob SHA-256 mismatch"):
        load_prospective_capture_ledger(
            protocol,
            frontier,
            output_root=tmp_path,
        )


def test_unresolved_memory_price_source_cannot_be_prospectively_captured(tmp_path) -> None:
    protocol = load_frozen_company_gp_ex_ante_protocol()
    frontier = load_ex_ante_feature_frontier()

    with pytest.raises(ValueError, match="not prospective-capture eligible"):
        capture_prospective_source_bytes(
            protocol,
            frontier,
            period_id="2026Q3",
            feature_id="memory_price_proxy",
            source_id="unresolved",
            source_available_at=datetime(2026, 8, 18, tzinfo=UTC),
            raw_bytes=b"not-allowed",
            observation_reference="unresolved price source",
            output_root=tmp_path,
            now=lambda: datetime(2026, 8, 18, 1, tzinfo=UTC),
        )
