from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone

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
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    ResearchRoundBlocker,
    ResearchRoundMode,
    ResearchRoundStatus,
)
from alpha_cycle.intelligence.research_run_ledger_v2_1 import (
    ResearchRoundRunSnapshot,
    ResearchRunKind,
    build_research_run_ledger,
    persist_research_run,
    persist_research_run_ledger,
)
from alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane
from alpha_cycle.investment_thesis_repository_v2_1 import persist_investment_thesis
from alpha_cycle.research_observatory_v2_1 import (
    ObservatoryDataError,
    load_latest_observatory_state,
)
from alpha_cycle.research_request_intake_v2_1 import record_analysis_request
from alpha_cycle.research_request_preflight_v2_1 import preflight_pending_request_theses

NOW = datetime(2026, 8, 23, 6, 0, tzinfo=UTC)
EVALUATION_DATE = date(2026, 8, 23)


def _uncertainty() -> ThesisUncertainty:
    dimension = UncertaintyDimension(
        level=UncertaintyLevel.HIGH,
        rationale="Final P2 regression fixture uncertainty.",
    )
    return ThesisUncertainty(
        evidence=dimension,
        model=dimension,
        regime=dimension,
        expectation=dimension,
        catalyst=dimension,
        valuation=dimension,
    )


def _thesis(security_id: str, captured_at: datetime) -> InvestmentThesisSnapshot:
    return InvestmentThesisSnapshot(
        thesis_id=f"thesis-{security_id}",
        snapshot_version=1,
        parent_snapshot_id=None,
        captured_at=captured_at,
        security_id=security_id,
        horizon_trading_days=120,
        variant_view="Research prerequisite only; no investment conclusion.",
        why_now="Exercise final P2 preflight hardening.",
        claims=(
            ThesisClaim(
                claim_id="claim-1",
                category="industry_cycle",
                statement="Transmission remains a hypothesis until downstream research runs.",
                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
                direction=ClaimDirection.MIXED,
            ),
        ),
        catalysts=(),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=(),
        first_rejection_risk="The proposed transmission may fail.",
        portfolio_overlap=(),
        opportunity_set_refs=(),
        status=ThesisStatus.RESEARCH_PRIORITY,
    )


def _record_request(
    tmp_path,
    *,
    request_id: str,
    security_ids: tuple[str, ...],
    mode: ResearchRoundMode = ResearchRoundMode.PROSPECTIVE,
):
    return record_analysis_request(
        request_id=request_id,
        requested_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        evaluation_date=EVALUATION_DATE,
        horizon_trading_days=120,
        security_ids=security_ids,
        mode=mode,
        requested_lane=UnderwritingLane.DEEP,
        request_text="Exercise final typed-thesis preflight P2 regressions.",
        artifact_root=tmp_path,
    )


def test_blocker_clear_uses_current_state_without_new_ledger_enum(tmp_path) -> None:
    receipt = _record_request(
        tmp_path,
        request_id="clear-transition",
        security_ids=("000660",),
    )
    blocked = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="blocked-first",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    assert blocked.run is not None
    assert blocked.run.kind is ResearchRunKind.PRE_ORCHESTRATION_BLOCKED

    persist_investment_thesis(
        _thesis("000660", NOW + timedelta(minutes=1, seconds=10)),
        artifact_root=tmp_path,
    )
    ready = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="ready-after-thesis",
        processed_at=NOW + timedelta(minutes=2),
        artifact_root=tmp_path,
    )

    assert ready.ready_for_package_assembly is True
    assert ready.changed_history is False
    assert ready.changed_current_state is True
    assert ready.run is None
    assert ready.ledger.summary.run_count == 1
    assert ready.ledger.summary.blocked_run_count == 1
    assert dict(ready.ledger.summary.status_counts) == {
        "pre_orchestration_blocked": 1,
    }
    assert not hasattr(ResearchRunKind, "PRE_ORCHESTRATION_READY")
    ledger_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "research_run_ledger_v2_1").glob("*.json")
    )
    assert "pre_orchestration_ready" not in ledger_text

    state = load_latest_observatory_state(tmp_path)
    assert state is not None
    assert len(state.inbox) == 1
    assert state.inbox[0].state == "pre_orchestration_ready"
    assert state.inbox[0].blocker_count == 0


