from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

import alpha_cycle.investment_thesis_repository_v2_1 as thesis_repository
from alpha_cycle.intelligence.decision_thesis_v2 import (
    ClaimDirection,
    EpistemicStatus,
    InvestmentThesisSnapshot,
    ThesisClaim,
    ThesisStatus,
    ThesisUncertainty,
    UncertaintyDimension,
    UncertaintyLevel,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import ResearchRoundMode
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.investment_thesis_repository_v2_1 import (
    InvestmentThesisRepositoryError,
    find_latest_investment_thesis,
    load_investment_thesis,
    persist_investment_thesis,
)
from alpha_cycle.research_observatory_v2_1 import load_latest_observatory_state
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request
from alpha_cycle.research_request_preflight_v2_1 import preflight_pending_request_theses

NOW = datetime(2026, 8, 23, 6, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 23)
LEGACY_SHARED_LOCK = ".research_request_intake.lock"


def _uncertainty() -> ThesisUncertainty:
    dimension = UncertaintyDimension(
        level=UncertaintyLevel.HIGH,
        rationale="P2 regression fixture uncertainty.",
    )
    return ThesisUncertainty(
        evidence=dimension,
        model=dimension,
        regime=dimension,
        expectation=dimension,
        catalyst=dimension,
        valuation=dimension,
    )


def _thesis(
    security_id: str = "000660",
    *,
    version: int = 1,
    parent_snapshot_id: str | None = None,
    captured_at: datetime = NOW,
    thesis_id: str | None = None,
) -> InvestmentThesisSnapshot:
    return InvestmentThesisSnapshot(
        thesis_id=thesis_id or f"thesis-{security_id}",
        snapshot_version=version,
        parent_snapshot_id=parent_snapshot_id,
        captured_at=captured_at,
        security_id=security_id,
        horizon_trading_days=120,
        variant_view="Research priority only.",
        why_now="P2 regression coverage.",
        claims=(
            ThesisClaim(
                claim_id="claim-1",
                category="industry_cycle",
                statement="Prospective transmission remains uncertain.",
                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
                direction=ClaimDirection.MIXED,
            ),
        ),
        catalysts=(),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=(),
        first_rejection_risk="The proposed mechanism may fail.",
        portfolio_overlap=(),
        opportunity_set_refs=(),
        status=ThesisStatus.RESEARCH_PRIORITY,
    )


def _record_request(
    tmp_path,
    *,
    request_id: str = "p2-request",
    security_ids: tuple[str, ...] = ("000660",),
    recorded_at: datetime | None = None,
    mode: ResearchRoundMode = ResearchRoundMode.PROSPECTIVE,
):
    return record_analysis_request(
        request_id=request_id,
        requested_at=NOW,
        recorded_at=recorded_at or NOW + timedelta(seconds=1),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=security_ids,
        mode=mode,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Exercise P2 integrity boundaries.",
        artifact_root=tmp_path,
    )


def test_unknown_thesis_field_cannot_bypass_content_address_tamper_detection(tmp_path) -> None:
    thesis = _thesis()
    path = persist_investment_thesis(thesis, artifact_root=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unknown_future_field"] = {"silently_ignored_before_fix": True}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvestmentThesisRepositoryError, match="persisted payload"):
        load_investment_thesis(path)


def test_nested_unknown_thesis_field_also_changes_content_address(tmp_path) -> None:
    thesis = _thesis()
    path = persist_investment_thesis(thesis, artifact_root=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["claims"][0]["unknown_claim_field"] = "must-not-be-ignored"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InvestmentThesisRepositoryError, match="persisted payload"):
        load_investment_thesis(path)


def test_thesis_publish_is_not_discoverable_until_complete_atomic_link(
    tmp_path, monkeypatch
) -> None:
    thesis = _thesis()
    real_link = thesis_repository.os.link
    observed_before_publish = False

    def guarded_link(src, dst) -> None:
        nonlocal observed_before_publish
        observed_before_publish = True
        directory = tmp_path / "investment_thesis_v2_1"
        assert not list(directory.glob("*.json"))
        assert (
            find_latest_investment_thesis(
                tmp_path,
                security_id="000660",
                horizon_trading_days=120,
                as_of=NOW + timedelta(minutes=1),
            )
            is None
        )
        real_link(src, dst)

    monkeypatch.setattr(thesis_repository.os, "link", guarded_link)
    path = persist_investment_thesis(thesis, artifact_root=tmp_path)

    assert observed_before_publish is True
    assert load_investment_thesis(path) == thesis
    assert not list((tmp_path / "investment_thesis_v2_1").glob("*.tmp"))


def test_backdated_preflight_cannot_append_ledger_older_than_current_head(tmp_path) -> None:
    receipt = _record_request(tmp_path, recorded_at=NOW + timedelta(seconds=10))

    with pytest.raises(ValueError, match="latest ledger built_at"):
        preflight_pending_request_theses(
            request_id=receipt.request.request_id,
            run_id="backdated-preflight",
            processed_at=NOW + timedelta(seconds=5),
            artifact_root=tmp_path,
        )

    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert state.ledger.snapshot_id == receipt.ledger.snapshot_id
    assert state.ledger.summary.run_count == 0


def test_duplicate_security_ids_are_rejected_at_intake(tmp_path) -> None:
    with pytest.raises(ValueError, match="security_ids cannot contain duplicates"):
        _record_request(
            tmp_path,
            request_id="duplicate-securities",
            security_ids=("000660", "000660"),
        )

    assert not (tmp_path / "analysis_request_v2_1").exists()
    assert not (tmp_path / "research_run_ledger_v2_1").exists()


def test_orphan_thesis_parent_cannot_be_selected_as_latest(tmp_path) -> None:
    orphan = _thesis(
        version=2,
        parent_snapshot_id="a" * 64,
        captured_at=NOW + timedelta(minutes=1),
    )
    persist_investment_thesis(orphan, artifact_root=tmp_path)

    with pytest.raises(InvestmentThesisRepositoryError, match="parent artifact is missing"):
        find_latest_investment_thesis(
            tmp_path,
            security_id="000660",
            horizon_trading_days=120,
            as_of=NOW + timedelta(minutes=2),
        )


def test_cross_security_thesis_parent_cannot_satisfy_lineage(tmp_path) -> None:
    foreign_parent = _thesis(
        security_id="005930",
        thesis_id="shared-thesis-id",
        captured_at=NOW,
    )
    child = _thesis(
        security_id="000660",
        thesis_id="shared-thesis-id",
        version=2,
        parent_snapshot_id=foreign_parent.snapshot_id,
        captured_at=NOW + timedelta(minutes=1),
    )
    persist_investment_thesis(foreign_parent, artifact_root=tmp_path)
    persist_investment_thesis(child, artifact_root=tmp_path)

    with pytest.raises(InvestmentThesisRepositoryError, match="different thesis identity"):
        find_latest_investment_thesis(
            tmp_path,
            security_id="000660",
            horizon_trading_days=120,
            as_of=NOW + timedelta(minutes=2),
        )


def test_thesis_lineage_requires_immediate_version_progression(tmp_path) -> None:
    parent = _thesis(captured_at=NOW)
    child = _thesis(
        version=3,
        parent_snapshot_id=parent.snapshot_id,
        captured_at=NOW + timedelta(minutes=1),
    )
    persist_investment_thesis(parent, artifact_root=tmp_path)
    persist_investment_thesis(child, artifact_root=tmp_path)

    with pytest.raises(InvestmentThesisRepositoryError, match="immediately precede"):
        find_latest_investment_thesis(
            tmp_path,
            security_id="000660",
            horizon_trading_days=120,
            as_of=NOW + timedelta(minutes=2),
        )


def test_forked_thesis_lineage_is_rejected_instead_of_silently_selecting_branch(tmp_path) -> None:
    parent = _thesis(captured_at=NOW)
    branch_a = replace(
        _thesis(
            version=2,
            parent_snapshot_id=parent.snapshot_id,
            captured_at=NOW + timedelta(minutes=1),
        ),
        why_now="fork branch A",
    )
    branch_b = replace(
        _thesis(
            version=2,
            parent_snapshot_id=parent.snapshot_id,
            captured_at=NOW + timedelta(minutes=2),
        ),
        why_now="fork branch B",
    )
    persist_investment_thesis(parent, artifact_root=tmp_path)
    persist_investment_thesis(branch_a, artifact_root=tmp_path)
    persist_investment_thesis(branch_b, artifact_root=tmp_path)

    with pytest.raises(InvestmentThesisRepositoryError, match="forked"):
        find_latest_investment_thesis(
            tmp_path,
            security_id="000660",
            horizon_trading_days=120,
            as_of=NOW + timedelta(minutes=3),
        )


def test_replay_preflight_requires_explicit_historical_research_cutoff(tmp_path) -> None:
    receipt = _record_request(tmp_path, mode=ResearchRoundMode.REPLAY)

    with pytest.raises(ValueError, match="requires an explicit research_cutoff_at"):
        preflight_pending_request_theses(
            request_id=receipt.request.request_id,
            run_id="replay-no-cutoff",
            processed_at=NOW + timedelta(minutes=1),
            artifact_root=tmp_path,
        )


def test_replay_preflight_uses_historical_cutoff_not_processing_time(tmp_path) -> None:
    receipt = _record_request(tmp_path, mode=ResearchRoundMode.REPLAY)
    cutoff = NOW - timedelta(days=30)
    historical = _thesis(captured_at=cutoff - timedelta(minutes=1))
    later = replace(
        _thesis(
            version=2,
            parent_snapshot_id=historical.snapshot_id,
            captured_at=cutoff + timedelta(minutes=1),
        ),
        why_now="captured after replay cutoff",
    )
    persist_investment_thesis(historical, artifact_root=tmp_path)
    persist_investment_thesis(later, artifact_root=tmp_path)

    preflight = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="historical-replay",
        processed_at=NOW + timedelta(minutes=1),
        research_cutoff_at=cutoff,
        artifact_root=tmp_path,
    )

    assert preflight.ready_for_package_assembly is True
    assert preflight.research_cutoff_at == cutoff
    assert preflight.thesis_snapshots == (historical,)
    assert later.snapshot_id not in preflight.payload()["thesis_snapshot_ids"]


def test_prospective_preflight_rejects_cutoff_before_request_time(tmp_path) -> None:
    receipt = _record_request(tmp_path)

    with pytest.raises(ValueError, match="cannot precede the analysis request"):
        preflight_pending_request_theses(
            request_id=receipt.request.request_id,
            run_id="prospective-backcast",
            processed_at=NOW + timedelta(minutes=1),
            research_cutoff_at=NOW - timedelta(minutes=1),
            artifact_root=tmp_path,
        )


def test_shared_lock_keeps_pre301_intake_and_new_preflight_mutually_exclusive(tmp_path) -> None:
    receipt = _record_request(tmp_path)
    lock_path = tmp_path / LEGACY_SHARED_LOCK
    lock_path.write_text("pre-301 intake still active\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        preflight_pending_request_theses(
            request_id=receipt.request.request_id,
            run_id="blocked-by-legacy-lock",
            processed_at=NOW + timedelta(minutes=1),
            artifact_root=tmp_path,
        )

    assert lock_path.exists()
