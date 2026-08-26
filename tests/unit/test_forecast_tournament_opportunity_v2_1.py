from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
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

CAPTURED = datetime(2026, 8, 25, 7, 0, tzinfo=UTC)
MARKET_ID = "8" * 64
RESEARCH_ID = "9" * 64
SOURCE = Path(
    "data/private/research/skhynix-company-gp-ex-ante-2026q3-forecast/"
    "numeric-forecast-1fd34ba0f43bc2fbc296a6823f2f313296955d8a3860994b7757eb6e23dad468.json"
)


def _bundle(path: Path = SOURCE):
    return build_forecast_opportunity_bundle(
        frozen_forecast_path=path,
        captured_at=CAPTURED,
        evaluation_date=date(2026, 8, 25),
        market_snapshot_id=MARKET_ID,
        research_snapshot_id=RESEARCH_ID,
    )


def _copy_source(tmp_path: Path) -> Path:
    target = tmp_path / "frozen.json"
    target.write_bytes(SOURCE.read_bytes())
    return target


def _copy_lineage(tmp_path: Path) -> tuple[Path, Path, Path]:
    feature = tmp_path / "feature.json"
    estimator = tmp_path / "estimator.json"
    capture = tmp_path / "capture"
    feature.write_bytes(tournament_module.DEFAULT_FEATURE.read_bytes())
    estimator.write_bytes(tournament_module.DEFAULT_ESTIMATOR.read_bytes())
    (capture / "raw").mkdir(parents=True)
    source_capture = tournament_module.DEFAULT_SOURCE_CAPTURE_DIRECTORY
    (capture / "capture.json").write_bytes((source_capture / "capture.json").read_bytes())
    (capture / "raw" / "2026Q2.json").write_bytes(
        (source_capture / "raw" / "2026Q2.json").read_bytes()
    )
    return feature, estimator, capture


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
        persist_forecast_opportunity_bundle(
            forged, output_root=tmp_path / "repo", frozen_forecast_path=source
        )


def test_source_mutation_after_registration_fails_replay(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = persist_forecast_opportunity_bundle(
        bundle, output_root=tmp_path / "repo", frozen_forecast_path=source
    )
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["forecast"]["selected_forecast_krw_million"] += 1
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        replay_forecast_opportunity_bundle(directory, frozen_forecast_path=source)


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
            persist_forecast_opportunity_bundle(
                forged, output_root=tmp_path / "repo", frozen_forecast_path=source
            )


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
        persist_forecast_opportunity_bundle(
            forged, output_root=tmp_path / "repo", frozen_forecast_path=source
        )


def test_registration_after_origin_and_integer_forecast_fail_closed() -> None:
    candidate = _bundle().tournament.candidates[0]
    with pytest.raises(ForecastTournamentError, match="origin"):
        replace(candidate, registered_at=candidate.forecast_origin + timedelta(seconds=1))
    with pytest.raises(ForecastTournamentError, match="canonical finite float"):
        replace(candidate, forecast_value=int(candidate.forecast_value))


def test_bundle_capture_cannot_predate_evaluation_date() -> None:
    with pytest.raises(ForecastTournamentError, match="precede evaluation"):
        build_forecast_opportunity_bundle(
            frozen_forecast_path=SOURCE,
            captured_at=CAPTURED,
            evaluation_date=date(2026, 8, 26),
            market_snapshot_id=MARKET_ID,
            research_snapshot_id=RESEARCH_ID,
        )


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
    directory = persist_forecast_opportunity_bundle(
        bundle, output_root=tmp_path / "repo", frozen_forecast_path=source
    )
    assert replay_forecast_opportunity_bundle(directory, frozen_forecast_path=source) == bundle
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
        replay_forecast_opportunity_bundle(directory, frozen_forecast_path=source)


def test_unknown_field_and_bool_number_alias_fail_closed(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = persist_forecast_opportunity_bundle(
        bundle, output_root=tmp_path / "repo", frozen_forecast_path=source
    )
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
            replay_forecast_opportunity_bundle(directory, frozen_forecast_path=source)


def test_frozen_source_unknown_bool_alias_and_malformed_utf8_fail_closed(tmp_path: Path) -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
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


def test_replay_performs_no_network_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = persist_forecast_opportunity_bundle(
        bundle, output_root=tmp_path / "repo", frozen_forecast_path=source
    )

    def forbidden_network(*args, **kwargs):
        raise AssertionError("network access is forbidden during replay")

    import socket

    monkeypatch.setattr(socket, "socket", forbidden_network)
    assert replay_forecast_opportunity_bundle(directory, frozen_forecast_path=source) == bundle


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
        persist_forecast_opportunity_bundle(
            bundle, output_root=repository, frozen_forecast_path=source
        )
    assert (foreign / "owned.txt").read_text(encoding="utf-8") == "foreign"
    assert {item.name for item in repository.iterdir()} == {"foreign-artifact"}


def test_wrong_artifact_root_binding_is_rejected(tmp_path: Path) -> None:
    source = _copy_source(tmp_path)
    bundle = _bundle(source)
    directory = persist_forecast_opportunity_bundle(
        bundle, output_root=tmp_path / "repo", frozen_forecast_path=source
    )
    renamed = directory.with_name("wrong-root")
    directory.rename(renamed)
    with pytest.raises(ForecastTournamentError, match="directory identity"):
        replay_forecast_opportunity_bundle(renamed, frozen_forecast_path=source)


def test_cli_records_real_six_cell_acceptance(tmp_path: Path, capsys) -> None:
    source = _copy_source(tmp_path)
    result = cli_main(
        [
            "--frozen-forecast", str(source),
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
        link.symlink_to(SOURCE.resolve())
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ForecastTournamentError, match="plain immutable"):
        _bundle(link)
