from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from alpha_cycle.intelligence.investor_flow_evidence import (
    FlowWindowSummary,
    InvestorFlowEvidence,
)
from alpha_cycle.intelligence.macro_liquidity_evidence import MacroLiquidityEvidence
from alpha_cycle.intelligence.observable_universe import (
    AttemptStatus,
    CandidateRule,
    ChangeState,
    EvidenceMaturity,
    EvidenceReference,
    MeasuredObservation,
    MemberKind,
    ObservableUniverseError,
    ObservableUniverseSnapshot,
    ResearchModelStatus,
    ResearchPriority,
    UniverseMember,
    compare_universe_snapshots,
    load_current_universe_state,
    load_universe_snapshot,
    persist_successful_universe_attempt,
    planner_input,
    publish_failed_universe_attempt,
    surface_research_candidates,
)

T0 = datetime(2026, 8, 1, tzinfo=UTC)
T1 = datetime(2026, 8, 2, tzinfo=UTC)


def evidence(
    reference_id: str = "market-000660-20260801",
    *,
    at: datetime = T0,
    maturity: EvidenceMaturity = EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE,
    authority: str = "adjusted_close_market_evidence",
) -> EvidenceReference:
    return EvidenceReference(reference_id, "market_writer", at, maturity, authority)


def observation(
    value: float | None,
    *,
    member_id: str = "000660",
    dimension: str = "market_return",
    metric: str = "return",
    unit: str = "percent",
    basis: str = "adjusted_close",
    window: str = "20d",
    semantics: str = "trailing_market_return",
    at: datetime = T0,
    reference_id: str = "market-000660-20260801",
    maturity: EvidenceMaturity = EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE,
    unavailable_reason: str | None = None,
    authority: str = "adjusted_close_market_evidence",
) -> MeasuredObservation:
    refs = (
        ()
        if maturity is EvidenceMaturity.UNAVAILABLE
        else (evidence(reference_id, at=at, maturity=maturity, authority=authority),)
    )
    return MeasuredObservation(
        member_id=member_id,
        dimension_id=dimension,
        metric_id=metric,
        value=value,
        unit=unit,
        basis=basis,
        window=window,
        semantics=semantics,
        observed_at=at,
        available_at=at,
        maturity=maturity,
        evidence=refs,
        unavailable_reason=unavailable_reason,
    )


def member(
    member_id: str = "000660",
    *,
    aliases: tuple[str, ...] = ("SK hynix",),
    available: tuple[str, ...] = ("market_return",),
    unavailable: tuple[str, ...] = ("consensus",),
) -> UniverseMember:
    return UniverseMember(
        member_id=member_id,
        kind=MemberKind.SECURITY,
        domain_id="memory_semiconductor",
        aliases=aliases,
        required_dimensions=("market_return", "consensus"),
        available_dimensions=available,
        unavailable_dimensions=unavailable,
        research_model_status=ResearchModelStatus.DRAFT,
    )


def snapshot(
    value: float | None = 1.0,
    *,
    cutoff: datetime = T0,
    obs: tuple[MeasuredObservation, ...] | None = None,
    members: tuple[UniverseMember, ...] | None = None,
    version: str = "1",
) -> ObservableUniverseSnapshot:
    observations = obs if obs is not None else (observation(value, at=cutoff),)
    refs = tuple(sorted({ref.reference_id for item in observations for ref in item.evidence}))
    return ObservableUniverseSnapshot(
        universe_id="krx-research",
        version=version,
        research_cutoff_at=cutoff,
        members=members or (member(),),
        observations=observations,
        source_evidence_refs=refs,
    )


def test_valid_universe_is_deterministic_and_generic() -> None:
    first = snapshot()
    second = snapshot()
    assert first.snapshot_id == second.snapshot_id
    assert first.payload_without_id()["investment_authority"] is False
    generic = snapshot(
        obs=(observation(12.0, member_id="LMT", reference_id="market-lmt"),),
        members=(
            UniverseMember(
                member_id="LMT",
                kind=MemberKind.SECURITY,
                domain_id="defense_aerospace",
                required_dimensions=("market_return",),
                available_dimensions=("market_return",),
            ),
        ),
    )
    assert generic.members[0].domain_id == "defense_aerospace"


