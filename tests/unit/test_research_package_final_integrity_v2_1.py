from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence.decision_thesis_v2 import ThesisStatus
from alpha_cycle.intelligence.opportunity_set_v2_1 import (
    OpportunityCandidateSnapshot,
    OpportunityResearchClass,
    persist_opportunity_candidate,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    UnderwritingLane,
    UnderwritingReadiness,
)
from alpha_cycle.investment_thesis_repository_v2_1 import InvestmentThesisRepositoryError
from alpha_cycle.research_package_integrity_v2_1 import (
    ResearchPackageIntegrityError,
    decision_view_matches_underwriting_tournament,
    package_integrity_blocker_codes,
    require_trusted_artifact_root,
    validate_persisted_opportunity_candidate,
    validate_preflight_selection_timing,
    validate_publication_layout,
    validate_thesis_repository_layout,
)
from alpha_cycle.research_preflight_state_v2_1 import (
    ResearchPreflightStateError,
    load_current_research_thesis_preflight_states,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


def _view() -> SimpleNamespace:
    return SimpleNamespace(
        captured_at=NOW,
        security_id="000660",
        target_variable="net_income",
        target_date=date(2026, 12, 31),
        unit="KRW_million",
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        tournament_forecast_snapshot_ids=(A, B),
        selected_forecast_snapshot_id=A,
        selected_forecast_id="forecast-a",
        selected_forecast_value=20_000_000.0,
    )


def _tournament(view: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        comparable=True,
        security_id=view.security_id,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        forecast_origin=view.forecast_origin,
        information_cutoff=view.information_cutoff,
        primary_error_metric="absolute_error",
        forecast_snapshot_ids=(A, B),
        forecast_ids=("forecast-a", "forecast-b"),
        distinct_forecaster_count=2,
        dependency_cluster_count=2,
        blockers=(),
    )


def test_selected_forecast_id_must_pair_with_selected_snapshot() -> None:
    view = _view()
    view.selected_forecast_id = "forecast-b"
    underwriting = SimpleNamespace(forecast_tournament=_tournament(view))

    assert decision_view_matches_underwriting_tournament(view, underwriting) is False


def test_comparable_tournament_requires_multiple_distinct_forecasts() -> None:
    view = _view()
    view.tournament_forecast_snapshot_ids = (A,)
    tournament = _tournament(view)
    tournament.forecast_snapshot_ids = (A,)
    tournament.forecast_ids = ("forecast-a",)
    tournament.distinct_forecaster_count = 1
    tournament.dependency_cluster_count = 1
    underwriting = SimpleNamespace(forecast_tournament=tournament)

    assert decision_view_matches_underwriting_tournament(view, underwriting) is False


def test_future_information_cutoff_is_rejected() -> None:
    view = _view()
    view.information_cutoff = NOW + timedelta(minutes=1)
    tournament = _tournament(view)
    tournament.information_cutoff = view.information_cutoff
    underwriting = SimpleNamespace(forecast_tournament=tournament)

    assert decision_view_matches_underwriting_tournament(view, underwriting) is False


def test_terminal_thesis_status_is_blocked() -> None:
    thesis = SimpleNamespace(status=ThesisStatus.INVALIDATED, captured_at=NOW)

    blockers = package_integrity_blocker_codes(thesis, None, None, None, None)

    assert "terminal_thesis_status" in blockers


def test_ready_underwriting_requires_complete_lane_evidence_contract() -> None:
    thesis = SimpleNamespace(status=ThesisStatus.UNDERWRITING, captured_at=NOW)
    underwriting = SimpleNamespace(
        captured_at=NOW,
        lane=UnderwritingLane.DEEP,
        readiness=UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
        required_elements_satisfied=(),
        required_elements_missing=(),
        blockers=(),
    )

    blockers = package_integrity_blocker_codes(
        thesis,
        underwriting,
        None,
        None,
        None,
    )

    assert "underwriting_ready_evidence_contract_mismatch" in blockers


def test_thesis_payoff_underwriting_capture_order_is_blocked() -> None:
    thesis = SimpleNamespace(status=ThesisStatus.UNDERWRITING, captured_at=NOW)
    payoff = SimpleNamespace(snapshot_id=A, captured_at=NOW - timedelta(minutes=2))
    underwriting = SimpleNamespace(
        payoff_surface_snapshot_id=A,
        captured_at=NOW - timedelta(minutes=1),
        readiness=UnderwritingReadiness.DEEP_LANE_BLOCKED,
    )

    blockers = package_integrity_blocker_codes(
        thesis,
        underwriting,
        payoff,
        None,
        None,
    )

    assert "thesis_payoff_capture_order_mismatch" in blockers
    assert "thesis_underwriting_capture_order_mismatch" in blockers


def test_gap_observation_must_match_selected_decision_view() -> None:
    view = _view()
    observation = SimpleNamespace(
        observed_at=NOW - timedelta(minutes=1),
        unit="KRW_million",
        decision_value=19_000_000.0,
        consensus_value=18_000_000.0,
        absolute_gap=1_000_000.0,
        relative_gap=1_000_000.0 / 18_000_000.0,
    )
    gap = SimpleNamespace(
        captured_at=NOW,
        evaluation_date=date(2026, 8, 23),
        consensus_gaps=(observation,),
        price_implied_gaps=(),
    )
    thesis = SimpleNamespace(status=ThesisStatus.UNDERWRITING, captured_at=NOW)

    blockers = package_integrity_blocker_codes(thesis, None, None, view, gap)

    assert "decision_gap_observation_binding_mismatch" in blockers


def test_consensus_observation_after_evaluation_date_is_rejected() -> None:
    view = _view()
    observation = SimpleNamespace(
        observed_at=NOW,
        unit=view.unit,
        decision_value=view.selected_forecast_value,
        consensus_value=18_000_000.0,
        absolute_gap=2_000_000.0,
        relative_gap=2_000_000.0 / 18_000_000.0,
    )
    gap = SimpleNamespace(
        captured_at=NOW + timedelta(hours=1),
        evaluation_date=date(2026, 8, 22),
        consensus_gaps=(observation,),
        price_implied_gaps=(),
    )
    thesis = SimpleNamespace(status=ThesisStatus.UNDERWRITING, captured_at=NOW)

    blockers = package_integrity_blocker_codes(thesis, None, None, view, gap)

    assert "decision_gap_observation_binding_mismatch" in blockers


def test_preflight_selection_cannot_precede_research_cutoff() -> None:
    current = SimpleNamespace(
        selected_at=NOW,
        state=SimpleNamespace(research_cutoff_at=NOW + timedelta(minutes=1)),
    )

    with pytest.raises(
        ResearchPackageIntegrityError,
        match="cannot precede research cutoff",
    ):
        validate_preflight_selection_timing(
            current,
            processed_at=NOW + timedelta(minutes=2),
        )


def test_missing_artifact_root_rejects_symlink_ancestor(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    root = alias / "new-artifact-root"

    with pytest.raises(
        ResearchPackageIntegrityError,
        match="symlinked path component",
    ):
        require_trusted_artifact_root(root)


def test_thesis_repository_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "investment_thesis_v2_1").symlink_to(
        outside,
        target_is_directory=True,
    )

    with pytest.raises(
        InvestmentThesisRepositoryError,
        match="repository root cannot be a symlink",
    ):
        validate_thesis_repository_layout(tmp_path)


def test_preflight_repository_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "research_request_preflight_current_v2_1").symlink_to(
        outside,
        target_is_directory=True,
    )

    with pytest.raises(
        ResearchPreflightStateError,
        match="preflight-current repository cannot be a symlink",
    ):
        load_current_research_thesis_preflight_states(tmp_path)


