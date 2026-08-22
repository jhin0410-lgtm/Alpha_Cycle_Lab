from __future__ import annotations

import json
from dataclasses import replace
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
from alpha_cycle.intelligence.epistemic_defense import (
    BlindSpotCandidate,
    CounterExplanation,
    CounterThesisStatus,
    MaterialityLevel,
    PromotionRecommendation,
    UnresolvedContradiction,
    build_blind_spot_snapshot,
    build_counter_thesis_snapshot,
    build_epistemic_defense_package,
    persist_blind_spot_discovery,
    persist_counter_thesis,
    persist_epistemic_defense_package,
)

_KST = ZoneInfo("Asia/Seoul")
_EVIDENCE_A = "a" * 64
_EVIDENCE_B = "b" * 64


def _uncertainty() -> ThesisUncertainty:
    dimension = UncertaintyDimension(
        UncertaintyLevel.MEDIUM,
        "Material uncertainty remains explicit.",
    )
    return ThesisUncertainty(
        evidence=dimension,
        model=dimension,
        regime=dimension,
        expectation=dimension,
        catalyst=dimension,
        valuation=dimension,
    )


def _thesis(*, thesis_id: str = "000660-memory-cycle") -> InvestmentThesisSnapshot:
    claim = ThesisClaim(
        claim_id="memory-cycle",
        category="industry_cycle",
        statement="Memory pricing is improving relative to the prior observed state.",
        epistemic_status=EpistemicStatus.OBSERVED_FACT,
        direction=ClaimDirection.POSITIVE,
        evidence_refs=("evidence:memory-price",),
    )
    return InvestmentThesisSnapshot(
        thesis_id=thesis_id,
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=datetime(2026, 8, 22, 18, 0, tzinfo=_KST),
        security_id="000660",
        horizon_trading_days=120,
        variant_view="Earnings revisions may lag the memory-cycle inflection.",
        why_now="Industry evidence changed before the next earnings catalyst.",
        claims=(claim,),
        catalysts=(
            CatalystClock(
                catalyst_id="next-filing",
                statement="The next filing tests earnings transmission.",
                evidence_refs=("evidence:filing-calendar",),
                earliest_date=date(2026, 10, 1),
                latest_date=date(2026, 11, 16),
            ),
        ),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=("Memory pricing reverses while supply expands.",),
        first_rejection_risk="The cycle inflection may already be priced.",
        portfolio_overlap=("memory-upcycle",),
        opportunity_set_refs=("opportunity-set:2026-08-22",),
        status=ThesisStatus.UNDERWRITING,
    )


def _alternative(**overrides: object) -> CounterExplanation:
    values: dict[str, object] = {
        "explanation_id": "alt-demand-pull-forward",
        "statement": "Observed pricing strength may reflect temporary demand pull-forward.",
        "mechanism": "Customers pre-buy inventory ahead of expected supply or policy changes.",
        "epistemic_status": EpistemicStatus.ECONOMIC_HYPOTHESIS,
        "materiality": MaterialityLevel.HIGH,
        "supporting_evidence_refs": ("evidence:customer-inventory",),
        "opposing_evidence_refs": ("evidence:contract-duration",),
        "falsifier": "Pricing and shipment growth persist after customer inventory normalizes.",
    }
    values.update(overrides)
    return CounterExplanation(**values)  # type: ignore[arg-type]


def _counter(thesis: InvestmentThesisSnapshot, **overrides: object):
    values: dict[str, object] = {
        "counter_thesis_id": "000660-memory-cycle-counter",
        "snapshot_version": 1,
        "parent_snapshot_id": None,
        "thesis_snapshot_id": thesis.snapshot_id,
        "captured_at": datetime(2026, 8, 22, 18, 10, tzinfo=_KST),
        "created_without_thesis_support_search": True,
        "independence_method": "Separate search prompt and evidence pass before reading support refs.",
        "search_scope": ("demand reversal", "customer inventory", "competitor supply"),
        "strongest_alternative_explanation_id": "alt-demand-pull-forward",
        "alternative_explanations": (_alternative(),),
        "falsification_evidence_refs": ("evidence:falsification-plan",),
        "missing_evidence": ("customer inventory by major buyer",),
        "unresolved_contradictions": (
            UnresolvedContradiction(
                contradiction_id="pricing-vs-inventory",
                statement="Pricing strength conflicts with uncertain end-customer inventory.",
                materiality=MaterialityLevel.HIGH,
                evidence_refs=("evidence:pricing", "evidence:inventory-gap"),
            ),
        ),
        "status": CounterThesisStatus.UNRESOLVED,
    }
    values.update(overrides)
    return build_counter_thesis_snapshot(**values)


