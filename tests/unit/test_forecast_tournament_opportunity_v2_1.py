from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle.forecast_tournament_opportunity_v2_1 import (
    EvidenceStatus,
    ForecastTournamentError,
    build_forecast_opportunity_bundle,
    persist_forecast_opportunity_bundle,
    replay_forecast_opportunity_bundle,
)

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


def test_real_frozen_forecast_registers_two_outcome_blind_candidates() -> None:
    bundle = _bundle()
    tournament = bundle.tournament
    assert [item.candidate_id for item in tournament.candidates] == [
        "lagged_gp_affine_ols",
        "previous_reported_quarter_gross_profit_persistence",
    ]
    assert tournament.winner_candidate_id is None
    assert tournament.outcome_scoring_available is False
    assert tournament.blockers == ("authenticated_2026q3_outcome_unavailable",)


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
    assert forecast.status is EvidenceStatus.SUPPORTED
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


def test_registration_after_origin_and_integer_forecast_fail_closed() -> None:
    candidate = _bundle().tournament.candidates[0]
    with pytest.raises(ForecastTournamentError, match="origin"):
        replace(candidate, registered_at=candidate.forecast_origin + timedelta(seconds=1))
    with pytest.raises(ForecastTournamentError, match="canonical finite float"):
        replace(candidate, forecast_value=int(candidate.forecast_value))


def test_candidate_alias_and_single_candidate_winner_fail_closed() -> None:
    bundle = _bundle()
    first, second = bundle.tournament.candidates
    with pytest.raises(ForecastTournamentError, match="duplicate candidate"):
        replace(
            bundle.tournament,
            candidates=(first, replace(second, candidate_id="lagged-gp affine_ols")),
        )
    with pytest.raises(ForecastTournamentError, match="at least two"):
        replace(
            bundle.tournament,
            candidates=(first,),
            comparable_candidate_ids=(first.candidate_id,),
            winner_candidate_id=first.candidate_id,
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


def test_symlink_source_escape_fails_closed(tmp_path: Path) -> None:
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(SOURCE.resolve())
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ForecastTournamentError, match="plain immutable"):
        _bundle(link)