def test_replay_a_blocked_b_ready_a_blocked_restores_current_state_without_duplicate_metric(
    tmp_path,
) -> None:
    receipt = _record_request(
        tmp_path,
        request_id="replay-a-b-a",
        security_ids=("000660",),
        mode=ResearchRoundMode.REPLAY,
    )
    cutoff_a = NOW - timedelta(days=30)
    thesis_time = NOW - timedelta(days=25)
    cutoff_b = NOW - timedelta(days=20)
    persist_investment_thesis(_thesis("000660", thesis_time), artifact_root=tmp_path)

    first_a = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="replay-a-first",
        processed_at=NOW + timedelta(minutes=1),
        research_cutoff_at=cutoff_a,
        artifact_root=tmp_path,
    )
    second_b = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="replay-b",
        processed_at=NOW + timedelta(minutes=2),
        research_cutoff_at=cutoff_b,
        artifact_root=tmp_path,
    )
    state_b = load_latest_observatory_state(tmp_path)
    assert state_b is not None
    assert state_b.inbox[0].state == "pre_orchestration_ready"

    revisit_a = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="replay-a-revisit",
        processed_at=NOW + timedelta(minutes=3),
        research_cutoff_at=cutoff_a,
        artifact_root=tmp_path,
    )

    assert first_a.changed_history is True
    assert second_b.changed_history is False
    assert second_b.ready_for_package_assembly is True
    assert revisit_a.changed_history is False
    assert revisit_a.changed_current_state is True
    assert revisit_a.run == first_a.run
    assert revisit_a.preflight_state.snapshot_id == first_a.preflight_state.snapshot_id
    assert revisit_a.ledger.summary.run_count == 1
    assert revisit_a.ledger.summary.blocked_run_count == 1

    state_a = load_latest_observatory_state(tmp_path)
    assert state_a is not None
    assert state_a.inbox[0].state == "pre_orchestration_blocked"
    assert state_a.inbox[0].blocker_count == 1


def test_equivalent_replay_cutoff_offsets_share_state_and_metric_identity(tmp_path) -> None:
    receipt = _record_request(
        tmp_path,
        request_id="equivalent-cutoff",
        security_ids=("000660",),
        mode=ResearchRoundMode.REPLAY,
    )
    cutoff_utc = NOW - timedelta(days=10)
    cutoff_kst = cutoff_utc.astimezone(timezone(timedelta(hours=9)))

    first = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="cutoff-utc",
        processed_at=NOW + timedelta(minutes=1),
        research_cutoff_at=cutoff_utc,
        artifact_root=tmp_path,
    )
    second = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="cutoff-kst",
        processed_at=NOW + timedelta(minutes=2),
        research_cutoff_at=cutoff_kst,
        artifact_root=tmp_path,
    )

    assert second.changed_history is False
    assert second.changed_current_state is False
    assert second.run == first.run
    assert second.preflight_state.snapshot_id == first.preflight_state.snapshot_id
    assert second.research_cutoff_at.tzinfo is UTC
    assert second.ledger.summary.run_count == 1