def _candidate(**overrides: object) -> BlindSpotCandidate:
    values: dict[str, object] = {
        "candidate_id": "fx-translation",
        "variable": "USD/KRW translation",
        "mechanism": "FX can alter reported KRW earnings independently of memory-unit economics.",
        "materiality": MaterialityLevel.HIGH,
        "evidence_refs": ("evidence:fx-sensitivity",),
        "already_covered": False,
        "promotion_recommendation": PromotionRecommendation.MONITOR,
        "rationale": "The current critical-state set does not explicitly represent FX translation.",
    }
    values.update(overrides)
    return BlindSpotCandidate(**values)  # type: ignore[arg-type]


def _blind_spot(thesis: InvestmentThesisSnapshot, **overrides: object):
    values: dict[str, object] = {
        "discovery_id": "000660-memory-cycle-blind-spot",
        "snapshot_version": 1,
        "parent_snapshot_id": None,
        "thesis_snapshot_id": thesis.snapshot_id,
        "captured_at": datetime(2026, 8, 22, 18, 12, tzinfo=_KST),
        "existing_critical_state_variables": (
            "AI/HBM demand",
            "memory supply",
            "memory price and mix",
            "earnings revision trajectory",
            "valuation and positioning",
        ),
        "graph_variables_used_as_exclusion_set": True,
        "search_scope": ("macro", "competition", "policy", "capital allocation"),
        "discovery_method": "Search outside the existing critical-state variable names and mechanisms.",
        "search_completed": True,
        "candidates": (_candidate(),),
        "search_limitations": (
            "Search coverage is finite and does not prove that no other blind spot exists.",
        ),
        "no_candidate_found_reason": None,
    }
    values.update(overrides)
    return build_blind_spot_snapshot(**values)


def test_counter_thesis_must_be_independent_of_support_search() -> None:
    thesis = _thesis()
    with pytest.raises(ValueError, match="independently of thesis support search"):
        _counter(thesis, created_without_thesis_support_search=False)


def test_counter_thesis_strongest_explanation_must_exist() -> None:
    thesis = _thesis()
    with pytest.raises(ValueError, match="strongest alternative explanation must exist"):
        _counter(thesis, strongest_alternative_explanation_id="missing")


def test_counter_observed_fact_requires_supporting_evidence() -> None:
    with pytest.raises(ValueError, match="counter explanation requires evidence"):
        _alternative(
            epistemic_status=EpistemicStatus.OBSERVED_FACT,
            supporting_evidence_refs=(),
        )


def test_counter_and_blind_spot_lineage_is_append_only() -> None:
    thesis = _thesis()
    first_counter = _counter(thesis)
    second_counter = _counter(
        thesis,
        snapshot_version=2,
        parent_snapshot_id=first_counter.snapshot_id,
        captured_at=datetime(2026, 8, 23, 18, 10, tzinfo=_KST),
    )
    assert second_counter.parent_snapshot_id == first_counter.snapshot_id
    first_blind = _blind_spot(thesis)
    second_blind = _blind_spot(
        thesis,
        snapshot_version=2,
        parent_snapshot_id=first_blind.snapshot_id,
        captured_at=datetime(2026, 8, 23, 18, 12, tzinfo=_KST),
    )
    assert second_blind.parent_snapshot_id == first_blind.snapshot_id


def test_blind_spot_scan_enforces_five_variable_decision_budget() -> None:
    thesis = _thesis()
    with pytest.raises(ValueError, match="complexity budget"):
        _blind_spot(
            thesis,
            existing_critical_state_variables=("a", "b", "c", "d", "e", "f"),
        )


