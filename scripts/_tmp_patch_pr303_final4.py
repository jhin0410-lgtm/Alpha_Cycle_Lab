from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one replacement in {path}: found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    integrity = ROOT / "src/alpha_cycle/research_package_integrity_v2_1.py"
    assembler = ROOT / "src/alpha_cycle/research_package_assembler_v2_1.py"
    tests = ROOT / "tests/unit/test_research_package_last_review_v2_1.py"

    replace_once(
        integrity,
        """from alpha_cycle.intelligence.decision_view_v2_1 import (\n    DECISION_VIEW_SCHEMA_VERSION,\n    DecisionExpectationGapSnapshot,\n""",
        """from alpha_cycle.intelligence.decision_view_v2_1 import (\n    DECISION_VIEW_SCHEMA_VERSION,\n    DecisionExpectationGapSnapshot,\n    build_decision_view,\n""",
    )

    marker = """def decision_view_matches_underwriting_tournament(\n    view: DecisionViewSnapshot,\n"""
    helper = """def decision_view_has_valid_persisted_selection(\n    view: DecisionViewSnapshot,\n    *,\n    artifact_root: str | Path,\n) -> bool:\n    \"\"\"Rebuild the canonical Decision View from persisted preregistered inputs.\"\"\"\n\n    snapshot_ids = tuple(view.tournament_forecast_snapshot_ids)\n    if len(snapshot_ids) < 2 or len(set(snapshot_ids)) != len(snapshot_ids):\n        return False\n    registrations = _load_persisted_forecast_registrations(\n        Path(artifact_root),\n        snapshot_ids,\n    )\n    if len(registrations) != len(snapshot_ids):\n        return False\n    if tuple(sorted(item.snapshot_id for item in registrations)) != tuple(\n        sorted(snapshot_ids)\n    ):\n        return False\n    rule = _load_persisted_decision_view_selection_rule(\n        Path(artifact_root),\n        view.selection_rule_snapshot_id,\n    )\n    if rule is None:\n        return False\n    active = load_decision_system_v21_guardrails()\n    if (\n        view.guardrail_evidence_id != active.evidence_id\n        or rule.guardrail_evidence_id != active.evidence_id\n    ):\n        return False\n    try:\n        rebuilt = build_decision_view(\n            rule,\n            registrations,\n            captured_at=view.captured_at,\n            evaluation_date=view.evaluation_date,\n            guardrails=active,\n        )\n    except (TypeError, ValueError):\n        return False\n    return bool(\n        rebuilt.snapshot_id == view.snapshot_id\n        and rebuilt.payload_without_id() == view.payload_without_id()\n    )\n\n\n""" + marker
    replace_once(integrity, marker, helper)

    replace_once(
        integrity,
        """    \"\"\"Bind a Decision View to a genuine persisted forecast tournament identity.\"\"\"\n\n    tournament = underwriting.forecast_tournament\n""",
        """    \"\"\"Bind a Decision View to a genuine persisted forecast tournament identity.\"\"\"\n\n    if artifact_root is not None and not decision_view_has_valid_persisted_selection(\n        view,\n        artifact_root=artifact_root,\n    ):\n        return False\n    tournament = underwriting.forecast_tournament\n""",
    )

    replace_once(
        integrity,
        """    if underwriting.lane is UnderwritingLane.FAST:\n        if underwriting.readiness is not UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW:\n            return False\n        required = tuple(active.fast_lane_required_elements)\n""",
        """    if underwriting.lane is UnderwritingLane.FAST:\n        if (\n            underwriting.readiness\n            is not UnderwritingReadiness.FAST_LANE_READY_FOR_HUMAN_REVIEW\n        ):\n            return False\n        if thesis.status.value not in active.fast_lane_allowed_thesis_statuses:\n            return False\n        required = tuple(active.fast_lane_required_elements)\n""",
    )

    replace_once(
        integrity,
        """    \"ResearchPackageIntegrityError\",\n    \"decision_view_matches_underwriting_tournament\",\n""",
        """    \"ResearchPackageIntegrityError\",\n    \"decision_view_has_valid_persisted_selection\",\n    \"decision_view_matches_underwriting_tournament\",\n""",
    )

    replace_once(
        assembler,
        """from alpha_cycle.research_package_integrity_v2_1 import (\n    decision_view_matches_underwriting_tournament,\n""",
        """from alpha_cycle.research_package_integrity_v2_1 import (\n    decision_view_has_valid_persisted_selection,\n    decision_view_matches_underwriting_tournament,\n""",
    )

    old_component_block = """    underwriting = component_index.latest_underwriting(\n        security_id,\n        thesis_snapshot_id=thesis.snapshot_id,\n        evaluation_date=request.evaluation_date,\n        lane=request.requested_lane,\n        guardrail_evidence_id=guardrail_evidence_id,\n    )\n    if underwriting is None:\n        _block(\n            blockers,\n            \"underwriter\",\n            \"underwriting_snapshot_missing_or_incompatible\",\n            security_id,\n        )\n    payoff = component_index.latest_payoff(\n        security_id,\n        thesis_snapshot_id=thesis.snapshot_id,\n        horizon_trading_days=request.horizon_trading_days,\n        guardrail_evidence_id=guardrail_evidence_id,\n    )\n    if payoff is None:\n        _block(\n            blockers,\n            \"payoff_surface\",\n            \"payoff_surface_missing_or_incompatible\",\n            security_id,\n        )\n    view = component_index.latest_decision_view(\n        security_id,\n        evaluation_date=request.evaluation_date,\n        guardrail_evidence_id=guardrail_evidence_id,\n    )\n    if view is None:\n        _block(\n            blockers,\n            \"decision_view\",\n            \"decision_view_missing_or_incompatible\",\n            security_id,\n        )\n    gap = None\n    if view is not None:\n        gap = component_index.latest_expectation_gap(\n            security_id,\n            decision_view_snapshot_id=view.snapshot_id,\n            evaluation_date=request.evaluation_date,\n            guardrail_evidence_id=guardrail_evidence_id,\n        )\n    if gap is None:\n        _block(\n            blockers,\n            \"expectation_gap\",\n            \"expectation_gap_missing_or_incompatible\",\n            security_id,\n        )\n"""
    new_component_block = """    underwriting_selection_failed = False\n    try:\n        underwriting = component_index.latest_underwriting(\n            security_id,\n            thesis_snapshot_id=thesis.snapshot_id,\n            evaluation_date=request.evaluation_date,\n            lane=request.requested_lane,\n            guardrail_evidence_id=guardrail_evidence_id,\n        )\n    except ResearchComponentRepositoryError:\n        underwriting = None\n        underwriting_selection_failed = True\n        _block(\n            blockers,\n            \"underwriter\",\n            \"underwriting_snapshot_selection_ambiguous\",\n            security_id,\n        )\n    if underwriting is None and not underwriting_selection_failed:\n        _block(\n            blockers,\n            \"underwriter\",\n            \"underwriting_snapshot_missing_or_incompatible\",\n            security_id,\n        )\n\n    payoff_selection_failed = False\n    try:\n        payoff = component_index.latest_payoff(\n            security_id,\n            thesis_snapshot_id=thesis.snapshot_id,\n            horizon_trading_days=request.horizon_trading_days,\n            guardrail_evidence_id=guardrail_evidence_id,\n        )\n    except ResearchComponentRepositoryError:\n        payoff = None\n        payoff_selection_failed = True\n        _block(\n            blockers,\n            \"payoff_surface\",\n            \"payoff_surface_selection_ambiguous\",\n            security_id,\n        )\n    if payoff is None and not payoff_selection_failed:\n        _block(\n            blockers,\n            \"payoff_surface\",\n            \"payoff_surface_missing_or_incompatible\",\n            security_id,\n        )\n\n    decision_view_selection_failed = False\n    try:\n        view = component_index.latest_decision_view(\n            security_id,\n            evaluation_date=request.evaluation_date,\n            guardrail_evidence_id=guardrail_evidence_id,\n        )\n    except ResearchComponentRepositoryError:\n        view = None\n        decision_view_selection_failed = True\n        _block(\n            blockers,\n            \"decision_view\",\n            \"decision_view_selection_ambiguous\",\n            security_id,\n        )\n    if view is None and not decision_view_selection_failed:\n        _block(\n            blockers,\n            \"decision_view\",\n            \"decision_view_missing_or_incompatible\",\n            security_id,\n        )\n\n    gap = None\n    expectation_gap_selection_failed = False\n    if view is not None:\n        try:\n            gap = component_index.latest_expectation_gap(\n                security_id,\n                decision_view_snapshot_id=view.snapshot_id,\n                evaluation_date=request.evaluation_date,\n                guardrail_evidence_id=guardrail_evidence_id,\n            )\n        except ResearchComponentRepositoryError:\n            expectation_gap_selection_failed = True\n            _block(\n                blockers,\n                \"expectation_gap\",\n                \"expectation_gap_selection_ambiguous\",\n                security_id,\n            )\n    if gap is None and not expectation_gap_selection_failed:\n        _block(\n            blockers,\n            \"expectation_gap\",\n            \"expectation_gap_missing_or_incompatible\",\n            security_id,\n        )\n"""
    replace_once(assembler, old_component_block, new_component_block)

    replace_once(
        assembler,
        """    if (\n        underwriting is not None\n        and view is not None\n        and underwriting.lane is UnderwritingLane.DEEP\n    ):\n""",
        """    if (\n        view is not None\n        and artifact_root is not None\n        and not decision_view_has_valid_persisted_selection(\n            view,\n            artifact_root=artifact_root,\n        )\n    ):\n        _block(\n            blockers,\n            \"research_package\",\n            \"decision_view_persisted_selection_invalid\",\n            security_id,\n        )\n    if (\n        underwriting is not None\n        and view is not None\n        and underwriting.lane is UnderwritingLane.DEEP\n    ):\n""",
    )

    replace_once(
        assembler,
        """    temporary = Path(temporary_name)\n    try:\n        with os.fdopen(fd, \"wb\") as handle:\n""",
        """    temporary = Path(temporary_name)\n    try:\n        if os.name != \"nt\":\n            os.fchmod(fd, 0o644)\n        with os.fdopen(fd, \"wb\") as handle:\n""",
    )

    replace_once(
        tests,
        """import os\nfrom datetime import UTC, date, datetime\n""",
        """import os\nimport stat\nfrom datetime import UTC, date, datetime\n""",
    )
    replace_once(
        tests,
        """import alpha_cycle.research_package_assembler_v2_1 as assembler\nfrom alpha_cycle.intelligence.underwriter_v2_1 import UnderwritingLane\n""",
        """import alpha_cycle.research_package_assembler_v2_1 as assembler\nimport alpha_cycle.research_package_integrity_v2_1 as integrity\nfrom alpha_cycle.intelligence.decision_thesis_v2 import ThesisStatus\nfrom alpha_cycle.intelligence.underwriter_v2_1 import (\n    UnderwritingLane,\n    UnderwritingReadiness,\n)\n""",
    )
    replace_once(
        tests,
        """from alpha_cycle.investment_thesis_repository_v2_1 import (\n    InvestmentThesisRepositoryError,\n)\n""",
        """from alpha_cycle.investment_thesis_repository_v2_1 import (\n    InvestmentThesisRepositoryError,\n)\nfrom alpha_cycle.research_component_repository_v2_1 import (\n    ResearchComponentRepositoryError,\n)\n""",
    )

    appendix = r'''


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
'''
    text = tests.read_text(encoding="utf-8")
    if "test_fast_lane_still_validates_persisted_decision_view" in text:
        raise RuntimeError("final-four tests already present")
    tests.write_text(text.rstrip() + appendix + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