def test_preflight_rejects_request_after_orchestrated_run(tmp_path) -> None:
    intake = _record_request(
        tmp_path,
        request_id="already-orchestrated",
        security_ids=("000660",),
    )
    request = intake.request
    blocker = ResearchRoundBlocker(
        component="underwriter",
        code="fixture_blocker",
        detail="Fixture orchestrated blocker.",
        security_id="000660",
    )
    run = ResearchRoundRunSnapshot(
        run_id="orchestrated-existing",
        request_snapshot_id=request.snapshot_id,
        request_id=request.request_id,
        kind=ResearchRunKind.ORCHESTRATED,
        started_at=NOW + timedelta(minutes=1),
        completed_at=NOW + timedelta(minutes=1),
        evaluation_date=request.evaluation_date,
        horizon_trading_days=request.horizon_trading_days,
        security_ids=request.security_ids,
        mode=request.mode,
        requested_lane=request.requested_lane,
        research_round_snapshot_id="c" * 64,
        round_status=ResearchRoundStatus.PROSPECTIVE_BLOCKED,
        blockers=(blocker,),
        flags=(),
        opportunity_set_snapshot_id=None,
        expectation_overlay_snapshot_id=None,
        prospective_registration_snapshot_id=None,
        guardrail_evidence_id=request.guardrail_evidence_id,
    )
    ledger = build_research_run_ledger(
        intake.ledger.requests,
        (run,),
        built_at=NOW + timedelta(minutes=1),
    )
    persist_research_run(run, output_root=tmp_path)
    persist_research_run_ledger(ledger, output_root=tmp_path)

    with pytest.raises(ValueError, match="already has an orchestrated run"):
        preflight_pending_request_theses(
            request_id=request.request_id,
            run_id="illegal-preflight",
            processed_at=NOW + timedelta(minutes=2),
            artifact_root=tmp_path,
        )
    latest = load_latest_observatory_state(tmp_path)
    assert latest is not None
    assert latest.ledger.snapshot_id == ledger.snapshot_id
    assert latest.inbox[0].state == ResearchRoundStatus.PROSPECTIVE_BLOCKED.value


def test_multi_security_preflight_scans_each_thesis_artifact_once(tmp_path, monkeypatch) -> None:
    receipt = _record_request(
        tmp_path,
        request_id="single-repository-scan",
        security_ids=("000660", "005930"),
    )
    for index, security_id in enumerate(("000660", "005930"), start=1):
        persist_investment_thesis(
            _thesis(security_id, NOW + timedelta(seconds=10 + index)),
            artifact_root=tmp_path,
        )

    real_loader = thesis_repository.load_investment_thesis
    loaded_paths: list[str] = []

    def counting_loader(path):
        loaded_paths.append(str(path))
        return real_loader(path)

    monkeypatch.setattr(thesis_repository, "load_investment_thesis", counting_loader)
    preflight = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="single-scan-ready",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )

    assert preflight.ready_for_package_assembly is True
    assert preflight.run is None
    assert len(loaded_paths) == 2
    assert len(set(loaded_paths)) == 2


def test_current_preflight_state_tampering_fails_closed(tmp_path) -> None:
    receipt = _record_request(
        tmp_path,
        request_id="tamper-current-state",
        security_ids=("000660",),
    )
    preflight = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="tamper-state-run",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    payload = json.loads(preflight.preflight_state_path.read_text(encoding="utf-8"))
    payload["unknown_field"] = "tampered"
    preflight.preflight_state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ObservatoryDataError, match="current thesis-preflight state failed validation"):
        load_latest_observatory_state(tmp_path)


def test_current_preflight_pointer_tampering_fails_closed(tmp_path) -> None:
    receipt = _record_request(
        tmp_path,
        request_id="tamper-current-pointer",
        security_ids=("000660",),
    )
    preflight = preflight_pending_request_theses(
        request_id=receipt.request.request_id,
        run_id="tamper-pointer-run",
        processed_at=NOW + timedelta(minutes=1),
        artifact_root=tmp_path,
    )
    payload = json.loads(
        preflight.preflight_current_pointer_path.read_text(encoding="utf-8")
    )
    payload["state_snapshot_id"] = "f" * 64
    preflight.preflight_current_pointer_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ObservatoryDataError, match="current thesis-preflight state failed validation"):
        load_latest_observatory_state(tmp_path)
