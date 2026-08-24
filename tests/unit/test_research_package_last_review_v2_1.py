from __future__ import annotations

import os
import stat
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import alpha_cycle.research_package_assembler_v2_1 as assembler
import alpha_cycle.research_package_integrity_v2_1 as integrity
from alpha_cycle.intelligence.decision_thesis_v2 import ThesisStatus
from alpha_cycle.intelligence.underwriter_v2_1 import (
    UnderwritingLane,
    UnderwritingReadiness,
)
from alpha_cycle.investment_thesis_repository_v2_1 import (
    InvestmentThesisRepositoryError,
)
from alpha_cycle.research_component_repository_v2_1 import (
    ResearchComponentRepositoryError,
)

NOW = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)
EVAL = date(2026, 8, 23)
A = "a" * 64
B = "b" * 64
C = "c" * 64


def test_thesis_lineage_resolution_failure_becomes_structured_blocker() -> None:
    class BrokenIndex:
        def find_latest(self, *, security_id: str, horizon_trading_days: int):
            del security_id, horizon_trading_days
            raise InvestmentThesisRepositoryError("parent snapshot is missing")

    blockers = []
    thesis = assembler._resolve_latest_thesis_for_package(
        BrokenIndex(),  # type: ignore[arg-type]
        security_id="000660",
        horizon_trading_days=120,
        blockers=blockers,
    )

    assert thesis is None
    assert [(item.component, item.code, item.security_id) for item in blockers] == [
        ("thesis", "investment_thesis_lineage_invalid", "000660")
    ]


