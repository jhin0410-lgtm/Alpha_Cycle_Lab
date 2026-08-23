from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.decision_thesis_v2 import ThesisStatus
from alpha_cycle.intelligence.decision_view_v2_1 import (
    build_decision_view_selection_rule,
    persist_decision_view_selection_rule,
)
from alpha_cycle.intelligence.forecast_ledger import (
    ForecasterKind,
    ForecastRegistrationMode,
    ForecastRegistrationSnapshot,
    OrdinalAssessment,
    PrimaryErrorMetric,
    persist_forecast_registration,
)
from alpha_cycle.intelligence.research_round_orchestrator_v2_1 import (
    persist_research_round,
)
from alpha_cycle.intelligence.underwriter_v2_1 import (
    SUPPLEMENTAL_DEEP_ELEMENTS,
    UnderwritingLane,
    UnderwritingReadiness,
)
from alpha_cycle.research_package_integrity_v2_1 import (
    ResearchPackageIntegrityError,
    decision_view_matches_underwriting_tournament,
    package_integrity_blocker_codes,
    require_trusted_artifact_root,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
TARGET = date(2026, 12, 31)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id
A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64
DEEP_REQUIRED = (
    load_decision_system_v21_guardrails().deep_lane_required_elements
    + SUPPLEMENTAL_DEEP_ELEMENTS
)


def _thesis() -> SimpleNamespace:
    return SimpleNamespace(
        status=ThesisStatus.UNDERWRITING,
        captured_at=NOW,
        catalysts=("earnings",),
        kill_conditions=("kill",),
        opportunity_set_refs=("opportunity",),
        portfolio_overlap=("cycle",),
    )


def _ready_underwriting(*, flags: tuple[str, ...] = ()) -> SimpleNamespace:
    return SimpleNamespace(
        captured_at=NOW,
        lane=UnderwritingLane.DEEP,
        readiness=UnderwritingReadiness.DEEP_LANE_READY_FOR_HUMAN_REVIEW,
        required_elements_satisfied=DEEP_REQUIRED,
        required_elements_missing=(),
        blockers=(),
        flags=flags,
        causal_graph_snapshot_id=A,
        expectation_state_snapshot_id=B,
        forward_valuation_snapshot_id=C,
        price_implied_requirement_snapshot_id=D,
        payoff_surface_snapshot_id=E,
        epistemic_defense_snapshot_id=F,
        forecast_tournament=SimpleNamespace(comparable=True, flags=()),
    )


def _registration(
    forecast_id: str,
    *,
    model_family: str,
    cluster: str,
    value: float,
) -> ForecastRegistrationSnapshot:
    return ForecastRegistrationSnapshot(
        forecast_id=forecast_id,
        registered_at=NOW - timedelta(hours=2, minutes=30),
        ledger_recorded_at=NOW - timedelta(hours=2, minutes=20),
        forecast_origin=NOW - timedelta(hours=2),
        information_cutoff=NOW - timedelta(hours=3),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        horizon_label="fixture",
        forecast_value=value,
        unit="KRW_million",
        range_lower=None,
        range_upper=None,
        direction=None,
        direction_reference_value=None,
        direction_flat_tolerance=0.0,
        confidence=OrdinalAssessment.MEDIUM,
        confidence_rationale="fixture",
        forecaster_kind=ForecasterKind.MODEL,
        model_family=model_family,
        driver_refs=("driver",),
        regime_tags=("regime",),
        decision_relevance=OrdinalAssessment.HIGH,
        difficulty=OrdinalAssessment.MEDIUM,
        baseline_refs=(),
        dependency_cluster_id=cluster,
        source_evidence_ids=(A,),
        registration_mode=ForecastRegistrationMode.NATIVE_PROSPECTIVE,
        primary_error_metric=PrimaryErrorMetric.ABSOLUTE_ERROR,
        guardrail_evidence_id=GUARDRAIL,
    )


def _view(first: ForecastRegistrationSnapshot, second: ForecastRegistrationSnapshot):
    return SimpleNamespace(
        captured_at=NOW,
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        forecast_origin=first.forecast_origin,
        information_cutoff=first.information_cutoff,
        tournament_forecast_snapshot_ids=(first.snapshot_id, second.snapshot_id),
        tournament_dependency_overlap=False,
        selected_forecast_snapshot_id=first.snapshot_id,
        selected_forecast_id=first.forecast_id,
        selected_forecaster_kind=first.forecaster_kind,
        selected_model_family=first.model_family,
        selected_forecast_value=first.forecast_value,
    )


def _tournament(first: ForecastRegistrationSnapshot, second: ForecastRegistrationSnapshot):
    return SimpleNamespace(
        comparable=True,
        forecast_snapshot_ids=(first.snapshot_id, second.snapshot_id),
        forecast_ids=(first.forecast_id, second.forecast_id),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        forecast_origin=first.forecast_origin,
        information_cutoff=first.information_cutoff,
        primary_error_metric="absolute_error",
        distinct_forecaster_count=2,
        dependency_cluster_count=2,
        blockers=(),
        flags=(),
    )


def test_ready_deep_elements_require_concrete_bound_snapshot_ids() -> None:
    underwriting = _ready_underwriting()
    underwriting.causal_graph_snapshot_id = None
    payoff = SimpleNamespace(snapshot_id=E, captured_at=NOW)
    blockers = package_integrity_blocker_codes(
        _thesis(), underwriting, payoff, None, None
    )
    assert "underwriting_ready_evidence_contract_mismatch" in blockers


def test_deep_flags_require_flagged_readiness_state() -> None:
    underwriting = _ready_underwriting(flags=("counter_evidence_material",))
    payoff = SimpleNamespace(snapshot_id=E, captured_at=NOW)
    blockers = package_integrity_blocker_codes(
        _thesis(), underwriting, payoff, None, None
    )
    assert "underwriting_ready_evidence_contract_mismatch" in blockers


def test_persisted_tournament_must_prove_distinct_forecaster_descriptors(
    tmp_path: Path,
) -> None:
    first = _registration(
        "forecast-a", model_family="same-model", cluster="a", value=20.0
    )
    second = _registration(
        "forecast-b", model_family="same-model", cluster="b", value=19.0
    )
    persist_forecast_registration(first, output_root=tmp_path)
    persist_forecast_registration(second, output_root=tmp_path)
    view = _view(first, second)
    underwriting = SimpleNamespace(
        forecast_tournament=_tournament(first, second),
        guardrail_evidence_id=GUARDRAIL,
    )
    assert (
        decision_view_matches_underwriting_tournament(
            view,
            underwriting,
            artifact_root=tmp_path,
        )
        is False
    )


def test_persisted_tournament_rejects_impossible_chronology() -> None:
    first = _registration(
        "forecast-a", model_family="model-a", cluster="a", value=20.0
    )
    second = _registration(
        "forecast-b", model_family="model-b", cluster="b", value=19.0
    )
    view = _view(first, second)
    tournament = _tournament(first, second)
    future_cutoff = view.forecast_origin + timedelta(minutes=1)
    view.information_cutoff = future_cutoff
    tournament.information_cutoff = future_cutoff
    underwriting = SimpleNamespace(forecast_tournament=tournament)
    assert decision_view_matches_underwriting_tournament(view, underwriting) is False


def test_source_ledger_symlink_is_rejected_before_observatory_read(
    tmp_path: Path,
) -> None:
    ledger_root = tmp_path / "research_run_ledger_v2_1"
    ledger_root.mkdir()
    outside = tmp_path / "outside-ledger.json"
    outside.write_text("{}", encoding="utf-8")
    (ledger_root / f"{A}.json").symlink_to(outside)
    with pytest.raises(
        ResearchPackageIntegrityError,
        match="ledger artifact cannot be a symlink",
    ):
        require_trusted_artifact_root(tmp_path)


def test_research_round_eexist_never_deletes_preexisting_artifact(tmp_path: Path) -> None:
    snapshot = SimpleNamespace(
        snapshot_id=A,
        payload_without_id=lambda: {"schema_version": 1, "round_id": "existing"},
    )
    path = tmp_path / "research_round_v2_1" / f"{A}.json"
    path.parent.mkdir(parents=True)
    original = b"pre-existing-round\n"
    path.write_bytes(original)
    with pytest.raises(FileExistsError):
        persist_research_round(snapshot, output_root=tmp_path)
    assert path.read_bytes() == original


def test_fabricated_registration_payload_cannot_enter_persisted_tournament(
    tmp_path: Path,
) -> None:
    first = _registration(
        "forecast-a", model_family="model-a", cluster="a", value=20.0
    )
    second = _registration(
        "forecast-b", model_family="model-b", cluster="b", value=19.0
    )
    rule = build_decision_view_selection_rule(
        rule_id="canonical-rule",
        registered_at=NOW - timedelta(hours=4),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecaster_kind=first.forecaster_kind,
        selected_model_family=first.model_family,
        rationale="Pinned before forecast registration.",
        source_evidence_ids=(A,),
    )
    persist_decision_view_selection_rule(rule, output_root=tmp_path)
    persist_forecast_registration(first, output_root=tmp_path)
    pointer = persist_forecast_registration(second, output_root=tmp_path)
    pointer_payload = __import__("json").loads(pointer.read_text(encoding="utf-8"))
    directory = Path(pointer_payload["snapshot_path"])
    payload_path = directory / "forecast_registration.json"
    payload = __import__("json").loads(payload_path.read_text(encoding="utf-8"))
    payload["forecaster_kind"] = "fabricated-kind"
    payload["outcome_observed"] = True
    # Rebind the directory/manifest to the fabricated payload so simple hash/manifest checks pass.
    import hashlib
    import json

    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    fabricated_id = hashlib.sha256(encoded).hexdigest()
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot_id"] = fabricated_id
    manifest["forecast_id"] = second.forecast_id
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    new_directory = directory.with_name(directory.name.rsplit("__", 1)[0] + f"__{fabricated_id[:12]}")
    directory.rename(new_directory)

    view = _view(first, second)
    view.selection_rule_snapshot_id = rule.snapshot_id
    view.tournament_forecast_snapshot_ids = (first.snapshot_id, fabricated_id)
    tournament = _tournament(first, second)
    tournament.forecast_snapshot_ids = (first.snapshot_id, fabricated_id)
    underwriting = SimpleNamespace(
        forecast_tournament=tournament,
        guardrail_evidence_id=GUARDRAIL,
    )
    assert (
        decision_view_matches_underwriting_tournament(
            view, underwriting, artifact_root=tmp_path
        )
        is False
    )


def test_persisted_selection_rule_must_precede_and_uniquely_pin_forecast(
    tmp_path: Path,
) -> None:
    first = _registration(
        "forecast-a", model_family="model-a", cluster="a", value=20.0
    )
    second = _registration(
        "forecast-b", model_family="model-b", cluster="b", value=19.0
    )
    late_rule = build_decision_view_selection_rule(
        rule_id="late-rule",
        registered_at=first.registered_at + timedelta(minutes=1),
        security_id="000660",
        target_variable="net_income",
        target_date=TARGET,
        unit="KRW_million",
        selected_forecaster_kind=first.forecaster_kind,
        selected_model_family=first.model_family,
        rationale="This rule is intentionally too late.",
        source_evidence_ids=(A,),
    )
    persist_decision_view_selection_rule(late_rule, output_root=tmp_path)
    persist_forecast_registration(first, output_root=tmp_path)
    persist_forecast_registration(second, output_root=tmp_path)
    view = _view(first, second)
    view.selection_rule_snapshot_id = late_rule.snapshot_id
    underwriting = SimpleNamespace(
        forecast_tournament=_tournament(first, second),
        guardrail_evidence_id=GUARDRAIL,
    )
    assert (
        decision_view_matches_underwriting_tournament(
            view, underwriting, artifact_root=tmp_path
        )
        is False
    )
