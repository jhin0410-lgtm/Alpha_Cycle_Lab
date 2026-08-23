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
from alpha_cycle.investment_thesis_repository_v2_1 import InvestmentThesisRepositoryError
from alpha_cycle.research_package_integrity_v2_1 import (
    ResearchPackageIntegrityError,
    decision_view_matches_underwriting_tournament,
    package_integrity_blocker_codes,
    validate_persisted_opportunity_candidate,
    validate_preflight_selection_timing,
    validate_publication_layout,
    validate_thesis_repository_layout,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64


def test_selected_forecast_id_must_pair_with_selected_snapshot() -> None:
    view = SimpleNamespace(
        security_id="000660",
        target_variable="net_income",
        target_date=date(2026, 12, 31),
        unit="KRW_million",
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        tournament_forecast_snapshot_ids=(A, B),
        selected_forecast_snapshot_id=A,
        selected_forecast_id="forecast-b",
    )
    tournament = SimpleNamespace(
        comparable=True,
        security_id=view.security_id,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        forecast_origin=view.forecast_origin,
        information_cutoff=view.information_cutoff,
        forecast_snapshot_ids=(A, B),
        forecast_ids=("forecast-a", "forecast-b"),
    )
    underwriting = SimpleNamespace(forecast_tournament=tournament)

    assert decision_view_matches_underwriting_tournament(view, underwriting) is False


def test_terminal_thesis_status_is_blocked() -> None:
    thesis = SimpleNamespace(status=ThesisStatus.INVALIDATED, captured_at=NOW)

    blockers = package_integrity_blocker_codes(thesis, None, None, None, None)

    assert "terminal_thesis_status" in blockers


def test_thesis_payoff_underwriting_capture_order_is_blocked() -> None:
    thesis = SimpleNamespace(status=ThesisStatus.UNDERWRITING, captured_at=NOW)
    payoff = SimpleNamespace(snapshot_id=A, captured_at=NOW - timedelta(minutes=2))
    underwriting = SimpleNamespace(
        payoff_surface_snapshot_id=A,
        captured_at=NOW - timedelta(minutes=1),
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
    view = SimpleNamespace(
        unit="KRW_million",
        selected_forecast_value=20_000_000.0,
    )
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
