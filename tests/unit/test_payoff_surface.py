from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from alpha_cycle.intelligence.decision_thesis_v2 import (
    CatalystClock,
    ClaimDirection,
    EpistemicStatus,
    InvestmentThesisSnapshot,
    ThesisClaim,
    ThesisStatus,
    ThesisUncertainty,
    UncertaintyDimension,
    UncertaintyLevel,
)
from alpha_cycle.intelligence.payoff_surface import (
    PayoffScenario,
    ScenarioLabel,
    build_payoff_surface,
    persist_payoff_surface,
)

_KST = ZoneInfo("Asia/Seoul")
_EVIDENCE = "a" * 64


def _thesis() -> InvestmentThesisSnapshot:
    uncertainty = UncertaintyDimension(UncertaintyLevel.MEDIUM, "Uncertainty is explicit.")
    return InvestmentThesisSnapshot(
        thesis_id="000660-underwriting",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=datetime(2026, 8, 22, 19, 0, tzinfo=_KST),
        security_id="000660",
        horizon_trading_days=120,
        variant_view="Earnings revisions may lag memory fundamentals.",
        why_now="Memory-cycle evidence changed before the next earnings catalyst.",
        claims=(
            ThesisClaim(
                claim_id="industry",
                category="industry_cycle",
                statement="Memory conditions are changing.",
                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
                direction=ClaimDirection.POSITIVE,
            ),
        ),
        catalysts=(
            CatalystClock(
                catalyst_id="earnings",
                statement="Next earnings release tests the thesis.",
                evidence_refs=("evidence:calendar",),
                earliest_date=date(2026, 10, 1),
                latest_date=date(2026, 11, 16),
            ),
        ),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=ThesisUncertainty(
            evidence=uncertainty,
            model=uncertainty,
            regime=uncertainty,
            expectation=uncertainty,
            catalyst=uncertainty,
            valuation=uncertainty,
        ),
        kill_conditions=("Memory pricing reverses while supply expands.",),
        first_rejection_risk="The improvement may already be priced.",
        portfolio_overlap=("memory-upcycle",),
        opportunity_set_refs=("opportunity-set:2026-08-22",),
        status=ThesisStatus.UNDERWRITING,
    )


def _scenario(label: ScenarioLabel, lower: float, upper: float) -> PayoffScenario:
    return PayoffScenario(
        scenario_id=f"{label.value}-case",
        label=label,
        horizon_trading_days=120,
        trigger_conditions=(f"{label.value} operating conditions emerge",),
        fundamental_assumptions=(f"{label.value} earnings assumptions hold",),
        catalyst_refs=("catalyst:earnings",),
        source_evidence_ids=(_EVIDENCE,),
        return_lower=lower,
        return_upper=upper,
        thesis_break_conditions=("The scenario assumptions are invalidated.",),
    )


def _surface():
    return build_payoff_surface(
        _thesis(),
        captured_at=datetime(2026, 8, 22, 19, 10, tzinfo=_KST),
        scenarios=(
            _scenario(ScenarioLabel.BEAR, -0.35, -0.15),
            _scenario(ScenarioLabel.BASE, 0.10, 0.30),
            _scenario(ScenarioLabel.BULL, 0.35, 0.60),
        ),
        source_snapshot_ids=("b" * 64,),
    )


def test_surface_requires_bear_base_bull_and_no_probabilities() -> None:
    surface = _surface()
    assert surface.worst_case_return_lower == pytest.approx(-0.35)
    assert surface.best_case_return_upper == pytest.approx(0.60)
    payload = surface.payload_without_id()
    assert payload["probabilities_calibrated"] is False
    assert payload["expected_value_calculated"] is False
    assert all(row["scenario_probability"] is None for row in payload["scenarios"])


def test_missing_or_duplicate_scenario_label_fails_closed() -> None:
    thesis = _thesis()
    with pytest.raises(ValueError, match="exactly one bear, base, and bull"):
        build_payoff_surface(
            thesis,
            captured_at=datetime(2026, 8, 22, 19, 10, tzinfo=_KST),
            scenarios=(
                _scenario(ScenarioLabel.BEAR, -0.4, -0.2),
                _scenario(ScenarioLabel.BASE, 0.0, 0.2),
                _scenario(ScenarioLabel.BASE, 0.1, 0.3),
            ),
        )


def test_numeric_range_requires_evidence_and_valid_bounds() -> None:
    with pytest.raises(ValueError, match="requires source_evidence_ids"):
        PayoffScenario(
            scenario_id="bear",
            label=ScenarioLabel.BEAR,
            horizon_trading_days=120,
            trigger_conditions=("bear",),
            fundamental_assumptions=("bear assumptions",),
            catalyst_refs=(),
            source_evidence_ids=(),
            return_lower=-0.4,
            return_upper=-0.2,
            thesis_break_conditions=(),
        )
    with pytest.raises(ValueError, match="return_upper"):
        _scenario(ScenarioLabel.BASE, 0.3, 0.1)
    with pytest.raises(ValueError, match="-100%"):
        _scenario(ScenarioLabel.BEAR, -1.1, -0.5)


def test_surface_must_share_thesis_horizon() -> None:
    thesis = _thesis()
    wrong = PayoffScenario(
        scenario_id="bear",
        label=ScenarioLabel.BEAR,
        horizon_trading_days=60,
        trigger_conditions=("bear",),
        fundamental_assumptions=("bear assumptions",),
        catalyst_refs=(),
        source_evidence_ids=(_EVIDENCE,),
        return_lower=-0.3,
        return_upper=-0.1,
        thesis_break_conditions=(),
    )
    with pytest.raises(ValueError, match="share the thesis horizon"):
        build_payoff_surface(
            thesis,
            captured_at=datetime(2026, 8, 22, 19, 10, tzinfo=_KST),
            scenarios=(
                wrong,
                _scenario(ScenarioLabel.BASE, 0.1, 0.3),
                _scenario(ScenarioLabel.BULL, 0.4, 0.6),
            ),
        )


def test_persistence_keeps_false_precision_disabled(tmp_path: Path) -> None:
    surface = _surface()
    pointer = persist_payoff_surface(surface, output_root=tmp_path)
    ref = json.loads(pointer.read_text(encoding="utf-8"))
    directory = Path(ref["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == surface.snapshot_id
    assert manifest["scenario_count"] == 3
    assert manifest["probabilities_calibrated"] is False
    assert manifest["expected_value_calculated"] is False
    assert manifest["target_price_enabled"] is False
    assert manifest["optimal_position_size_enabled"] is False
    assert manifest["order_api_enabled"] is False
