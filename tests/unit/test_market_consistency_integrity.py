"""Tests for the fail-closed market consistency integrity wrapper."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from alpha_cycle import market_consistency_cli as core
from alpha_cycle import market_consistency_integrity as integrity


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_non_finite_tolerance_invalidates_latest_pointer(tmp_path: Path) -> None:
    old_pointer = tmp_path / "latest_market_consistency.json"
    old_pointer.write_text(
        json.dumps(
            {
                "status": "passed",
                "result_id": "stale-success",
                "decision_integration_eligible": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(core.ConsistencyError, match="finite decimals"):
        integrity.run_consistency_check(
            output_root=tmp_path,
            required_days=20,
            price_tolerance_won=Decimal("NaN"),
            live_tolerance_bps=Decimal(50),
            max_snapshot_age_minutes=30,
            max_capture_gap_seconds=60,
            now=datetime(2026, 8, 4, 8, 0, tzinfo=UTC),
        )

    pointer = json.loads(old_pointer.read_text(encoding="utf-8"))
    assert pointer["status"] == "failed_validation"
    assert pointer["result_id"] is None
    assert pointer["result_path"] is None
    assert pointer["decision_integration_eligible"] is False
    assert pointer["account_api_enabled"] is False
    assert pointer["order_api_enabled"] is False


def test_duplicate_live_quote_rows_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    _write_csv(
        path,
        [
            {"symbol": "000660", "last_price": 1},
            {"symbol": "000660", "last_price": 2},
            {"symbol": "005930", "last_price": 3},
            {"symbol": "005935", "last_price": 4},
        ],
    )

    with pytest.raises(core.ConsistencyError, match="duplicate symbols: 000660"):
        integrity._validate_unique_rows(
            path,
            symbol_field="symbol",
            provider="TossInvest",
        )


def test_collision_free_clock_never_reuses_existing_result_directory(
    tmp_path: Path,
) -> None:
    requested = datetime(2026, 8, 4, 8, 0, 30, tzinfo=UTC)
    existing_name = requested.astimezone(core.KOREA_TZ).strftime("%Y%m%dT%H%M%S%z")
    existing = tmp_path / "market-source-consistency" / existing_name
    existing.mkdir(parents=True)
    marker = existing / "immutable.txt"
    marker.write_text("preserve", encoding="utf-8")

    selected = integrity._collision_free_checked_at(tmp_path, requested)

    assert selected == requested - timedelta(seconds=1)
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_wrapper_passes_a_collision_free_clock_to_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = datetime(2026, 8, 4, 8, 0, 30, tzinfo=UTC)
    existing_name = requested.astimezone(core.KOREA_TZ).strftime("%Y%m%dT%H%M%S%z")
    (tmp_path / "market-source-consistency" / existing_name).mkdir(parents=True)
    observed: dict[str, object] = {}
    sentinel_path = tmp_path / "result" / "consistency.json"

    monkeypatch.setattr(integrity, "_preflight_evidence", lambda _root: None)

    def fake_run(**kwargs: object) -> tuple[object, Path]:
        observed.update(kwargs)
        return object(), sentinel_path

    monkeypatch.setattr(core, "run_consistency_check", fake_run)

    result, path = integrity.run_consistency_check(
        output_root=tmp_path,
        required_days=20,
        price_tolerance_won=Decimal(0),
        live_tolerance_bps=Decimal(50),
        max_snapshot_age_minutes=30,
        max_capture_gap_seconds=60,
        now=requested,
    )

    assert result is not None
    assert path == sentinel_path
    assert observed["now"] == requested - timedelta(seconds=1)


def test_windows_command_uses_integrity_protected_runner() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_market_source_consistency.cmd"
    ).read_text(encoding="utf-8")

    assert "alpha_cycle.market_consistency_integrity_runner_cli" in script
    assert "run_alpha_cycle_module.ps1" in script