def test_blind_spot_scan_must_exclude_existing_graph_variables() -> None:
    thesis = _thesis()
    with pytest.raises(ValueError, match="exclude already represented variables"):
        _blind_spot(thesis, graph_variables_used_as_exclusion_set=False)


def test_high_materiality_blind_spot_requires_evidence() -> None:
    with pytest.raises(ValueError, match="high-materiality blind spot requires evidence_refs"):
        _candidate(evidence_refs=())


def test_promoted_blind_spot_cannot_already_be_covered() -> None:
    with pytest.raises(ValueError, match="already-covered variable cannot be promoted"):
        _candidate(
            already_covered=True,
            promotion_recommendation=PromotionRecommendation.PROMOTE_TO_CRITICAL_VARIABLE,
        )


def test_empty_blind_spot_result_requires_explicit_reason() -> None:
    thesis = _thesis()
    with pytest.raises(ValueError, match="requires no_candidate_found_reason"):
        _blind_spot(thesis, candidates=(), no_candidate_found_reason=None)
    empty = _blind_spot(
        thesis,
        candidates=(),
        no_candidate_found_reason="No uncovered candidate passed the documented search screen.",
    )
    assert empty.candidates == ()


def test_epistemic_package_surfaces_material_flags_without_approving_trade() -> None:
    thesis = _thesis()
    counter = _counter(thesis)
    blind_spot = _blind_spot(
        thesis,
        candidates=(
            _candidate(
                promotion_recommendation=(
                    PromotionRecommendation.PROMOTE_TO_CRITICAL_VARIABLE
                )
            ),
        ),
    )
    package = build_epistemic_defense_package(
        thesis,
        counter,
        blind_spot,
        captured_at=datetime(2026, 8, 22, 18, 15, tzinfo=_KST),
    )
    assert package.high_materiality_counter_explanation_count == 1
    assert package.high_materiality_unresolved_contradiction_count == 1
    assert package.uncovered_high_materiality_blind_spot_count == 1
    assert package.blind_spot_promotion_candidate_count == 1
    payload = package.payload_without_id()
    assert payload["decision_score_enabled"] is False
    assert payload["investability_decision_enabled"] is False
    assert payload["automatic_execution_enabled"] is False


def test_epistemic_package_rejects_cross_thesis_binding() -> None:
    thesis = _thesis()
    other = _thesis(thesis_id="000660-other-thesis")
    counter = _counter(other)
    blind_spot = _blind_spot(thesis)
    with pytest.raises(ValueError, match="counter-thesis is bound to a different thesis"):
        build_epistemic_defense_package(
            thesis,
            counter,
            blind_spot,
            captured_at=datetime(2026, 8, 22, 18, 15, tzinfo=_KST),
        )


def test_persistence_keeps_epistemic_objects_content_addressed_and_separate(
    tmp_path: Path,
) -> None:
    thesis = _thesis()
    counter = _counter(thesis)
    blind_spot = _blind_spot(thesis)
    package = build_epistemic_defense_package(
        thesis,
        counter,
        blind_spot,
        captured_at=datetime(2026, 8, 22, 18, 15, tzinfo=_KST),
    )
    counter_pointer = persist_counter_thesis(counter, output_root=tmp_path)
    blind_pointer = persist_blind_spot_discovery(blind_spot, output_root=tmp_path)
    package_pointer = persist_epistemic_defense_package(package, output_root=tmp_path)

    assert counter_pointer.parent.name == "counter_thesis"
    assert blind_pointer.parent.name == "blind_spot"
    assert package_pointer.parent.name == "epistemic_package"

    pointer_payload = json.loads(package_pointer.read_text(encoding="utf-8"))
    directory = Path(pointer_payload["snapshot_path"])
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == package.snapshot_id
    assert manifest["immutable"] is True
    assert manifest["decision_score_enabled"] is False
    assert manifest["investability_decision_enabled"] is False
    assert manifest["automatic_execution_enabled"] is False
