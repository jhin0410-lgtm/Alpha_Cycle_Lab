from __future__ import annotations

from datetime import date

import pytest

from alpha_cycle.intelligence.catalyst_horizon import (
    build_catalyst_event,
    build_catalyst_horizon_evidence,
)

EVALUATION = date(2026, 8, 14)


def _event(event_date: str, **overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "ticker": "000660",
        "sector_id": "semiconductor",
        "title": "Certified future event",
        "description": "Source-bounded future catalyst timing.",
        "source_role": "issuer_ir",
        "source_url": "https://news.skhynix.com/example",
        "source_published_date": "2026-08-01",
        "event_date": event_date,
        "timing_status": "certified_date",
        "prerequisite_status": "pending",
        "prerequisite": "Customer qualification must complete.",
        "market_pricing_status": "unknown",
        "surprise_potential": "unknown",
        "binary_event": False,
        "thesis_invalidation_if_failed": "Qualification failure would weaken the product-cycle thesis.",
    }
    raw.update(overrides)
    return raw


def test_catalyst_horizon_buckets_use_future_certified_timing_only() -> None:
    assert build_catalyst_event(_event("2026-09-14"), evaluation_date=EVALUATION).horizon_bucket == "1m"
    assert build_catalyst_event(_event("2026-11-14"), evaluation_date=EVALUATION).horizon_bucket == "3m"
    assert build_catalyst_event(_event("2027-02-14"), evaluation_date=EVALUATION).horizon_bucket == "6m"
    assert build_catalyst_event(_event("2027-08-14"), evaluation_date=EVALUATION).horizon_bucket == "12m"
    assert build_catalyst_event(_event("2027-09-01"), evaluation_date=EVALUATION).horizon_bucket == "beyond_12m"


def test_past_disclosure_cannot_be_relabelled_as_future_catalyst() -> None:
    event = build_catalyst_event(_event("2026-08-01"), evaluation_date=EVALUATION)
    assert event.horizon_days is not None and event.horizon_days < 0
    assert event.horizon_bucket == "past_not_future"


def test_uncertified_timing_cannot_publish_a_date() -> None:
    raw = _event("2026-09-01", timing_status="uncertified")
    with pytest.raises(ValueError, match="uncertified catalyst timing"):
        build_catalyst_event(raw, evaluation_date=EVALUATION)


def test_certified_window_uses_window_start_for_horizon_and_validates_order() -> None:
    raw = _event(
        "",
        timing_status="certified_window",
        window_start="2026-10-01",
        window_end="2026-10-31",
    )
    event = build_catalyst_event(raw, evaluation_date=EVALUATION)
    assert event.event_date is None
    assert event.horizon_bucket == "3m"

    bad = {**raw, "window_start": "2026-11-01", "window_end": "2026-10-01"}
    with pytest.raises(ValueError, match="window_start"):
        build_catalyst_event(bad, evaluation_date=EVALUATION)


def test_bundle_preserves_binary_prerequisite_and_invalidation_without_scoring() -> None:
    evidence = build_catalyst_horizon_evidence(
        [
            _event(
                "2026-10-15",
                binary_event=True,
                market_pricing_status="partially_priced",
                surprise_potential="high",
                prerequisite_status="pending",
            )
        ],
        evaluation_date=EVALUATION,
    )
    event = evidence.events[0]
    assert event.binary_event is True
    assert event.prerequisite_status == "pending"
    assert event.market_pricing_status == "partially_priced"
    assert event.surprise_potential == "high"
    assert event.thesis_invalidation_if_failed is not None
    assert event.decision_score_enabled is False
    assert evidence.decision_score_enabled is False
    assert evidence.forecast_enabled is False
