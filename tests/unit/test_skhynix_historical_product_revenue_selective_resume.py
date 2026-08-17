from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from alpha_cycle.intelligence import (
    sk_hynix_opendart_historical_product_revenue_panel as panel,
)


_EVALUATION_DATE = date(2026, 8, 16)
_CAPTURED_AT = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)


def _period_specs() -> dict[str, object]:
    return {
        panel.historical_period_id(spec): spec
        for spec in panel.load_historical_product_revenue_specs()
    }


def _install_fake_certification_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    specs: dict[str, object],
    *,
    reject_old_periods: frozenset[str] = frozenset(),
) -> tuple[list[str], list[str], list[str]]:
    replayed: list[str] = []
    bound: list[str] = []
    captured: list[str] = []

    def fake_replay(pointer_path: str | Path, spec: object, *, evaluation_date: date) -> None:
        assert evaluation_date == _EVALUATION_DATE
        period_id = Path(pointer_path).parent.name
        replayed.append(period_id)
        payload = json.loads(Path(pointer_path).read_text(encoding="utf-8"))
        if period_id in reject_old_periods and payload.get("generation") == "old":
            raise ValueError("stale parser contract candidate")

    def fake_bind(pointer_path: str | Path, spec: object) -> dict[str, object]:
        period_id = Path(pointer_path).parent.name
        bound.append(period_id)
        return {"chain_evidence_id": "b" * 64}

    def fake_load(pointer_path: str | Path, *, evaluation_date: date) -> object:
        assert evaluation_date == _EVALUATION_DATE
        period_id = Path(pointer_path).parent.name
        spec = specs[period_id]
        return SimpleNamespace(
            evidence_id="a" * 64,
            period_end=spec.period_end,  # type: ignore[attr-defined]
            rcept_no="20260816000001",
        )

    def fake_capture(
        client: object,
        spec: object,
        *,
        evaluation_date: date,
        output: str | Path,
        captured_at: datetime,
    ) -> dict[str, object]:
        assert evaluation_date == _EVALUATION_DATE
        assert captured_at == _CAPTURED_AT
        period_id = Path(output).name
        captured.append(period_id)
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)
        pointer = root / "latest_certification.json"
        pointer.write_text(json.dumps({"generation": "fresh"}), encoding="utf-8")
        return {"status": "skhynix_opendart_q2_product_revenue_certified"}

    monkeypatch.setattr(
        panel,
        "replay_periodic_product_revenue_certification_against_spec",
        fake_replay,
    )
    monkeypatch.setattr(panel, "bind_periodic_product_revenue_parser_contract", fake_bind)
    monkeypatch.setattr(panel, "load_periodic_product_revenue_certification", fake_load)
    monkeypatch.setattr(panel, "capture_periodic_product_revenue_certification", fake_capture)
    return replayed, bound, captured


def _seed_old_pointer(root: Path, period_id: str) -> None:
    directory = root / period_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "latest_certification.json").write_text(
        json.dumps({"generation": "old"}),
        encoding="utf-8",
    )


def test_selective_resume_reuses_two_valid_periods_and_captures_only_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = _period_specs()
    _seed_old_pointer(tmp_path, "2025Q2")
    _seed_old_pointer(tmp_path, "2025Q3")
    replayed, bound, captured = _install_fake_certification_pipeline(monkeypatch, specs)

    result = panel.capture_historical_product_revenue_panel(
        object(),  # type: ignore[arg-type]
        evaluation_date=_EVALUATION_DATE,
        output=tmp_path,
        captured_at=_CAPTURED_AT,
        resume_valid_existing=True,
    )

    assert result["reused_periods"] == ["2025Q2", "2025Q3"]
    assert result["reuse_rejected_periods"] == []
    assert result["capture_attempted_periods"] == [
        "2023Q1",
        "2023Q2",
        "2023Q3",
        "2024Q1",
        "2024Q2",
        "2024Q3",
        "2025Q1",
        "2026Q1",
    ]
    assert captured == result["capture_attempted_periods"]
    assert set(replayed) == set(panel._EXPECTED_PERIODS)
    assert set(bound) == set(panel._EXPECTED_PERIODS)
    assert result["failed_periods"] == ()
    assert result["full_source_coverage_certified"] is True


def test_selective_resume_recaptures_existing_candidate_rejected_by_current_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = _period_specs()
    _seed_old_pointer(tmp_path, "2025Q2")
    _replayed, _bound, captured = _install_fake_certification_pipeline(
        monkeypatch,
        specs,
        reject_old_periods=frozenset({"2025Q2"}),
    )

    result = panel.capture_historical_product_revenue_panel(
        object(),  # type: ignore[arg-type]
        evaluation_date=_EVALUATION_DATE,
        output=tmp_path,
        captured_at=_CAPTURED_AT,
        resume_valid_existing=True,
    )

    assert result["reused_periods"] == []
    assert result["reuse_rejected_periods"] == ["2025Q2"]
    assert result["reuse_rejected_error_types"] == {"2025Q2": "ValueError"}
    assert "2025Q2" in captured
    assert captured == list(panel._EXPECTED_PERIODS)
    assert result["full_source_coverage_certified"] is True


def test_certified_entry_never_binds_before_non_mutating_replay_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = panel.load_historical_product_revenue_specs()[0]
    pointer_path = tmp_path / "latest_certification.json"
    pointer_path.write_text("{}", encoding="utf-8")
    bind_called = False

    def reject_replay(pointer: str | Path, candidate: object, *, evaluation_date: date) -> None:
        raise ValueError("current parser does not reproduce old artifact")

    def forbidden_bind(pointer: str | Path, candidate: object) -> dict[str, object]:
        nonlocal bind_called
        bind_called = True
        return {}

    monkeypatch.setattr(
        panel,
        "replay_periodic_product_revenue_certification_against_spec",
        reject_replay,
    )
    monkeypatch.setattr(panel, "bind_periodic_product_revenue_parser_contract", forbidden_bind)

    with pytest.raises(ValueError, match="does not reproduce"):
        panel._certified_entry(
            period_id="2023Q1",
            spec=spec,
            pointer_path=pointer_path,
            evaluation_date=_EVALUATION_DATE,
        )
    assert bind_called is False
