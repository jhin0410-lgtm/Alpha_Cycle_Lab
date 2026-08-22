from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.forward_valuation import ForwardValuationMetric
from alpha_cycle.intelligence.price_implied_requirement import (
    PriceImpliedRequirementStatus,
    ReferenceFrameKind,
    ValuationReferencePoint,
    build_price_implied_requirement,
    build_valuation_reference_frame,
    persist_price_implied_requirement,
    persist_valuation_reference_frame,
)
from alpha_cycle.intelligence.valuation import ValuationEvidenceSnapshot

_KST = ZoneInfo("Asia/Seoul")
_EVIDENCE = "a" * 64
_SNAPSHOT = "b" * 64


def _valuation(
    *,
    market_cap: float | None = 100_000_000_000.0,
    complete: object = True,
    evaluation_date: date = date(2026, 8, 22),
) -> ValuationEvidenceSnapshot:
    return ValuationEvidenceSnapshot(
        captured_at=datetime(2026, 8, 22, 16, 45, tzinfo=_KST),
        evaluation_date=evaluation_date,
        research_snapshot_id="c" * 64,
        market_snapshot_id="d" * 64,
        history_years=5,
        shares=pd.DataFrame(),
        security_values=pd.DataFrame(),
        financial_history=pd.DataFrame(),
        valuation_metrics=pd.DataFrame(
            [
                {
                    "ticker": "000660",
                    "market_cap_complete": complete,
                    "market_cap": market_cap,
                }
            ]
        ),
        raw_valuation={},
    )


def _point(
    *,
    reference_id: str = "forward-pe-10x",
    metric: ForwardValuationMetric = ForwardValuationMetric.FORWARD_PE,
    multiple: float = 10.0,
    kind: ReferenceFrameKind = ReferenceFrameKind.HISTORICAL_FORWARD_VINTAGE,
    evidence: tuple[str, ...] = (_EVIDENCE,),
    target_period_end: date = date(2026, 12, 31),
    observed_at: datetime | None = None,
) -> ValuationReferencePoint:
    return ValuationReferencePoint(
        reference_id=reference_id,
        metric=metric,
        target_period="FY2026",
        target_period_end=target_period_end,
        reference_multiple=multiple,
        reference_kind=kind,
        observed_at=observed_at or datetime(2026, 8, 22, 15, 0, tzinfo=_KST),
        rationale="Frozen conditional valuation reference for reverse inference.",
        source_evidence_ids=evidence,
    )


def _frame(*points: ValuationReferencePoint, evaluation_date: date = date(2026, 8, 22)):
    selected = points or (_point(),)
    return build_valuation_reference_frame(
        captured_at=datetime(2026, 8, 22, 16, 0, tzinfo=_KST),
        evaluation_date=evaluation_date,
        security_id="000660",
        reference_points=tuple(selected),
        source_snapshot_ids=(_SNAPSHOT,),
    )


def test_forward_pe_reference_implies_required_net_income() -> None:
    snapshot = build_price_implied_requirement(_valuation(), _frame())
    row = snapshot.observations[0]
    assert row.status is PriceImpliedRequirementStatus.AVAILABLE
    assert row.implied_metric.value == "net_income"
    assert row.implied_value_krw == pytest.approx(10_000_000_000.0)
    assert snapshot.guardrail_evidence_id == load_decision_system_v21_guardrails().evidence_id


def test_forward_ps_reference_implies_required_revenue() -> None:
    point = _point(
        reference_id="forward-ps-2x",
        metric=ForwardValuationMetric.FORWARD_PS,
        multiple=2.0,
    )
    row = build_price_implied_requirement(_valuation(), _frame(point)).observations[0]
    assert row.implied_metric.value == "revenue"
    assert row.implied_value_krw == pytest.approx(50_000_000_000.0)


def test_multiple_reference_points_remain_surface_without_selection() -> None:
    low = _point(reference_id="pe-8x", multiple=8.0)
    high = _point(reference_id="pe-12x", multiple=12.0)
    snapshot = build_price_implied_requirement(_valuation(), _frame(low, high))
    assert len(snapshot.observations) == 2
    implied = {row.reference_id: row.implied_value_krw for row in snapshot.observations}
    assert implied["pe-8x"] == pytest.approx(12_500_000_000.0)
    assert implied["pe-12x"] == pytest.approx(100_000_000_000.0 / 12.0)
    payload = snapshot.payload_without_id()
    assert payload["market_expectation_claimed"] is False
    assert payload["single_price_implied_truth_claimed"] is False


def test_explicit_scenario_reference_may_exist_without_external_evidence() -> None:
    point = _point(
        kind=ReferenceFrameKind.EXPLICIT_SCENARIO_ASSUMPTION,
        evidence=(),
    )
    frame = _frame(point)
    assert frame.reference_points[0].payload()["market_expectation_certified"] is False
    assert frame.payload_without_id()["single_market_expectation_claimed"] is False


def test_evidence_based_reference_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires source_evidence_ids"):
        _point(evidence=())


def test_incomplete_market_cap_keeps_requirement_unavailable() -> None:
    snapshot = build_price_implied_requirement(
        _valuation(market_cap=80_000_000_000.0, complete=False),
        _frame(),
    )
    row = snapshot.observations[0]
    assert row.status is PriceImpliedRequirementStatus.MARKET_CAP_UNAVAILABLE
    assert row.market_cap_krw is None
    assert row.implied_value_krw is None


def test_market_cap_completeness_requires_strict_boolean() -> None:
    with pytest.raises(ValueError, match="market_cap_complete must be a boolean"):
        build_price_implied_requirement(_valuation(complete="false"), _frame())


def test_historical_target_period_is_rejected() -> None:
    point = _point(target_period_end=date(2026, 6, 30))
    with pytest.raises(ValueError, match="target must not be historical"):
        _frame(point)


def test_evaluation_date_mismatch_fails_closed() -> None:
    prior_point = _point(
        observed_at=datetime(2026, 8, 21, 15, 0, tzinfo=_KST),
    )
    with pytest.raises(ValueError, match="same evaluation date"):
        build_price_implied_requirement(
            _valuation(evaluation_date=date(2026, 8, 22)),
            _frame(prior_point, evaluation_date=date(2026, 8, 21)),
        )


def test_persistence_keeps_reference_and_requirement_separate(tmp_path: Path) -> None:
    frame = _frame()
    snapshot = build_price_implied_requirement(_valuation(), frame)
    frame_pointer = persist_valuation_reference_frame(frame, output_root=tmp_path)
    result_pointer = persist_price_implied_requirement(snapshot, output_root=tmp_path)

    assert frame_pointer.parent.name == "valuation_reference_frame"
    assert result_pointer.parent.name == "price_implied_requirement"

    pointer = json.loads(result_pointer.read_text(encoding="utf-8"))
    directory = Path(pointer["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == snapshot.snapshot_id
    assert manifest["immutable"] is True
    assert manifest["market_expectation_claimed"] is False
    assert manifest["fair_value_enabled"] is False
    assert manifest["target_price_enabled"] is False
    assert manifest["decision_score_enabled"] is False
    assert manifest["automatic_execution_enabled"] is False
