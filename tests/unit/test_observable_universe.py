from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

import alpha_cycle.intelligence.observable_universe as observable_module
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
T2 = datetime(2026, 8, 3, tzinfo=UTC)
T3 = datetime(2026, 8, 4, tzinfo=UTC)


def content_id(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def evidence(
    reference_id: str = "market-000660-20260801",
    *,
    at: datetime = T0,
    maturity: EvidenceMaturity = EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE,
    authority: str = "adjusted_close_market_evidence",
) -> EvidenceReference:
    return EvidenceReference(reference_id, "market_writer", at, maturity, authority)


def observation(
    value: float | int | str | bool | None,
    *,
    member_id: str = "000660",
    dimension: str = "market_return",
    metric: str = "return",
    unit: str = "percent",
    basis: str = "adjusted_close",
    window: str = "20d",
    semantics: str = "trailing_market_return",
    at: datetime = T0,
    reference_id: str | None = None,
    maturity: EvidenceMaturity = EvidenceMaturity.REPLAYABLE_PROVIDER_EVIDENCE,
    unavailable_reason: str | None = None,
    authority: str = "adjusted_close_market_evidence",
) -> MeasuredObservation:
    resolved_reference_id = reference_id or f"market-{member_id}-{at:%Y%m%d}"
    refs = (
        ()
        if maturity is EvidenceMaturity.UNAVAILABLE
        else (
            evidence(
                resolved_reference_id,
                at=at,
                maturity=maturity,
                authority=authority,
            ),
        )
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


@pytest.mark.parametrize(
    "status", (ResearchModelStatus.OPERATIONAL, ResearchModelStatus.CALIBRATING)
)
def test_active_model_status_requires_all_required_dimensions_available(
    status: ResearchModelStatus,
) -> None:
    with pytest.raises(ObservableUniverseError, match="every required dimension.*available"):
        replace(member(), research_model_status=status)


def test_snapshot_identity_canonicalizes_collection_order() -> None:
    members = (
        member("000660", aliases=("Hynix",)),
        member("005930", aliases=("Samsung",)),
    )
    observations = (
        observation(1.0),
        observation(2.0, member_id="005930", reference_id="samsung"),
    )
    first = snapshot(members=members, obs=observations)
    second = snapshot(
        members=tuple(reversed(members)),
        obs=tuple(reversed(observations)),
    )
    second = replace(
        second,
        source_evidence_refs=tuple(reversed(second.source_evidence_refs)),
    )
    assert first == second
    assert first.snapshot_id == second.snapshot_id


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


def test_non_scalar_observation_value_is_rejected_before_publication() -> None:
    with pytest.raises(ObservableUniverseError, match="JSON scalar"):
        replace(observation(1.0), value=["not", "a", "scalar"])


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
    assert changed.evidence_refs == (
        "market-000660-20260801",
        "market-000660-20260802",
    )
    unchanged = compare_universe_snapshots(snapshot(1.0), snapshot(1.0, cutoff=T1, version="2"))[0]
    assert unchanged.state is ChangeState.UNCHANGED


def test_evidence_maturity_downgrade_is_not_reported_as_unchanged() -> None:
    prior = snapshot(
        obs=(
            observation(
                1.0,
                maturity=EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY,
            ),
        )
    )
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(
            observation(
                1.0,
                at=T1,
                maturity=EvidenceMaturity.CITED_CONTEXT,
                reference_id="downgraded-context",
            ),
        ),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert "maturity differs" in change.reason


def test_evidence_maturity_upgrade_is_explicit() -> None:
    prior = snapshot(obs=(observation(1.0, maturity=EvidenceMaturity.CITED_CONTEXT),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(
            observation(
                1.0,
                at=T1,
                maturity=EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY,
                reference_id="validated-upgrade",
            ),
        ),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert "maturity differs" in change.reason


def test_semantic_authority_change_is_incomparable() -> None:
    prior = snapshot(obs=(observation(1.0, authority="audited filing metric"),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(
            observation(
                1.0,
                at=T1,
                reference_id="weaker-authority",
                authority="unverified narrative context",
            ),
        ),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert "authority or maturity differs" in change.reason


def test_upstream_reference_maturity_change_is_incomparable() -> None:
    prior_observation = observation(
        1.0,
        maturity=EvidenceMaturity.STRUCTURED_OBSERVATION,
        reference_id="prior-validated",
    )
    prior_observation = replace(
        prior_observation,
        evidence=(
            evidence(
                "prior-validated",
                maturity=EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY,
            ),
        ),
    )
    prior = snapshot(obs=(prior_observation,))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(
            observation(
                1.0,
                at=T1,
                maturity=EvidenceMaturity.STRUCTURED_OBSERVATION,
                reference_id="current-structured",
            ),
        ),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert "authority or maturity differs" in change.reason


def test_cross_snapshot_evidence_id_redefinition_is_rejected() -> None:
    prior = snapshot(obs=(observation(1.0, reference_id="shared-reference"),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(observation(2.0, at=T1, reference_id="shared-reference"),),
    )
    with pytest.raises(ObservableUniverseError, match="change definition"):
        compare_universe_snapshots(prior, current)


def test_observation_chronology_cannot_regress() -> None:
    prior = snapshot(obs=(observation(1.0, at=T0),))
    older = T0 - timedelta(hours=1)
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(observation(2.0, at=older, reference_id="older-evidence"),),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert "chronology regresses" in change.reason


def test_changed_backfill_already_knowable_at_prior_cutoff_is_incomparable() -> None:
    prior = snapshot(1.0, cutoff=T1)
    current = snapshot(
        cutoff=T2,
        version="2",
        obs=(observation(2.0, at=T1, reference_id="late-backfill"),),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert "already knowable" in change.reason


def test_unchanged_carried_forward_observation_remains_unchanged() -> None:
    prior = snapshot(1.0, cutoff=T1)
    current = snapshot(
        cutoff=T2,
        version="2",
        obs=(observation(1.0, at=T1, reference_id="carried-forward"),),
    )
    assert compare_universe_snapshots(prior, current)[0].state is ChangeState.UNCHANGED


def test_member_identity_normalization_pairs_cross_snapshot_slots() -> None:
    prior = snapshot(
        members=(member("ABC", aliases=()),),
        obs=(observation(1.0, member_id="ABC"),),
    )
    current = snapshot(
        cutoff=T1,
        version="2",
        members=(member(" abc ", aliases=()),),
        obs=(observation(2.0, member_id=" abc ", at=T1),),
    )
    changes = compare_universe_snapshots(prior, current)
    assert len(changes) == 1
    assert changes[0].member_id == " abc "
    assert changes[0].state is ChangeState.CHANGED


def test_normalized_member_identity_surfaces_observationless_missing_candidate() -> None:
    prior = snapshot(
        members=(member("ABC", aliases=()),),
        obs=(observation(1.0, member_id="ABC"),),
    )
    current = snapshot(
        cutoff=T1,
        version="2",
        members=(
            member(
                " abc ",
                aliases=(),
                available=(),
                unavailable=("market_return", "consensus"),
            ),
        ),
        obs=(),
    )
    changes = compare_universe_snapshots(prior, current)
    rule = CandidateRule(
        "missing",
        "market_return",
        (ChangeState.NEWLY_MISSING,),
        ResearchPriority.ELEVATED,
        "evidence disappeared",
    )
    candidate = surface_research_candidates(current, changes, (rule,), prior_snapshot=prior)[0]
    assert candidate.member_id == " abc "


def test_integer_delta_remains_exact_beyond_binary64_range() -> None:
    prior = snapshot(obs=(observation(2**53),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(observation(2**53 + 1, at=T1, reference_id="large-integer"),),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.CHANGED
    assert change.delta == 1
    assert type(change.delta) is int


def test_mixed_numeric_encodings_do_not_erase_an_exact_change() -> None:
    prior = snapshot(obs=(observation(2**53 + 1),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(observation(float(2**53), at=T1, reference_id="mixed-number"),),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.CHANGED
    assert change.delta == -1
    assert type(change.delta) is int


@pytest.mark.parametrize(("prior_value", "current_value"), [(1, True), (False, 0.0)])
def test_boolean_numeric_encoding_switch_is_incomparable(
    prior_value: int | float | bool, current_value: int | float | bool
) -> None:
    prior = snapshot(obs=(observation(prior_value),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(observation(current_value, at=T1, reference_id="encoding-switch"),),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.INCOMPARABLE
    assert "scalar encoding changed" in change.reason


def test_opposing_large_floats_produce_an_exact_integer_delta() -> None:
    prior = snapshot(obs=(observation(-1.7e308),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(observation(1.7e308, at=T1, reference_id="large-float"),),
    )
    change = compare_universe_snapshots(prior, current)[0]
    assert change.state is ChangeState.CHANGED
    assert type(change.delta) is int


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
            snapshot(
                obs=(missing0,),
                members=(member(available=(), unavailable=("market_return", "consensus")),),
            ),
            snapshot(cutoff=T1, obs=(available1,), version="2"),
        )[0].state
        is ChangeState.NEWLY_AVAILABLE
    )
    assert (
        compare_universe_snapshots(
            snapshot(obs=(available0,)),
            snapshot(
                cutoff=T1,
                obs=(missing1,),
                version="2",
                members=(member(available=(), unavailable=("market_return", "consensus")),),
            ),
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


def test_observation_cannot_promote_upstream_maturity_or_conflict_with_membership() -> None:
    low_maturity = evidence(
        maturity=EvidenceMaturity.CITED_CONTEXT,
        authority="cited context only",
    )
    with pytest.raises(ObservableUniverseError, match="cannot exceed"):
        replace(
            observation(1.0),
            maturity=EvidenceMaturity.INDEPENDENTLY_VALIDATED_AUTHORITY,
            evidence=(low_maturity,),
        )
    with pytest.raises(ObservableUniverseError, match="availability conflicts"):
        snapshot(
            obs=(observation(1.0, dimension="consensus"),),
            members=(member(available=(), unavailable=("market_return", "consensus")),),
        )


def test_one_reference_id_cannot_have_conflicting_canonical_definitions() -> None:
    first = observation(1.0, member_id="000660", reference_id="shared-reference")
    second = observation(2.0, member_id="005930", reference_id="shared-reference")
    second = replace(
        second,
        evidence=(
            evidence(
                "shared-reference",
                authority="conflicting semantic authority",
            ),
        ),
    )
    members = (
        member("000660", aliases=("Hynix",)),
        member("005930", aliases=("Samsung",)),
    )
    with pytest.raises(ObservableUniverseError, match="conflicting definitions"):
        snapshot(obs=(first, second), members=members)


def test_repeated_identical_evidence_reference_is_unambiguous() -> None:
    observations = (
        observation(1.0, member_id="000660", reference_id="shared-reference"),
        observation(2.0, member_id="005930", reference_id="shared-reference"),
    )
    state = snapshot(
        obs=observations,
        members=(
            member("000660", aliases=("Hynix",)),
            member("005930", aliases=("Samsung",)),
        ),
    )
    assert state.source_evidence_refs == ("shared-reference",)


def test_observation_evidence_requires_canonical_reference_order() -> None:
    with pytest.raises(ObservableUniverseError, match="canonical reference_id order"):
        replace(
            observation(1.0),
            evidence=(evidence("z-reference"), evidence("a-reference")),
        )


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
    prior = snapshot(1.0)
    current = snapshot(3.0, cutoff=T1, version="2")
    changes = compare_universe_snapshots(prior, current)
    rule = CandidateRule(
        "material-return-change",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ELEVATED,
        "material market-state change deserves research",
        minimum_absolute_delta=1.0,
    )
    first = surface_research_candidates(current, changes, (rule,), prior_snapshot=prior)
    second = surface_research_candidates(
        current, tuple(reversed(changes)), (rule,), prior_snapshot=prior
    )
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
    planner_candidate = planner_input(candidate)
    assert planner_candidate.candidate_id == candidate.candidate_id
    assert planner_candidate.priority is ResearchPriority.ELEVATED
    assert planner_candidate.current_snapshot_id == current.snapshot_id
    assert planner_candidate.evaluated_at == T1
    assert planner_candidate.triggering_change_ids == candidate.triggering_change_ids


def test_missing_evidence_never_improves_candidate_and_no_rule_means_no_candidate() -> None:
    prior = snapshot(1.0)
    current = snapshot(2.0, cutoff=T1, version="2")
    changes = compare_universe_snapshots(prior, current)
    assert surface_research_candidates(current, changes, (), prior_snapshot=prior) == ()
    missing_current = snapshot(
        cutoff=T1,
        version="2",
        members=(member(available=(), unavailable=("market_return", "consensus")),),
        obs=(
            observation(
                None,
                at=T1,
                maturity=EvidenceMaturity.UNAVAILABLE,
                unavailable_reason="source failed",
            ),
        ),
    )
    missing_change = compare_universe_snapshots(prior, missing_current)
    positive_only = CandidateRule(
        "changed-only",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.URGENT,
        "measured change",
    )
    assert (
        surface_research_candidates(
            missing_current,
            missing_change,
            (positive_only,),
            prior_snapshot=prior,
        )
        == ()
    )


def test_candidate_changes_must_bind_to_current_snapshot() -> None:
    prior = snapshot(1.0)
    current = snapshot(2.0, cutoff=T1, version="2")
    change = compare_universe_snapshots(prior, current)[0]
    foreign_current = snapshot(3.0, cutoff=T1, version="foreign")
    rule = CandidateRule(
        "changed",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ROUTINE,
        "changed",
    )
    with pytest.raises(ObservableUniverseError, match="bound prior/current"):
        surface_research_candidates(foreign_current, (change,), (rule,), prior_snapshot=prior)


def test_candidate_change_must_bind_to_its_exact_observation_slot() -> None:
    members = (
        member("000660", aliases=("Hynix",)),
        member("005930", aliases=("Samsung",)),
    )
    prior = snapshot(
        members=members,
        obs=(
            observation(1.0),
            observation(1.0, member_id="005930", reference_id="samsung-prior"),
        ),
    )
    current = snapshot(
        cutoff=T1,
        version="2",
        members=members,
        obs=(
            observation(2.0, at=T1),
            observation(
                2.0,
                member_id="005930",
                at=T1,
                reference_id="samsung-current",
            ),
        ),
    )
    change = next(
        item for item in compare_universe_snapshots(prior, current) if item.member_id == "000660"
    )
    forged = replace(change, member_id="005930")
    rule = CandidateRule(
        "changed",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ROUTINE,
        "changed",
    )
    with pytest.raises(ObservableUniverseError, match="bound prior/current"):
        surface_research_candidates(current, (forged,), (rule,), prior_snapshot=prior)


def test_candidate_change_rejects_unbound_current_evidence() -> None:
    prior = snapshot(1.0)
    current = snapshot(2.0, cutoff=T1, version="2")
    change = compare_universe_snapshots(prior, current)[0]
    forged = replace(change, current_evidence_refs=("undeclared-evidence",))
    rule = CandidateRule(
        "changed",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ROUTINE,
        "changed",
    )
    with pytest.raises(ObservableUniverseError, match="bound prior/current"):
        surface_research_candidates(current, (forged,), (rule,), prior_snapshot=prior)


def test_candidate_change_rejects_forged_prior_lineage() -> None:
    prior = snapshot(1.0)
    current = snapshot(2.0, cutoff=T1, version="2")
    change = compare_universe_snapshots(prior, current)[0]
    forged = replace(
        change,
        prior_value=999.0,
        prior_evidence_refs=("nonexistent-prior-evidence",),
    )
    rule = CandidateRule(
        "changed",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ROUTINE,
        "changed",
    )
    with pytest.raises(ObservableUniverseError, match="bound prior/current"):
        surface_research_candidates(current, (forged,), (rule,), prior_snapshot=prior)


def test_candidate_carries_distinct_prior_and_current_evidence() -> None:
    prior = snapshot(obs=(observation(1.0, reference_id="prior-measurement"),))
    current = snapshot(
        cutoff=T1,
        version="2",
        obs=(observation(2.0, at=T1, reference_id="current-measurement"),),
    )
    change = compare_universe_snapshots(prior, current)[0]
    rule = CandidateRule(
        "changed",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ROUTINE,
        "changed",
    )
    candidate = surface_research_candidates(current, (change,), (rule,), prior_snapshot=prior)[0]
    assert candidate.triggering_evidence_refs == (
        "current-measurement",
        "prior-measurement",
    )

    missing_member = member(available=(), unavailable=("market_return", "consensus"))
    missing_current = snapshot(
        cutoff=T1,
        version="missing",
        obs=(),
        members=(missing_member,),
    )
    missing_change = compare_universe_snapshots(prior, missing_current)[0]
    missing_rule = CandidateRule(
        "newly-missing",
        "market_return",
        (ChangeState.NEWLY_MISSING,),
        ResearchPriority.ELEVATED,
        "evidence disappeared",
    )
    missing_candidate = surface_research_candidates(
        missing_current,
        (missing_change,),
        (missing_rule,),
        prior_snapshot=prior,
    )[0]
    assert missing_candidate.triggering_evidence_refs == ("prior-measurement",)


def test_planner_input_carries_concrete_evidence_blockers() -> None:
    prior = snapshot(1.0)
    current = snapshot(
        cutoff=T1,
        version="2",
        members=(member(available=(), unavailable=("market_return", "consensus")),),
        obs=(
            observation(
                None,
                at=T1,
                maturity=EvidenceMaturity.UNAVAILABLE,
                unavailable_reason="provider timeout",
            ),
        ),
    )
    changes = compare_universe_snapshots(prior, current)
    rule = CandidateRule(
        "missing",
        "market_return",
        (ChangeState.NEWLY_MISSING,),
        ResearchPriority.ELEVATED,
        "evidence disappeared",
    )
    candidate = surface_research_candidates(current, changes, (rule,), prior_snapshot=prior)[0]
    assert planner_input(candidate).blocked_evidence == ("provider timeout",)


@pytest.mark.parametrize("variant", ["version", "domain", "membership", "missing"])
def test_change_lineage_binds_snapshot_metadata_even_when_observations_match(
    variant: str,
) -> None:
    prior = snapshot(1.0)
    current = snapshot(2.0, cutoff=T1, version="2")
    change = compare_universe_snapshots(prior, current)[0]
    base_member = current.members[0]
    if variant == "version":
        alternate = replace(current, version="other")
    elif variant == "domain":
        alternate = replace(current, members=(replace(base_member, domain_id="other"),))
    elif variant == "membership":
        alternate = replace(
            current,
            members=(
                base_member,
                UniverseMember(
                    "DOMAIN_ONLY",
                    MemberKind.DOMAIN,
                    domain_id="macro",
                    unavailable_dimensions=("policy",),
                ),
            ),
        )
    else:
        alternate = replace(
            current,
            members=(
                replace(
                    base_member,
                    required_dimensions=("market_return", "consensus", "guidance"),
                    unavailable_dimensions=("consensus", "guidance"),
                ),
            ),
        )
    rule = CandidateRule(
        "changed",
        "market_return",
        (ChangeState.CHANGED,),
        ResearchPriority.ROUTINE,
        "changed",
    )
    with pytest.raises(ObservableUniverseError, match="bound prior/current"):
        surface_research_candidates(alternate, (change,), (rule,), prior_snapshot=prior)


def test_missing_current_observation_still_binds_exact_snapshot() -> None:
    prior = snapshot(1.0)
    missing_member = member(available=(), unavailable=("market_return", "consensus"))
    current = snapshot(cutoff=T1, version="2", obs=(), members=(missing_member,))
    change = compare_universe_snapshots(prior, current)[0]
    assert change.current_observation_id is None
    alternate = replace(current, version="other")
    rule = CandidateRule(
        "missing",
        "market_return",
        (ChangeState.NEWLY_MISSING,),
        ResearchPriority.ELEVATED,
        "evidence disappeared",
    )
    with pytest.raises(ObservableUniverseError, match="bound prior/current"):
        surface_research_candidates(alternate, (change,), (rule,), prior_snapshot=prior)


def test_multiple_rules_deduplicate_one_change_and_preserve_distinct_reasons() -> None:
    prior = snapshot(1.0)
    current = snapshot(3.0, cutoff=T1, version="2")
    change = compare_universe_snapshots(prior, current)[0]
    rules = (
        CandidateRule(
            "a-routine",
            "market_return",
            (ChangeState.CHANGED,),
            ResearchPriority.ROUTINE,
            "price changed",
        ),
        CandidateRule(
            "b-urgent",
            "market_return",
            (ChangeState.CHANGED,),
            ResearchPriority.URGENT,
            "large move requires review",
        ),
    )
    candidate = surface_research_candidates(current, (change,), rules, prior_snapshot=prior)[0]
    assert candidate.triggering_change_ids == (change.change_id,)
    assert len(candidate.measured_reasons) == 2
    assert candidate.priority is ResearchPriority.URGENT


def test_removed_members_do_not_abort_retained_candidates() -> None:
    prior_members = (
        member("000660", aliases=("Hynix",)),
        member("005930", aliases=("Samsung",)),
    )
    prior = snapshot(
        members=prior_members,
        obs=(
            observation(1.0),
            observation(1.0, member_id="005930", reference_id="samsung-prior"),
        ),
    )
    current = snapshot(3.0, cutoff=T1, version="2")
    changes = compare_universe_snapshots(prior, current)
    removed = next(item for item in changes if item.member_id == "005930")
    assert removed.state is ChangeState.NEWLY_MISSING
    assert removed.current_snapshot_id == current.snapshot_id
    rules = (
        CandidateRule(
            "changed",
            "market_return",
            (ChangeState.CHANGED,),
            ResearchPriority.ELEVATED,
            "retained member changed",
        ),
        CandidateRule(
            "missing",
            "market_return",
            (ChangeState.NEWLY_MISSING,),
            ResearchPriority.URGENT,
            "member evidence missing",
        ),
    )
    candidates = surface_research_candidates(current, changes, rules, prior_snapshot=prior)
    assert [item.member_id for item in candidates] == ["000660"]


def test_newly_available_but_old_evidence_is_stale_not_fresh() -> None:
    prior_missing = observation(
        None,
        maturity=EvidenceMaturity.UNAVAILABLE,
        unavailable_reason="not yet available",
    )
    prior = snapshot(
        obs=(prior_missing,),
        members=(member(available=(), unavailable=("market_return", "consensus")),),
    )
    current = snapshot(
        cutoff=T1,
        obs=(observation(2.0, at=T0 + timedelta(hours=1)),),
        version="2",
    )
    change = compare_universe_snapshots(prior, current, stale_after=timedelta(hours=12))[0]
    assert change.state is ChangeState.STALE
    fresh_rule = CandidateRule(
        "fresh",
        "market_return",
        (ChangeState.NEWLY_AVAILABLE,),
        ResearchPriority.ELEVATED,
        "fresh evidence",
    )
    assert (
        surface_research_candidates(
            current,
            (change,),
            (fresh_rule,),
            prior_snapshot=prior,
            stale_after=timedelta(hours=12),
        )
        == ()
    )


def test_newly_declared_unavailable_dimension_emits_a_gap_change() -> None:
    prior = snapshot(1.0)
    current_member = replace(
        member(),
        required_dimensions=("market_return", "consensus", "guidance"),
        unavailable_dimensions=("consensus", "guidance"),
    )
    current = snapshot(1.0, cutoff=T1, version="2", members=(current_member,))
    changes = compare_universe_snapshots(prior, current)
    gap = next(item for item in changes if item.dimension_id == "guidance")
    assert gap.state is ChangeState.NEWLY_MISSING
    assert gap.current_observation_id is None
    rule = CandidateRule(
        "new-gap",
        "guidance",
        (ChangeState.NEWLY_MISSING,),
        ResearchPriority.ELEVATED,
        "new evidence gap",
    )
    candidate = surface_research_candidates(current, changes, (rule,), prior_snapshot=prior)[0]
    assert "guidance" in candidate.missing_dimensions


def test_removed_dimension_does_not_emit_a_false_missing_change() -> None:
    prior = snapshot(1.0)
    current_member = UniverseMember(
        member_id="000660",
        kind=MemberKind.SECURITY,
        domain_id="memory_semiconductor",
        aliases=("SK hynix",),
        required_dimensions=("consensus",),
        available_dimensions=(),
        unavailable_dimensions=("consensus",),
        research_model_status=ResearchModelStatus.DRAFT,
    )
    current = snapshot(cutoff=T1, version="2", members=(current_member,), obs=())
    assert compare_universe_snapshots(prior, current) == ()


def test_negative_staleness_window_is_rejected() -> None:
    with pytest.raises(ObservableUniverseError, match="cannot be negative"):
        compare_universe_snapshots(
            snapshot(1.0),
            snapshot(2.0, cutoff=T1, version="2"),
            stale_after=timedelta(seconds=-1),
        )


def test_public_change_states_only_advertise_emitted_r1a_semantics() -> None:
    assert set(ChangeState) == {
        ChangeState.CHANGED,
        ChangeState.UNCHANGED,
        ChangeState.NEWLY_AVAILABLE,
        ChangeState.NEWLY_MISSING,
        ChangeState.STALE,
        ChangeState.INCOMPARABLE,
    }


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
        current,
        compare_universe_snapshots(prior, current),
        (rule,),
        prior_snapshot=prior,
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
    assert failed.last_successful_cutoff_at == T0
    assert failed.last_successful_snapshot_id == state.snapshot_id
    assert path.exists()  # immutable history remains, but is not current readiness


@pytest.mark.parametrize("target", ["snapshot", "manifest", "pointer", "identity"])
def test_persisted_tampering_fails_closed(tmp_path: Path, target: str) -> None:
    state = snapshot()
    snapshot_path = persist_successful_universe_attempt(
        state, output_root=tmp_path, attempted_at=T0
    )
    current_path = tmp_path / "observable_universe_v1/current.json"
    pointer = json.loads(current_path.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "observable_universe_v1/manifests" / f"{pointer['manifest_id']}.json"
    identity_path = tmp_path / "observable_universe_v1/universe.json"
    path = {
        "snapshot": snapshot_path,
        "manifest": manifest_path,
        "pointer": current_path,
        "identity": identity_path,
    }[target]
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


def test_successful_attempt_cannot_predate_research_cutoff(tmp_path: Path) -> None:
    with pytest.raises(ObservableUniverseError, match="precede the research cutoff"):
        persist_successful_universe_attempt(
            snapshot(cutoff=T1), output_root=tmp_path, attempted_at=T0
        )


def test_store_rejects_switch_to_an_unrelated_universe(tmp_path: Path) -> None:
    original = snapshot()
    persist_successful_universe_attempt(original, output_root=tmp_path, attempted_at=T0)
    unrelated = replace(snapshot(2.0, cutoff=T1, version="2"), universe_id="unrelated-universe")
    with pytest.raises(ObservableUniverseError, match="cannot switch universe identity"):
        persist_successful_universe_attempt(unrelated, output_root=tmp_path, attempted_at=T1)
    current = load_current_universe_state(tmp_path)
    assert current is not None and current.snapshot == original


def test_rejected_stale_success_cannot_bind_an_unclaimed_store(tmp_path: Path) -> None:
    publish_failed_universe_attempt(
        output_root=tmp_path,
        attempted_at=T2,
        failure_code="initial_provider_failure",
    )
    stale = replace(snapshot(1.0, cutoff=T0), universe_id="stale-universe")
    with pytest.raises(ObservableUniverseError, match="cannot move backward"):
        persist_successful_universe_attempt(
            stale,
            output_root=tmp_path,
            attempted_at=T1,
        )
    assert not (tmp_path / "observable_universe_v1/universe.json").exists()
    assert not (
        tmp_path / "observable_universe_v1/snapshots" / f"{stale.snapshot_id}.json"
    ).exists()

    legitimate = replace(
        snapshot(2.0, cutoff=T2, version="2"),
        universe_id="legitimate-universe",
    )
    persist_successful_universe_attempt(
        legitimate,
        output_root=tmp_path,
        attempted_at=T3,
    )
    current = load_current_universe_state(tmp_path)
    assert current is not None and current.snapshot == legitimate


def test_successful_publication_cannot_regress_current_research_cutoff(
    tmp_path: Path,
) -> None:
    newer = snapshot(2.0, cutoff=T1, version="2")
    persist_successful_universe_attempt(newer, output_root=tmp_path, attempted_at=T1)
    publish_failed_universe_attempt(
        output_root=tmp_path,
        attempted_at=T2,
        failure_code="provider_timeout",
    )
    older = snapshot(1.0, cutoff=T0, version="1")
    with pytest.raises(ObservableUniverseError, match="regress.*research cutoff"):
        persist_successful_universe_attempt(older, output_root=tmp_path, attempted_at=T3)
    current = load_current_universe_state(tmp_path)
    assert current is not None
    assert current.status is AttemptStatus.FAILED
    assert current.last_successful_cutoff_at == T1
    assert current.last_successful_snapshot_id == newer.snapshot_id


def test_failed_pointer_reconstructs_its_success_watermark(tmp_path: Path) -> None:
    state = snapshot()
    snapshot_path = persist_successful_universe_attempt(
        state, output_root=tmp_path, attempted_at=T0
    )
    publish_failed_universe_attempt(
        output_root=tmp_path,
        attempted_at=T1,
        failure_code="provider_timeout",
    )
    snapshot_path.unlink()
    with pytest.raises(ObservableUniverseError, match="cannot read snapshot"):
        load_current_universe_state(tmp_path)


def test_pointer_replace_fsyncs_publication_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[Path] = []
    monkeypatch.setattr(observable_module, "_fsync_directory", synced.append)
    observable_module._atomic_replace(tmp_path / "current.json", b"{}")
    assert synced == [tmp_path]


def test_new_publication_directories_fsync_each_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synced: list[Path] = []
    monkeypatch.setattr(observable_module, "_fsync_directory", synced.append)
    observable_root = tmp_path / "observable_universe_v1"
    observable_module._mkdir_durable(observable_root / "snapshots")
    assert synced == [tmp_path, observable_root]


def test_replay_rejects_attempt_that_predates_selected_snapshot_cutoff(
    tmp_path: Path,
) -> None:
    persist_successful_universe_attempt(snapshot(cutoff=T1), output_root=tmp_path, attempted_at=T1)
    current_path = tmp_path / "observable_universe_v1/current.json"
    pointer = json.loads(current_path.read_text(encoding="utf-8"))
    pointer["attempted_at"] = T0.isoformat()
    pointer["attempt_id"] = content_id(
        {
            "status": pointer["status"],
            "attempted_at": pointer["attempted_at"],
            "snapshot_id": pointer["snapshot_id"],
            "manifest_id": pointer["manifest_id"],
        }
    )
    pointer_without_id = dict(pointer)
    del pointer_without_id["pointer_id"]
    pointer["pointer_id"] = content_id(pointer_without_id)
    current_path.write_text(
        json.dumps(pointer, allow_nan=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ObservableUniverseError, match="predates.*research cutoff"):
        load_current_universe_state(tmp_path)


def test_replay_rejects_failed_attempt_that_predates_success_watermark(
    tmp_path: Path,
) -> None:
    persist_successful_universe_attempt(snapshot(cutoff=T1), output_root=tmp_path, attempted_at=T1)
    publish_failed_universe_attempt(
        output_root=tmp_path,
        attempted_at=T2,
        failure_code="provider_timeout",
    )
    current_path = tmp_path / "observable_universe_v1/current.json"
    pointer = json.loads(current_path.read_text(encoding="utf-8"))
    pointer["attempted_at"] = T0.isoformat()
    pointer["attempt_id"] = content_id(
        {
            "status": pointer["status"],
            "attempted_at": pointer["attempted_at"],
            "failure_code": pointer["failure_code"],
        }
    )
    pointer_without_id = dict(pointer)
    del pointer_without_id["pointer_id"]
    pointer["pointer_id"] = content_id(pointer_without_id)
    current_path.write_text(
        json.dumps(pointer, allow_nan=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ObservableUniverseError, match="predates.*successful cutoff"):
        load_current_universe_state(tmp_path)


def test_immutable_install_failure_leaves_no_partial_artifact_and_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = snapshot()
    snapshot_path = tmp_path / "observable_universe_v1/snapshots" / f"{state.snapshot_id}.json"
    real_link = observable_module.os.link
    calls = 0

    def fail_snapshot_link(source: str | bytes, destination: str | bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected immutable install failure")
        real_link(source, destination)

    monkeypatch.setattr(observable_module.os, "link", fail_snapshot_link)
    with pytest.raises(OSError, match="injected immutable install failure"):
        persist_successful_universe_attempt(state, output_root=tmp_path, attempted_at=T0)

    assert not snapshot_path.exists()
    assert load_current_universe_state(tmp_path) is None

    monkeypatch.setattr(observable_module.os, "link", real_link)
    assert (
        persist_successful_universe_attempt(state, output_root=tmp_path, attempted_at=T0)
        == snapshot_path
    )
    current = load_current_universe_state(tmp_path)
    assert current is not None and current.ready and current.snapshot == state


def test_immutable_writer_rejects_a_symlink_artifact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b"expected")
    real_is_symlink = Path.is_symlink

    def report_target_as_symlink(path: Path) -> bool:
        return path == artifact or real_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", report_target_as_symlink)
    with pytest.raises(ObservableUniverseError, match="cannot be a symlink"):
        observable_module._write_immutable(artifact, b"expected")


def test_later_failure_wins_when_it_races_an_older_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered_success_write = threading.Event()
    attempted_failure_publish = threading.Event()
    release_success_write = threading.Event()
    real_write_immutable = observable_module._write_immutable
    real_lock = observable_module.exclusive_research_ledger_write_lock
    blocked_once = False
    lock_attempts = 0

    def note_lock_attempt(root: str | Path) -> AbstractContextManager[None]:
        nonlocal lock_attempts
        lock_attempts += 1
        if lock_attempts >= 2:
            attempted_failure_publish.set()
        return real_lock(root)

    def block_first_immutable_write(path: Path, content: bytes) -> None:
        nonlocal blocked_once
        if not blocked_once:
            blocked_once = True
            entered_success_write.set()
            assert release_success_write.wait(timeout=5)
        real_write_immutable(path, content)

    monkeypatch.setattr(observable_module, "_write_immutable", block_first_immutable_write)
    monkeypatch.setattr(
        observable_module,
        "exclusive_research_ledger_write_lock",
        note_lock_attempt,
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        success = pool.submit(
            persist_successful_universe_attempt,
            snapshot(),
            output_root=tmp_path,
            attempted_at=T0,
        )
        assert entered_success_write.wait(timeout=5)
        failure = pool.submit(
            publish_failed_universe_attempt,
            output_root=tmp_path,
            attempted_at=T1,
            failure_code="provider_timeout",
        )
        assert attempted_failure_publish.wait(timeout=5)
        release_success_write.set()
        success.result(timeout=5)
        failure.result(timeout=5)

    current = load_current_universe_state(tmp_path)
    assert current is not None
    assert current.status is AttemptStatus.FAILED
    assert current.attempted_at == T1
    assert current.snapshot is None