def test_publication_repository_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "opportunity_candidate").symlink_to(
        outside,
        target_is_directory=True,
    )
    artifacts = SimpleNamespace(
        opportunity_candidates=(),
        opportunity_set=None,
        snapshot=SimpleNamespace(snapshot_id=A),
    )
    run = SimpleNamespace(snapshot_id=B)
    ledger = SimpleNamespace(snapshot_id=C)

    with pytest.raises(
        ResearchPackageIntegrityError,
        match="opportunity_candidate repository cannot be a symlink",
    ):
        validate_publication_layout(
            tmp_path,
            artifacts=artifacts,
            run=run,
            ledger=ledger,
        )


def test_existing_research_round_collision_is_non_destructive(tmp_path: Path) -> None:
    round_root = tmp_path / "research_round_v2_1"
    round_root.mkdir()
    round_path = round_root / f"{A}.json"
    round_path.write_text('{"preexisting": true}\n', encoding="utf-8")
    before = round_path.read_bytes()
    artifacts = SimpleNamespace(
        opportunity_candidates=(),
        opportunity_set=None,
        snapshot=SimpleNamespace(snapshot_id=A),
    )
    run = SimpleNamespace(snapshot_id=B)
    ledger = SimpleNamespace(snapshot_id=C)

    with pytest.raises(
        ResearchPackageIntegrityError,
        match="research round artifact already exists",
    ):
        validate_publication_layout(
            tmp_path,
            artifacts=artifacts,
            run=run,
            ledger=ledger,
        )

    assert round_path.read_bytes() == before


def _candidate() -> OpportunityCandidateSnapshot:
    return OpportunityCandidateSnapshot(
        captured_at=NOW,
        evaluation_date=date(2026, 8, 23),
        security_id="000660",
        thesis_snapshot_id=A,
        underwriting_readiness_snapshot_id=B,
        payoff_surface_snapshot_id=C,
        horizon_trading_days=120,
        research_class=OpportunityResearchClass.DEEP_READY,
        bear_return_lower=-0.2,
        base_return_lower=0.1,
        base_return_upper=0.3,
        bull_return_upper=0.6,
        nearest_catalyst_id="earnings",
        nearest_catalyst_days=10,
        nearest_catalyst_evidence_refs=("calendar:evidence",),
        comparison_blockers=(),
        flags=(),
        guardrail_evidence_id=D,
    )


def test_corrupt_existing_opportunity_artifact_is_rejected(tmp_path: Path) -> None:
    candidate = _candidate()
    persist_opportunity_candidate(candidate, output_root=tmp_path)
    timestamp = candidate.captured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = (
        tmp_path
        / "opportunity_candidate"
        / f"{timestamp}__{candidate.snapshot_id[:12]}"
    )
    payload_path = directory / "opportunity_candidate.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["base_return_upper"] = 9.99
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ResearchPackageIntegrityError,
        match="payload disagrees",
    ):
        validate_persisted_opportunity_candidate(
            tmp_path,
            candidate,
            require_pointer=False,
        )