def test_duplicate_member_and_ambiguous_alias_rejected() -> None:
    with pytest.raises(ObservableUniverseError, match="duplicate"):
        snapshot(members=(member(), member(aliases=("Hynix",))))
    with pytest.raises(ObservableUniverseError, match="ambiguous alias"):
        snapshot(
            members=(
                member(aliases=("chip",)),
                member("005930", aliases=("CHIP",)),
            )
        )
    with pytest.raises(ObservableUniverseError, match="collides"):
        snapshot(
            members=(member(aliases=("005930",)), member("005930", aliases=())),
        )


def test_future_and_outside_observations_rejected() -> None:
    with pytest.raises(ObservableUniverseError, match="future evidence"):
        snapshot(cutoff=T0, obs=(observation(1.0, at=T1),))
    with pytest.raises(ObservableUniverseError, match="outside"):
        snapshot(obs=(observation(1.0, member_id="005930"),))


def test_duplicate_metric_slot_rejected() -> None:
    with pytest.raises(ObservableUniverseError, match="duplicate metric slots"):
        snapshot(obs=(observation(1.0), observation(2.0, metric="other")))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("metric_id", "price_return"),
        ("unit", "decimal"),
        ("basis", "unadjusted_close"),
        ("window", "5d"),
        ("semantics", "forward_return"),
    ],
)
def test_comparability_rejects_semantic_mismatch(field: str, value: str) -> None:
    prior = snapshot()
    current_observation = replace(observation(2.0, at=T1), **{field: value})
    current = snapshot(cutoff=T1, obs=(current_observation,), version="2")
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert field in change.reason
    assert change.delta is None


def test_changed_unchanged_and_exact_lineage() -> None:
    changed = compare_universe_snapshots(snapshot(1.0), snapshot(3.0, cutoff=T1, version="2"))[0]
    assert changed.state is ChangeState.CHANGED
    assert changed.delta == 2.0
    assert changed.evidence_refs == ("market-000660-20260801",)
    unchanged = compare_universe_snapshots(snapshot(1.0), snapshot(1.0, cutoff=T1, version="2"))[0]
    assert unchanged.state is ChangeState.UNCHANGED


def test_newly_available_newly_missing_and_stale() -> None:
    missing0 = observation(
        None,
        maturity=EvidenceMaturity.UNAVAILABLE,
        unavailable_reason="provider unavailable",
    )
    missing1 = replace(missing0, observed_at=T1, available_at=T1)
    available0 = observation(1.0)
    available1 = observation(2.0, at=T1)
    assert (
        compare_universe_snapshots(
            snapshot(obs=(missing0,)), snapshot(cutoff=T1, obs=(available1,), version="2")
        )[0].state
        is ChangeState.NEWLY_AVAILABLE
    )
    assert (
        compare_universe_snapshots(
            snapshot(obs=(available0,)), snapshot(cutoff=T1, obs=(missing1,), version="2")
        )[0].state
        is ChangeState.NEWLY_MISSING
    )
    stale_current = snapshot(cutoff=T1, obs=(available0,), version="2")
    assert (
        compare_universe_snapshots(snapshot(), stale_current, stale_after=timedelta(hours=12))[
            0
        ].state
        is ChangeState.STALE
    )


def test_missing_evidence_is_explicit_and_cannot_become_value() -> None:
    missing = observation(
        None,
        maturity=EvidenceMaturity.UNAVAILABLE,
        unavailable_reason="licensed consensus unavailable",
    )
    assert missing.value is None
    assert missing.evidence == ()
    with pytest.raises(ObservableUniverseError, match="null value"):
        replace(missing, value=0.0)


