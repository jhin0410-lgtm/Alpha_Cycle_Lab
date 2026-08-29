from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import alpha_cycle.forecast_tournament_opportunity_v2_1 as tournament_module
from alpha_cycle.forecast_tournament_opportunity_v2_1 import (
    EvidenceStatus,
    ForecastTournamentError,
    build_forecast_opportunity_bundle,
    persist_forecast_opportunity_bundle,
    replay_forecast_opportunity_bundle,
)
from alpha_cycle.forecast_tournament_opportunity_v2_1_cli import main as cli_main
from alpha_cycle.intelligence import (
    sk_hynix_company_gp_ex_ante_2026q3_numeric_forecast as numeric_module,
)
from alpha_cycle.intelligence import (
    sk_hynix_company_gp_ex_ante_2026q3_prospective_feature as feature_module,
)
from alpha_cycle.intelligence import (
    sk_hynix_company_gp_ex_ante_selected_estimator_freeze as estimator_module,
)

CAPTURED = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)
MARKET_ID = "8" * 64
RESEARCH_ID = "9" * 64
TEST_PATHS: tuple[Path, Path, Path, Path] | None = None


@pytest.fixture(scope="session", autouse=True)
def synthetic_lineage(tmp_path_factory: pytest.TempPathFactory):
    global TEST_PATHS
    root = tmp_path_factory.mktemp("forecast-tournament-lineage")
    raw_payload = {"financials": {"list": []}}
    raw_bytes = feature_module._canonical_bytes(raw_payload)
    kst = timezone(timedelta(hours=9))
    origin = datetime(2026, 8, 31, 23, 59, 59, tzinfo=kst)
    captured = datetime(2026, 8, 22, 16, 0, tzinfo=kst)
    provisional_capture = feature_module.ProspectiveSourceCapture(
        evidence_id="0" * 64,
        contract_evidence_id="1" * 64,
        historical_execution_evidence_id="2" * 64,
        target_period="2026Q3",
        source_period="2026Q2",
        forecast_origin=origin,
        captured_at=captured,
        raw_payload_sha256=feature_module._sha(raw_payload),
        captured_payload_bytes_sha256=feature_module._sha_bytes(raw_bytes),
    )
    capture = replace(
        provisional_capture,
        evidence_id=feature_module._sha(
            feature_module._source_capture_payload(provisional_capture)
        ),
    )
    periods = tuple(f"{year}Q{quarter}" for year in range(2016, 2026) for quarter in (2, 3))
    provisional_estimator = estimator_module.FrozenSelectedEstimatorFullFit(
        evidence_id="0" * 64,
        contract_evidence_id="3" * 64,
        execution_evidence_id="2" * 64,
        scope_evidence_id="4" * 64,
        combined_bundle_evidence_id="5" * 64,
        target_join_evidence_id="6" * 64,
        target_source_evidence_id="7" * 64,
        raw_target_capture_evidence_id="8" * 64,
        backtest_evidence_id="9" * 64,
        estimator_freeze_evidence_id="a" * 64,
        selected_candidate_id="lagged_gp_affine_ols",
        estimator="ordinary_least_squares",
        parameter_count=2,
        predictors=("lagged_company_gross_profit",),
        training_periods=periods,
        training_row_count=20,
        scaling_ddof=0,
        predictor_means=(50.0,),
        predictor_scales=(10.0,),
        standardized_coefficients=(110.0, 20.0),
        raw_unit_intercept=10.0,
        raw_unit_coefficients=(2.0,),
        design_rank=2,
        residual_degrees_of_freedom=18,
        condition_number=1.0,
        training_mae_krw_million=1.0,
        training_rmse_krw_million=2.0,
        historical_benchmark_mae_krw_million=4.0,
        historical_selected_candidate_mae_krw_million=3.0,
        historical_relative_mae_improvement=0.25,
    )
    estimator = replace(
        provisional_estimator,
        evidence_id=estimator_module._sha(
            estimator_module._artifact_payload(provisional_estimator)
        ),
    )
    provisional_feature = feature_module.FrozenProspectiveFeatureVector(
        evidence_id="0" * 64,
        contract_evidence_id="1" * 64,
        protocol_evidence_id="b" * 64,
        selected_estimator_evidence_id=estimator.evidence_id,
        historical_execution_evidence_id="2" * 64,
        source_capture_evidence_id=capture.evidence_id,
        target_period="2026Q3",
        source_period="2026Q2",
        forecast_origin=origin,
        frozen_at=datetime(2026, 8, 22, 16, 4, tzinfo=kst),
        source_receipt_no="20260814003509",
        source_receipt_date=date(2026, 8, 14),
        source_available_at=datetime(2026, 8, 14, 23, 59, 59, tzinfo=kst),
        source_raw_payload_sha256=capture.raw_payload_sha256,
        source_captured_payload_bytes_sha256=capture.captured_payload_bytes_sha256,
        predictors=("lagged_company_gross_profit",),
        feature_values=(100.0,),
    )
    feature = replace(
        provisional_feature,
        evidence_id=feature_module._sha(
            feature_module._feature_vector_payload(provisional_feature)
        ),
    )
    locked_at = datetime(2026, 8, 22, 16, 52, tzinfo=kst)
    provisional_forecast = numeric_module.LockedNumericForecast(
        evidence_id="0" * 64,
        contract_evidence_id="c" * 64,
        selected_estimator_evidence_id=estimator.evidence_id,
        feature_vector_evidence_id=feature.evidence_id,
        protocol_evidence_id=feature.protocol_evidence_id,
        source_capture_evidence_id=capture.evidence_id,
        target_period="2026Q3",
        forecast_origin=origin,
        forecast_locked_at=locked_at,
        selected_candidate_id="lagged_gp_affine_ols",
        predictors=("lagged_company_gross_profit",),
        feature_values=(100.0,),
        raw_unit_intercept=10.0,
        raw_unit_coefficients=(2.0,),
        standardized_input=(5.0,),
        selected_forecast_krw_million=210.0,
        benchmark_id="previous_reported_quarter_gross_profit_persistence",
        benchmark_forecast_krw_million=100.0,
        historical_selected_candidate_mae_krw_million=3.0,
        historical_benchmark_mae_krw_million=4.0,
    )
    forecast = replace(
        provisional_forecast,
        evidence_id=numeric_module._sha(
            numeric_module._forecast_payload(provisional_forecast)
        ),
    )
    forecast_path = root / "forecast.json"
    feature_path = root / "feature.json"
    estimator_path = root / "estimator.json"
    capture_directory = root / f"source-capture-{capture.evidence_id}"
    (capture_directory / "raw").mkdir(parents=True)
    forecast_path.write_bytes(
        numeric_module._canonical_bytes(
            {
                "schema_version": 1,
                "status": forecast.status,
                "forecast": {
                    "evidence_id": forecast.evidence_id,
                    **numeric_module._forecast_payload(forecast),
                },
            }
        )
    )
    feature_path.write_bytes(
        feature_module._canonical_bytes(
            {
                "schema_version": 1,
                "status": feature.status,
                "feature_vector": {
                    "evidence_id": feature.evidence_id,
                    **feature_module._feature_vector_payload(feature),
                },
            }
        )
    )
    estimator_path.write_bytes(
        estimator_module._canonical_bytes(
            {
                "schema_version": 1,
                "status": estimator.status,
                "selected_estimator": {
                    "evidence_id": estimator.evidence_id,
                    **estimator_module._artifact_payload(estimator),
                },
            }
        )
    )
    (capture_directory / "capture.json").write_bytes(
        feature_module._canonical_bytes(
            {
                "schema_version": 1,
                "status": capture.status,
                "capture": {
                    "evidence_id": capture.evidence_id,
                    **feature_module._source_capture_payload(capture),
                },
            }
        )
    )
    (capture_directory / "raw" / "2026Q2.json").write_bytes(raw_bytes)
    original_evidence_id = tournament_module.EXPECTED_FROZEN_FORECAST_EVIDENCE_ID
    original_bytes_sha256 = tournament_module.EXPECTED_FROZEN_FORECAST_BYTES_SHA256
    tournament_module.EXPECTED_FROZEN_FORECAST_EVIDENCE_ID = forecast.evidence_id
    tournament_module.EXPECTED_FROZEN_FORECAST_BYTES_SHA256 = hashlib.sha256(
        forecast_path.read_bytes()
    ).hexdigest()
    TEST_PATHS = (forecast_path, feature_path, estimator_path, capture_directory)
    yield
    TEST_PATHS = None
    tournament_module.EXPECTED_FROZEN_FORECAST_EVIDENCE_ID = original_evidence_id
    tournament_module.EXPECTED_FROZEN_FORECAST_BYTES_SHA256 = original_bytes_sha256


