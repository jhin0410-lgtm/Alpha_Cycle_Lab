from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import InvestmentThesisSnapshot
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
    ResearchRoundSnapshot,
    ResearchRoundStatus,
    ResearchSecurityPackage,
    persist_research_round,
    run_research_round,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
NOW = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 22)


def _fake_thesis(security_id: str, snapshot_id: str) -> InvestmentThesisSnapshot:
    value = SimpleNamespace(
        security_id=security_id,
        snapshot_id=snapshot_id,
        captured_at=NOW,
        horizon_trading_days=120,
    )
    return cast(InvestmentThesisSnapshot, value)


def _ready_snapshot() -> ResearchRoundSnapshot:
    guardrail = load_decision_system_v21_guardrails().evidence_id
    return ResearchRoundSnapshot(
        round_id="round-ready",
        mode=ResearchRoundMode.PROSPECTIVE,
        status=ResearchRoundStatus.PROSPECTIVE_READY_FOR_REGISTRATION,
        captured_at=NOW,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=("000660", "005930"),
        thesis_snapshot_ids=(SHA_A, SHA_B),
        underwriting_snapshot_ids=(SHA_C, SHA_D),
        payoff_surface_snapshot_ids=("1" * 64, "2" * 64),
        decision_view_snapshot_ids=(),
        expectation_gap_snapshot_ids=(),
        opportunity_candidate_snapshot_ids=("3" * 64, "4" * 64),
        opportunity_set_snapshot_id="5" * 64,
        expectation_overlay_snapshot_id=None,
        prospective_registration_snapshot_id=None,
        comparable_security_ids=("000660", "005930"),
        base_pareto_frontier_security_ids=("000660", "005930"),
        expectation_pareto_frontier_security_ids=(),
        blockers=(),
        flags=("expectation_overlay_not_requested",),
        guardrail_evidence_id=guardrail,
    )


def test_blocker_rejects_non_sha_snapshot_reference() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        ResearchRoundBlocker(
            component="underwriter",
            code="bad_ref",
            detail="invalid snapshot reference",
            snapshot_id="not-a-sha",
        )


def test_blocked_round_requires_explicit_blocker() -> None:
    guardrail = load_decision_system_v21_guardrails().evidence_id
    with pytest.raises(ValueError, match="requires at least one blocker"):
        ResearchRoundSnapshot(
            round_id="round-blocked",
            mode=ResearchRoundMode.PROSPECTIVE,
            status=ResearchRoundStatus.PROSPECTIVE_BLOCKED,
            captured_at=NOW,
            evaluation_date=EVALUATION_DATE,
            horizon_trading_days=120,
            security_ids=("000660", "005930"),
            thesis_snapshot_ids=(SHA_A, SHA_B),
            underwriting_snapshot_ids=(),
            payoff_surface_snapshot_ids=(),
            decision_view_snapshot_ids=(),
            expectation_gap_snapshot_ids=(),
            opportunity_candidate_snapshot_ids=(),
            opportunity_set_snapshot_id=None,
            expectation_overlay_snapshot_id=None,
            prospective_registration_snapshot_id=None,
            comparable_security_ids=(),
            base_pareto_frontier_security_ids=(),
            expectation_pareto_frontier_security_ids=(),
            blockers=(),
            flags=(),
            guardrail_evidence_id=guardrail,
        )


def test_registered_status_requires_registration_snapshot() -> None:
    ready = _ready_snapshot()
    with pytest.raises(ValueError, match="requires registration snapshot"):
        ResearchRoundSnapshot(
            **{
                **ready.__dict__,
                "status": ResearchRoundStatus.PROSPECTIVE_REGISTERED,
            }
        )


def test_missing_typed_sources_become_structured_blockers() -> None:
    packages = (
        ResearchSecurityPackage(thesis=_fake_thesis("000660", SHA_A)),
        ResearchSecurityPackage(thesis=_fake_thesis("005930", SHA_B)),
    )
    artifacts = run_research_round(
        packages,
        round_id="repo-evidence-only-blocker-round",
        mode=ResearchRoundMode.PROSPECTIVE,
        captured_at=NOW,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
    )

    assert artifacts.snapshot.status is ResearchRoundStatus.PROSPECTIVE_BLOCKED
    codes = {item.code for item in artifacts.snapshot.blockers}
    assert "underwriting_snapshot_missing" in codes
    assert "payoff_surface_missing" in codes
    assert "opportunity_candidate_coverage_incomplete" in codes
    assert artifacts.opportunity_set is None
    assert artifacts.prospective_registration is None
    assert "expectation_overlay_not_requested" in artifacts.snapshot.flags


def test_round_rejects_future_thesis_by_cutoff() -> None:
    future = cast(
        InvestmentThesisSnapshot,
        SimpleNamespace(
            security_id="000660",
            snapshot_id=SHA_A,
            captured_at=datetime(2026, 8, 23, 0, 0, tzinfo=UTC),
            horizon_trading_days=120,
        ),
    )
    packages = (
        ResearchSecurityPackage(thesis=future),
        ResearchSecurityPackage(thesis=_fake_thesis("005930", SHA_B)),
    )
    artifacts = run_research_round(
        packages,
        round_id="pit-cutoff-round",
        mode=ResearchRoundMode.REPLAY,
        captured_at=NOW,
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
    )
    codes = {item.code for item in artifacts.snapshot.blockers}
    assert "thesis_after_round_cutoff" in codes
    assert artifacts.snapshot.status is ResearchRoundStatus.REPLAY_BLOCKED


def test_payload_keeps_decision_boundaries_disabled() -> None:
    payload = _ready_snapshot().payload_without_id()
    assert payload["point_in_time_fail_closed"] is True
    assert payload["missing_evidence_neutralized"] is False
    assert payload["research_logic_reimplemented"] is False
    assert payload["automatic_investable_now_transition_enabled"] is False
    assert payload["target_price_enabled"] is False
    assert payload["optimal_position_size_enabled"] is False
    assert payload["portfolio_recommendation_enabled"] is False
    assert payload["automatic_execution_enabled"] is False
    assert payload["future_outcome_claimed"] is False


def test_persistence_is_immutable(tmp_path) -> None:
    snapshot = _ready_snapshot()
    path = persist_research_round(snapshot, output_root=tmp_path)
    assert path.exists()
    assert snapshot.snapshot_id in path.name
    with pytest.raises(FileExistsError):
        persist_research_round(snapshot, output_root=tmp_path)