def test_fast_lane_package_does_not_require_forecast_tournament_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thesis = SimpleNamespace(snapshot_id=A, security_id="000660")
    underwriting = SimpleNamespace(
        lane=UnderwritingLane.FAST,
        payoff_surface_snapshot_id=B,
        expectation_state_snapshot_id=None,
        price_implied_requirement_snapshot_id=None,
        forecast_tournament=SimpleNamespace(
            comparable=False,
            forecast_snapshot_ids=(),
            forecast_ids=(),
            blockers=("forecast_tournament_requires_at_least_two_registrations",),
        ),
    )
    payoff = SimpleNamespace(snapshot_id=B)
    view = SimpleNamespace(
        snapshot_id=C,
        captured_at=NOW,
        target_variable="net_income",
        target_date=date(2026, 12, 31),
        unit="KRW_million",
    )
    gap = SimpleNamespace(
        captured_at=NOW,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        expectation_state_snapshot_id=None,
        price_implied_requirement_snapshot_id=None,
    )
    component_index = SimpleNamespace(
        latest_underwriting=lambda *args, **kwargs: underwriting,
        latest_payoff=lambda *args, **kwargs: payoff,
        latest_decision_view=lambda *args, **kwargs: view,
        latest_expectation_gap=lambda *args, **kwargs: gap,
    )
    request = SimpleNamespace(
        evaluation_date=EVAL,
        requested_lane=UnderwritingLane.FAST,
        horizon_trading_days=120,
    )
    monkeypatch.setattr(assembler, "package_integrity_blocker_codes", lambda *args: ())

    def fail_if_called(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Fast-Lane must not require tournament binding")

    monkeypatch.setattr(
        assembler,
        "decision_view_matches_underwriting_tournament",
        fail_if_called,
    )
    blockers = []

    package = assembler._assemble_security_package(
        "000660",
        thesis=thesis,  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
        component_index=component_index,  # type: ignore[arg-type]
        guardrail_evidence_id=A,
        blockers=blockers,
    )

    assert package is not None
    assert blockers == []


def test_owned_pointer_temp_ignores_predictable_symlink_slot(tmp_path: Path) -> None:
    root = tmp_path / "opportunity_candidate"
    root.mkdir()
    outside = tmp_path / "outside-target"
    outside.write_bytes(b"sentinel")
    predictable = root / (
        f".latest_opportunity_candidate.json.{os.getpid()}.owned.tmp"
    )
    try:
        predictable.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    temporary = assembler._write_owned_pointer_temp(
        root,
        "latest_opportunity_candidate.json",
        b"owned-pointer\n",
    )
    try:
        assert temporary != predictable
        assert temporary.is_file()
        assert not temporary.is_symlink()
        assert temporary.read_bytes() == b"owned-pointer\n"
        assert outside.read_bytes() == b"sentinel"
        assert predictable.is_symlink()
    finally:
        temporary.unlink(missing_ok=True)


def test_fast_lane_still_validates_persisted_decision_view(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    thesis = SimpleNamespace(snapshot_id=A, security_id="000660")
    underwriting = SimpleNamespace(
        lane=UnderwritingLane.FAST,
        payoff_surface_snapshot_id=B,
        expectation_state_snapshot_id=None,
        price_implied_requirement_snapshot_id=None,
        forecast_tournament=SimpleNamespace(comparable=False),
    )
    payoff = SimpleNamespace(snapshot_id=B)
    view = SimpleNamespace(
        snapshot_id=C,
        captured_at=NOW,
        target_variable="net_income",
        target_date=date(2026, 12, 31),
        unit="KRW_million",
    )
    gap = SimpleNamespace(
        captured_at=NOW,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        expectation_state_snapshot_id=None,
        price_implied_requirement_snapshot_id=None,
    )
    component_index = SimpleNamespace(
        latest_underwriting=lambda *args, **kwargs: underwriting,
        latest_payoff=lambda *args, **kwargs: payoff,
        latest_decision_view=lambda *args, **kwargs: view,
        latest_expectation_gap=lambda *args, **kwargs: gap,
    )
    request = SimpleNamespace(
        evaluation_date=EVAL,
        requested_lane=UnderwritingLane.FAST,
        horizon_trading_days=120,
    )
    monkeypatch.setattr(assembler, "package_integrity_blocker_codes", lambda *args: ())
    monkeypatch.setattr(
        assembler,
        "decision_view_has_valid_persisted_selection",
        lambda *args, **kwargs: False,
    )

    def deep_binding_must_not_run(*args, **kwargs):
        del args, kwargs
        raise AssertionError("Fast-Lane must not require underwriting tournament binding")

    monkeypatch.setattr(
        assembler,
        "decision_view_matches_underwriting_tournament",
        deep_binding_must_not_run,
    )
    blockers = []

    package = assembler._assemble_security_package(
        "000660",
        thesis=thesis,  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
        component_index=component_index,  # type: ignore[arg-type]
        guardrail_evidence_id=A,
        artifact_root=tmp_path,
        blockers=blockers,
    )

    assert package is None
    assert any(
        item.code == "decision_view_persisted_selection_invalid" for item in blockers
    )


def test_fast_ready_requires_guardrail_allowed_thesis_status() -> None:
    active = integrity.load_decision_system_v21_guardrails()
    thesis = SimpleNamespace(status=ThesisStatus.VALUATION_GATED)
    underwriting = SimpleNamespace(
        readiness=UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW,
        lane=UnderwritingLane.FAST,
        required_elements_satisfied=tuple(active.fast_lane_required_elements),
        required_elements_missing=(),
        blockers=(),
    )

    assert not integrity._underwriting_ready_contract_is_valid(  # type: ignore[attr-defined]
        thesis,  # type: ignore[arg-type]
        underwriting,  # type: ignore[arg-type]
        None,
    )


def test_owned_pointer_temp_is_shared_reader_readable(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX pointer mode semantics do not apply on Windows")
    root = tmp_path / "opportunity_candidate"
    root.mkdir()
    temporary = assembler._write_owned_pointer_temp(
        root,
        "latest_opportunity_candidate.json",
        b"owned-pointer\n",
    )
    try:
        assert stat.S_IMODE(temporary.stat().st_mode) == 0o644
    finally:
        temporary.unlink(missing_ok=True)


def test_ambiguous_component_selection_becomes_structured_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thesis = SimpleNamespace(snapshot_id=A, security_id="000660")

    def ambiguous_underwriting(*args, **kwargs):
        del args, kwargs
        raise ResearchComponentRepositoryError("ambiguous latest underwriting snapshot")

    payoff = SimpleNamespace(snapshot_id=B)
    view = SimpleNamespace(
        snapshot_id=C,
        captured_at=NOW,
        target_variable="net_income",
        target_date=date(2026, 12, 31),
        unit="KRW_million",
    )
    gap = SimpleNamespace(
        captured_at=NOW,
        target_variable=view.target_variable,
        target_date=view.target_date,
        unit=view.unit,
        expectation_state_snapshot_id=None,
        price_implied_requirement_snapshot_id=None,
    )
    component_index = SimpleNamespace(
        latest_underwriting=ambiguous_underwriting,
        latest_payoff=lambda *args, **kwargs: payoff,
        latest_decision_view=lambda *args, **kwargs: view,
        latest_expectation_gap=lambda *args, **kwargs: gap,
    )
    request = SimpleNamespace(
        evaluation_date=EVAL,
        requested_lane=UnderwritingLane.FAST,
        horizon_trading_days=120,
    )
    monkeypatch.setattr(assembler, "package_integrity_blocker_codes", lambda *args: ())
    blockers = []

    package = assembler._assemble_security_package(
        "000660",
        thesis=thesis,  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
        component_index=component_index,  # type: ignore[arg-type]
        guardrail_evidence_id=A,
        blockers=blockers,
    )

    assert package is None
    assert [(item.component, item.code) for item in blockers] == [
        ("underwriter", "underwriting_snapshot_selection_ambiguous")
    ]