def _test_paths() -> tuple[Path, Path, Path, Path]:
    assert TEST_PATHS is not None
    return TEST_PATHS


def _bundle(path: Path | None = None):
    forecast, feature, estimator, capture = _test_paths()
    return build_forecast_opportunity_bundle(
        frozen_forecast_path=path or forecast,
        frozen_feature_path=feature,
        selected_estimator_path=estimator,
        source_capture_directory=capture,
        captured_at=CAPTURED,
        evaluation_date=date(2026, 8, 25),
        market_snapshot_id=MARKET_ID,
        research_snapshot_id=RESEARCH_ID,
    )


def _copy_source(tmp_path: Path) -> Path:
    source = _test_paths()[0]
    target = tmp_path / "frozen.json"
    target.write_bytes(source.read_bytes())
    return target


def _copy_lineage(tmp_path: Path) -> tuple[Path, Path, Path]:
    _, source_feature, source_estimator, source_capture = _test_paths()
    feature = tmp_path / "feature.json"
    estimator = tmp_path / "estimator.json"
    capture = tmp_path / "capture"
    feature.write_bytes(source_feature.read_bytes())
    estimator.write_bytes(source_estimator.read_bytes())
    (capture / "raw").mkdir(parents=True)
    (capture / "capture.json").write_bytes((source_capture / "capture.json").read_bytes())
    (capture / "raw" / "2026Q2.json").write_bytes(
        (source_capture / "raw" / "2026Q2.json").read_bytes()
    )
    return feature, estimator, capture


