from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

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
from alpha_cycle.investment_thesis_repository_v2_1 import (
    InvestmentThesisRepositoryError,
    find_latest_investment_thesis,
    load_investment_thesis,
    persist_investment_thesis,
)

NOW = datetime(2026, 8, 23, 6, 0, tzinfo=UTC)


def _uncertainty() -> ThesisUncertainty:
    dimension = UncertaintyDimension(
        level=UncertaintyLevel.HIGH,
        rationale="Prospective evidence is incomplete.",
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
    captured_at: datetime = NOW,
    version: int = 1,
    parent_snapshot_id: str | None = None,
) -> InvestmentThesisSnapshot:
    return InvestmentThesisSnapshot(
        thesis_id=f"thesis-{security_id}",
        snapshot_version=version,
        parent_snapshot_id=parent_snapshot_id,
        captured_at=captured_at,
        security_id=security_id,
        horizon_trading_days=120,
        variant_view="Research priority only; no investability conclusion.",
        why_now="Semiconductor earnings transmission requires prospective underwriting.",
        claims=(
            ThesisClaim(
                claim_id="claim-1",
                category="industry_cycle",
                statement="Memory-cycle transmission remains an economic hypothesis.",
                epistemic_status=EpistemicStatus.ECONOMIC_HYPOTHESIS,
                direction=ClaimDirection.POSITIVE,
            ),
        ),
        catalysts=(),
        forecast_refs=(),
        scenario_refs=(),
        uncertainty=_uncertainty(),
        kill_conditions=(),
        first_rejection_risk="The cycle may already be reflected in price.",
        portfolio_overlap=(),
        opportunity_set_refs=(),
        status=ThesisStatus.RESEARCH_PRIORITY,
    )


def test_persist_and_load_round_trip(tmp_path) -> None:
    thesis = _thesis()
    path = persist_investment_thesis(thesis, artifact_root=tmp_path)
    loaded = load_investment_thesis(path)
    assert loaded == thesis
    assert path.stem == thesis.snapshot_id
    with pytest.raises(FileExistsError):
        persist_investment_thesis(thesis, artifact_root=tmp_path)


def test_loader_rejects_payload_tampering(tmp_path) -> None:
    thesis = _thesis()
    path = persist_investment_thesis(thesis, artifact_root=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["why_now"] = "tampered after persistence"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(InvestmentThesisRepositoryError, match="canonical payload"):
        load_investment_thesis(path)


def test_loader_rejects_arbitrary_json_named_like_snapshot(tmp_path) -> None:
    directory = tmp_path / "investment_thesis_v2_1"
    directory.mkdir()
    path = directory / ("a" * 64 + ".json")
    path.write_text(json.dumps({"snapshot_id": "a" * 64}), encoding="utf-8")
    with pytest.raises(InvestmentThesisRepositoryError):
        load_investment_thesis(path)


def test_latest_selection_uses_embedded_capture_not_filesystem_time(tmp_path) -> None:
    first = _thesis()
    second = replace(
        _thesis(
            captured_at=NOW + timedelta(hours=1),
            version=2,
            parent_snapshot_id=first.snapshot_id,
        ),
        why_now="Later prospective thesis snapshot.",
    )
    first_path = persist_investment_thesis(first, artifact_root=tmp_path)
    second_path = persist_investment_thesis(second, artifact_root=tmp_path)
    first_path.touch()
    selected = find_latest_investment_thesis(
        tmp_path,
        security_id="000660",
        horizon_trading_days=120,
        as_of=NOW + timedelta(hours=2),
    )
    assert selected == second
    assert second_path.exists()


def test_future_thesis_is_excluded_from_point_in_time_lookup(tmp_path) -> None:
    current = _thesis()
    future = _thesis(captured_at=NOW + timedelta(days=1))
    persist_investment_thesis(current, artifact_root=tmp_path)
    persist_investment_thesis(future, artifact_root=tmp_path)
    selected = find_latest_investment_thesis(
        tmp_path,
        security_id="000660",
        horizon_trading_days=120,
        as_of=NOW + timedelta(hours=1),
    )
    assert selected == current


def test_lookup_requires_exact_security_and_horizon(tmp_path) -> None:
    persist_investment_thesis(_thesis(), artifact_root=tmp_path)
    assert (
        find_latest_investment_thesis(
            tmp_path,
            security_id="005930",
            horizon_trading_days=120,
            as_of=NOW + timedelta(hours=1),
        )
        is None
    )
    assert (
        find_latest_investment_thesis(
            tmp_path,
            security_id="000660",
            horizon_trading_days=60,
            as_of=NOW + timedelta(hours=1),
        )
        is None
    )