def test_macro_and_verified_flow_remain_descriptive_upstream_evidence() -> None:
    flow = observation(
        12500,
        dimension="investor_flow",
        metric="foreign_net_buy_shares",
        unit="shares",
        basis="verified_investor_classification",
        window="5d",
        semantics="verified_investor_flow_evidence",
        reference_id="investor-flow-snapshot",
        authority="verified investor-flow evidence; decision score disabled",
    )
    macro = observation(
        -0.2,
        member_id="US_FINANCIAL_CONDITIONS",
        dimension="macro_liquidity",
        metric="NFCI",
        unit="index",
        basis="official_series_current_vintage",
        window="latest",
        semantics="descriptive_macro_liquidity_non_pit_backtest",
        reference_id="macro-liquidity-evidence",
        maturity=EvidenceMaturity.STRUCTURED_OBSERVATION,
        authority="macro liquidity observation; composite score disabled",
    )
    state = ObservableUniverseSnapshot(
        "cross-asset",
        "1",
        T0,
        (
            UniverseMember("000660", MemberKind.SECURITY, available_dimensions=("investor_flow",)),
            UniverseMember(
                "US_FINANCIAL_CONDITIONS",
                MemberKind.ASSET,
                available_dimensions=("macro_liquidity",),
            ),
        ),
        (flow, macro),
        ("investor-flow-snapshot", "macro-liquidity-evidence"),
    )
    payload = state.payload_without_id()
    assert payload["decision_score_enabled"] is False
    assert payload["causal_claim_enabled"] is False
    assert flow.evidence[0].semantic_authority.startswith("verified investor-flow")
    assert "composite score disabled" in macro.evidence[0].semantic_authority


def test_real_upstream_evidence_types_fit_envelope_without_authority_promotion() -> None:
    flow_window = FlowWindowSummary(
        ticker="000660",
        window=5,
        observations=5,
        latest_date="20260801",
        oldest_date="20260727",
        latest_price_abs=200_000,
        oldest_price_abs=190_000,
        price_return_pct=5.26,
        cumulative_volume=1_000_000,
        individual_net_buy_shares=-100_000,
        foreign_net_buy_shares=60_000,
        institution_net_buy_shares=40_000,
        pension_net_buy_shares=5_000,
        foreign_institution_net_buy_shares=100_000,
        foreign_institution_volume_ratio=0.1,
        descriptive_state="demand_confirmation",
    )
    flow_evidence = InvestorFlowEvidence(
        status="verified",
        reason="verified_live_evidence",
        source_scope="kiwoom_openapi_plus_opt10059_net_buy_quantity",
        snapshot_id="flow-writer-snapshot",
        provider_semantic_status="verified",
        request_contract_status="verified_net_buy_quantity_single_share_unscored",
        field_mapping_verified=True,
        point_in_time_verified=True,
        evidence_verified=True,
        decision_score_enabled=False,
        evaluation_date="2026-08-01",
        reference_date="20260801",
        captured_date="2026-08-01",
        tickers=(),
        windows=(flow_window,),
    )
    macro_evidence = MacroLiquidityEvidence(
        evidence_id="a" * 64,
        evaluation_date=T0.date(),
        series=pd.DataFrame([{"series_id": "NFCI", "latest_value": -0.2}]),
        observations=pd.DataFrame([{"series_id": "NFCI", "value": -0.2}]),
    )
    assert flow_evidence.decision_score_enabled is False
    assert macro_evidence.composite_liquidity_score_enabled is False
    flow_observation = observation(
        flow_window.foreign_institution_net_buy_shares,
        dimension="investor_flow",
        metric="foreign_institution_net_buy_shares",
        unit="shares",
        basis=flow_evidence.request_contract_status,
        window="5d",
        semantics="verified_descriptive_flow",
        reference_id=flow_evidence.snapshot_id,
        authority="verified investor-flow evidence; decision score disabled",
    )
    macro_observation = observation(
        -0.2,
        member_id="US_FINANCIAL_CONDITIONS",
        dimension="macro_liquidity",
        metric="NFCI",
        unit="index",
        basis="official_series_current_vintage",
        window="latest",
        semantics="descriptive_non_historical_vintage",
        reference_id=macro_evidence.evidence_id,
        maturity=EvidenceMaturity.STRUCTURED_OBSERVATION,
        authority="macro observation; no composite score",
    )
    assert flow_observation.evidence[0].reference_id == flow_evidence.snapshot_id
    assert macro_observation.evidence[0].reference_id == macro_evidence.evidence_id