def _persist(bundle, output_root: Path, source: Path | None = None) -> Path:
    forecast, feature, estimator, capture = _test_paths()
    return persist_forecast_opportunity_bundle(
        bundle,
        output_root=output_root,
        frozen_forecast_path=source or forecast,
        frozen_feature_path=feature,
        selected_estimator_path=estimator,
        source_capture_directory=capture,
    )


def _replay(directory: Path, source: Path | None = None):
    forecast, feature, estimator, capture = _test_paths()
    return replay_forecast_opportunity_bundle(
        directory,
        frozen_forecast_path=source or forecast,
        frozen_feature_path=feature,
        selected_estimator_path=estimator,
        source_capture_directory=capture,
    )


def test_real_frozen_forecast_registers_two_outcome_blind_candidates() -> None:
    bundle = _bundle()
    tournament = bundle.tournament
    assert [item.candidate_id for item in tournament.candidates] == [
        "lagged_gp_affine_ols",
        "previous_reported_quarter_gross_profit_persistence",
    ]
    assert tournament.winner_candidate_id is None
    assert tournament.outcome_scoring_available is False
    assert tournament.comparable_candidate_ids == ()
    assert sum(item.tournament_eligible for item in tournament.candidates) == 1
    assert "candidate_training_cutoff_authority_unavailable" in tournament.blockers


def test_six_horizon_cells_never_turn_missing_dimensions_into_zero() -> None:
    bundle = _bundle()
    assert [(item.security_id, item.horizon_months) for item in bundle.opportunities] == [
        ("000660", 3), ("000660", 6), ("000660", 12),
        ("005930", 3), ("005930", 6), ("005930", 12),
    ]
    for opportunity in bundle.opportunities:
        assert opportunity.partial_rank is None
        assert opportunity.overall_rank is None
        assert all(item.payload()["numeric_score"] is None for item in opportunity.dimensions)
    forecast = next(
        item for item in bundle.opportunities[0].dimensions if item.name == "prospective_forecast"
    )
    assert forecast.status is EvidenceStatus.INCOMPARABLE
    assert all(
        next(item for item in row.dimensions if item.name == "valuation").status
        is EvidenceStatus.BLOCKED
        for row in bundle.opportunities
    )


def test_caller_mutation_cannot_self_authorize_persistence(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    forged = replace(bundle, market_snapshot_id="a" * 64)
    with pytest.raises(ForecastTournamentError, match="caller bundle"):
        _persist(forged, tmp_path / "repo", source)


def test_source_mutation_after_registration_fails_replay(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = _persist(bundle, tmp_path / "repo", source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["forecast"]["selected_forecast_krw_million"] += 1
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        _replay(directory, source)


@pytest.mark.parametrize("target", ["feature", "estimator", "raw"])
def test_each_upstream_generation_mutation_fails_replay(tmp_path: Path, target: str) -> None:
    source = _copy_source(tmp_path)
    feature, estimator, capture = _copy_lineage(tmp_path)
    bundle = build_forecast_opportunity_bundle(
        frozen_forecast_path=source,
        frozen_feature_path=feature,
        selected_estimator_path=estimator,
        source_capture_directory=capture,
        captured_at=CAPTURED,
        evaluation_date=date(2026, 8, 25),
        market_snapshot_id=MARKET_ID,
        research_snapshot_id=RESEARCH_ID,
    )
    directory = persist_forecast_opportunity_bundle(
        bundle,
        output_root=tmp_path / "repo",
        frozen_forecast_path=source,
        frozen_feature_path=feature,
        selected_estimator_path=estimator,
        source_capture_directory=capture,
    )
    path = {
        "feature": feature,
        "estimator": estimator,
        "raw": capture / "raw" / "2026Q2.json",
    }[target]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((ForecastTournamentError, ValueError)):
        replay_forecast_opportunity_bundle(
            directory,
            frozen_forecast_path=source,
            frozen_feature_path=feature,
            selected_estimator_path=estimator,
            source_capture_directory=capture,
        )


def test_model_candidate_and_scoring_rule_substitution_cannot_publish(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    model, benchmark = bundle.tournament.candidates
    for candidate in (
        replace(model, model_version_id="a" * 64),
        replace(model, scoring_rule="retrospective_best_error"),
        replace(model, security_id="005930"),
        replace(model, target_period="2026Q4"),
        replace(model, unit="KRW"),
        replace(model, accounting_basis="consolidated_net_income"),
    ):
        forged_tournament = replace(
            bundle.tournament,
            candidates=tuple(sorted((candidate, benchmark), key=lambda item: item.candidate_id)),
        )
        forged = replace(bundle, tournament=forged_tournament)
        with pytest.raises(ForecastTournamentError, match="caller bundle"):
            _persist(forged, tmp_path / "repo", source)


def test_future_cutoff_and_candidate_set_mutation_fail_closed(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    model = bundle.tournament.candidates[0]
    with pytest.raises(ForecastTournamentError, match="cutoff"):
        replace(model, input_cutoff=model.registered_at + timedelta(seconds=1))
    forged = replace(
        bundle,
        tournament=replace(bundle.tournament, candidates=(bundle.tournament.candidates[1],)),
    )
    with pytest.raises(ForecastTournamentError, match="caller bundle"):
        _persist(forged, tmp_path / "repo", source)


def test_registration_after_origin_and_integer_forecast_fail_closed() -> None:
    candidate = _bundle().tournament.candidates[0]
    with pytest.raises(ForecastTournamentError, match="origin"):
        replace(candidate, registered_at=candidate.forecast_origin + timedelta(seconds=1))
    with pytest.raises(ForecastTournamentError, match="canonical finite float"):
        replace(candidate, forecast_value=int(candidate.forecast_value))


def test_bundle_capture_cannot_predate_evaluation_date() -> None:
    with pytest.raises(ForecastTournamentError, match="precede evaluation"):
        forecast, feature, estimator, capture = _test_paths()
        build_forecast_opportunity_bundle(
            frozen_forecast_path=forecast,
            frozen_feature_path=feature,
            selected_estimator_path=estimator,
            source_capture_directory=capture,
            captured_at=CAPTURED,
            evaluation_date=date(2026, 8, 26),
            market_snapshot_id=MARKET_ID,
            research_snapshot_id=RESEARCH_ID,
        )


def test_bundle_capture_uses_korean_market_date() -> None:
    forecast, feature, estimator, capture = _test_paths()
    bundle = build_forecast_opportunity_bundle(
        frozen_forecast_path=forecast,
        frozen_feature_path=feature,
        selected_estimator_path=estimator,
        source_capture_directory=capture,
        captured_at=datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
        evaluation_date=date(2026, 8, 25),
        market_snapshot_id=MARKET_ID,
        research_snapshot_id=RESEARCH_ID,
    )
    assert bundle.evaluation_date == date(2026, 8, 25)


def test_candidate_alias_and_single_candidate_winner_fail_closed() -> None:
    bundle = _bundle()
    first, second = bundle.tournament.candidates
    with pytest.raises(ForecastTournamentError, match="duplicate candidate"):
        replace(
            bundle.tournament,
            candidates=(first, replace(second, candidate_id="lagged-gp affine_ols")),
        )
    eligible = next(item for item in (first, second) if item.tournament_eligible)
    with pytest.raises(ForecastTournamentError, match="at least two"):
        replace(
            bundle.tournament,
            candidates=(eligible,),
            comparable_candidate_ids=(eligible.candidate_id,),
            winner_candidate_id=eligible.candidate_id,
            outcome_scoring_available=False,
        )


def test_round_trip_and_duplicate_json_key_rejection(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = _persist(bundle, tmp_path / "repo", source)
    assert _replay(directory, source) == bundle
    path = directory / "bundle.json"
    text = path.read_text(encoding="utf-8").replace(
        "{\n", '{\n  "automatic_execution_enabled": true,\n', 1
    )
    path.write_text(text, encoding="utf-8")
    content = path.read_bytes()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["bundle.json"] = hashlib.sha256(content).hexdigest()
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ForecastTournamentError, match="duplicate JSON key"):
        _replay(directory, source)


def test_unknown_field_and_bool_number_alias_fail_closed(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = _persist(bundle, tmp_path / "repo", source)
    original = json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
    for mutation in (
        lambda value: value.__setitem__("unknown", True),
        lambda value: value.__setitem__("schema_version", True),
    ):
        payload = copy.deepcopy(original)
        mutation(payload)
        content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
        (directory / "bundle.json").write_bytes(content)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"]["bundle.json"] = hashlib.sha256(content).hexdigest()
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with pytest.raises(ForecastTournamentError):
            _replay(directory, source)


def test_frozen_source_unknown_bool_alias_and_malformed_utf8_fail_closed(tmp_path: Path) -> None:
    payload = json.loads(_test_paths()[0].read_text(encoding="utf-8"))
    mutations = (
        lambda value: value.__setitem__("unknown", True),
        lambda value: value["forecast"].__setitem__("q3_evaluated", 0),
    )
    for index, mutation in enumerate(mutations):
        changed = copy.deepcopy(payload)
        mutation(changed)
        path = tmp_path / f"source-{index}.json"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ForecastTournamentError):
            _bundle(path)
    malformed = tmp_path / "malformed.json"
    malformed.write_bytes(b"\xff\xfe")
    with pytest.raises(ForecastTournamentError, match="malformed UTF-8/JSON"):
        _bundle(malformed)


def test_self_hashed_forecast_lineage_mutation_is_not_registered_identity(
    tmp_path: Path,
) -> None:
    source = _copy_source(tmp_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    body = payload["forecast"]
    body["contract_evidence_id"] = "d" * 64
    body_without_id = {key: value for key, value in body.items() if key != "evidence_id"}
    body["evidence_id"] = numeric_module._sha(body_without_id)
    source.write_bytes(numeric_module._canonical_bytes(payload))
    with pytest.raises(ForecastTournamentError, match="registered immutable identity"):
        _bundle(source)


@pytest.mark.parametrize(
    ("field", "value"),
    [("condition_number", 1), ("raw_unit_coefficients", [2])],
)
def test_estimator_integer_aliases_fail_closed(
    tmp_path: Path, field: str, value: object
) -> None:
    source = _copy_source(tmp_path)
    feature, estimator, capture = _copy_lineage(tmp_path)
    payload = json.loads(estimator.read_text(encoding="utf-8"))
    payload["selected_estimator"][field] = value
    estimator.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ForecastTournamentError, match="canonical"):
        build_forecast_opportunity_bundle(
            frozen_forecast_path=source,
            frozen_feature_path=feature,
            selected_estimator_path=estimator,
            source_capture_directory=capture,
            captured_at=CAPTURED,
            evaluation_date=date(2026, 8, 25),
            market_snapshot_id=MARKET_ID,
            research_snapshot_id=RESEARCH_ID,
        )


def test_replay_performs_no_network_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = _persist(bundle, tmp_path / "repo", source)

    def forbidden_network(*args, **kwargs):
        raise AssertionError("network access is forbidden during replay")

    import socket

    monkeypatch.setattr(socket, "socket", forbidden_network)
    assert _replay(directory, source) == bundle


def test_atomic_publication_failure_leaves_no_partial_or_foreign_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    repository = tmp_path / "repo"
    foreign = repository / "foreign-artifact"
    foreign.mkdir(parents=True)
    (foreign / "owned.txt").write_text("foreign", encoding="utf-8")

    def fail_rename(source_path: Path, target_path: Path) -> None:
        raise OSError("injected atomic commit failure")

    monkeypatch.setattr(tournament_module.os, "rename", fail_rename)
    with pytest.raises(OSError, match="injected"):
        _persist(bundle, repository, source)
    assert (foreign / "owned.txt").read_text(encoding="utf-8") == "foreign"
    assert {item.name for item in repository.iterdir()} == {"foreign-artifact"}


def test_wrong_artifact_root_binding_is_rejected(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = _persist(bundle, tmp_path / "repo", source)
    renamed = directory.with_name("wrong-root")
    directory.rename(renamed)
    with pytest.raises(ForecastTournamentError, match="directory identity"):
        _replay(renamed, source)


def test_cli_records_real_six_cell_acceptance(tmp_path: Path, capsys) -> None:
    source = _copy_source(tmp_path)
    _, feature, estimator, capture = _test_paths()
    result = cli_main(
        [
            "--frozen-forecast", str(source),
            "--frozen-feature", str(feature),
            "--selected-estimator", str(estimator),
            "--source-capture-directory", str(capture),
            "--market-snapshot-id", MARKET_ID,
            "--research-snapshot-id", RESEARCH_ID,
            "--evaluation-date", "2026-08-25",
            "--captured-at", CAPTURED.isoformat(),
            "--output", str(tmp_path / "acceptance"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert len(payload["opportunities"]) == 6
    assert payload["eligible_candidate_ids"] == [
        "previous_reported_quarter_gross_profit_persistence"
    ]
    assert payload["winner_candidate_id"] is None
    assert payload["overall_ranking_available"] is False


def test_symlink_source_escape_fails_closed(tmp_path: Path) -> None:
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(_test_paths()[0].resolve())
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ForecastTournamentError, match="plain immutable"):
        _bundle(link)