def test_candidate_is_deterministic_explainable_and_non_authoritative() -> None:
    current = snapshot(3.0, cutoff=T1, version="2")
    changes = compare_universe_snapshots(snapshot(1.0), current)
    rule = CandidateRule(
        "material-return-change",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ELEVATED,
        "material market-state change deserves research",
        minimum_absolute_delta=1.0,
    )
    first = surface_research_candidates(current, changes, (rule,))
    second = surface_research_candidates(current, tuple(reversed(changes)), (rule,))
    assert first == second
    candidate = first[0]
    assert candidate.candidate_id == second[0].candidate_id
    assert candidate.triggering_change_ids == (changes[0].change_id,)
    assert candidate.triggering_evidence_refs == changes[0].evidence_refs
    assert candidate.missing_dimensions == ("consensus",)
    assert candidate.investment_authority is False
    payload = candidate.payload_without_id()
    assert payload["candidate_semantics"] == "research_this"
    assert payload["decision_score"] is None
    assert payload["recommendation"] is None
    assert payload["expected_return"] is None
    assert planner_input(candidate).candidate_id == candidate.candidate_id


def test_missing_evidence_never_improves_candidate_and_no_rule_means_no_candidate() -> None:
    current = snapshot(2.0, cutoff=T1, version="2")
    changes = compare_universe_snapshots(snapshot(1.0), current)
    assert surface_research_candidates(current, changes, ()) == ()
    missing_change = compare_universe_snapshots(
        snapshot(1.0),
        snapshot(
            cutoff=T1,
            version="2",
            obs=(
                observation(
                    None,
                    at=T1,
                    maturity=EvidenceMaturity.UNAVAILABLE,
                    unavailable_reason="source failed",
                ),
            ),
        ),
    )
    positive_only = CandidateRule(
        "changed-only",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.URGENT,
        "measured change",
    )
    assert surface_research_candidates(current, missing_change, (positive_only,)) == ()


def test_candidate_ordering_is_deterministic_across_members() -> None:
    members = (
        member("005930", aliases=("Samsung",)),
        member("000660", aliases=("Hynix",)),
    )
    prior = snapshot(
        members=members,
        obs=(observation(1.0, member_id="005930", reference_id="s1"), observation(1.0)),
    )
    current = snapshot(
        cutoff=T1,
        version="2",
        members=members,
        obs=(
            observation(2.0, member_id="005930", at=T1, reference_id="s2"),
            observation(2.0, at=T1),
        ),
    )
    rule = CandidateRule(
        "changed", "market_return", (ChangeState.CHANGED,), ResearchPriority.ROUTINE, "changed"
    )
    candidates = surface_research_candidates(
        current, compare_universe_snapshots(prior, current), (rule,)
    )
    assert [item.member_id for item in candidates] == ["000660", "005930"]


def test_persistence_replay_and_failed_later_attempt_semantics(tmp_path: Path) -> None:
    state = snapshot()
    path = persist_successful_universe_attempt(state, output_root=tmp_path, attempted_at=T0)
    assert load_universe_snapshot(path) == state
    current = load_current_universe_state(tmp_path)
    assert current is not None and current.ready and current.snapshot == state
    publish_failed_universe_attempt(
        output_root=tmp_path, attempted_at=T1, failure_code="provider_timeout"
    )
    failed = load_current_universe_state(tmp_path)
    assert failed is not None
    assert failed.status is AttemptStatus.FAILED
    assert failed.ready is False
    assert failed.snapshot is None
    assert failed.failure_code == "provider_timeout"
    assert path.exists()  # immutable history remains, but is not current readiness


@pytest.mark.parametrize("target", ["snapshot", "manifest", "pointer"])
def test_persisted_tampering_fails_closed(tmp_path: Path, target: str) -> None:
    state = snapshot()
    snapshot_path = persist_successful_universe_attempt(
        state, output_root=tmp_path, attempted_at=T0
    )
    current_path = tmp_path / "observable_universe_v1/current.json"
    pointer = json.loads(current_path.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "observable_universe_v1/manifests" / f"{pointer['manifest_id']}.json"
    path = {"snapshot": snapshot_path, "manifest": manifest_path, "pointer": current_path}[target]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tampered"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ObservableUniverseError):
        load_current_universe_state(tmp_path)


def test_attempt_time_cannot_move_backward(tmp_path: Path) -> None:
    persist_successful_universe_attempt(snapshot(), output_root=tmp_path, attempted_at=T1)
    with pytest.raises(ObservableUniverseError, match="move backward"):
        publish_failed_universe_attempt(
            output_root=tmp_path, attempted_at=T0, failure_code="old_failure"
        )
