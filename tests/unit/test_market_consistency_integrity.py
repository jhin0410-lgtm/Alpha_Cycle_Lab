"""Tests for the fail-closed market consistency integrity wrapper."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
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


def _result(*, checked_at: datetime) -> core.ConsistencyResult:
    timestamp = checked_at.isoformat()
    return core.ConsistencyResult(
        schema_version="1.0",
        status="passed_historical_only",
        checked_at_utc=timestamp,
        checked_at_kst=checked_at.astimezone(core.KOREA_TZ).isoformat(),
        expected_symbols=core.EXPECTED_SYMBOLS,
        toss_snapshot_id="toss-id",
        toss_captured_at=timestamp,
        toss_snapshot_age_seconds=0.0,
        toss_directory="toss",
        toss_resolution_source="pinned-test",
        kiwoom_snapshot_id="kiwoom-id",
        kiwoom_captured_at=timestamp,
        kiwoom_snapshot_age_seconds=0.0,
        kiwoom_directory="kiwoom",
        historical_cutoff_date_exclusive="2026-08-04",
        historical_days_required_per_symbol=20,
        historical_rows_compared=60,
        historical_symbols_passed=core.EXPECTED_SYMBOLS,
        historical_price_conflict_count=0,
        historical_volume_mismatch_count=0,
        live_quote_status="not_comparable",
        live_quote_comparable_count=0,
        live_quote_conflict_count=0,
        live_capture_gap_seconds=0.0,
        decision_integration_eligible=False,
        automatic_provider_substitution_enabled=False,
        account_api_enabled=False,
        order_api_enabled=False,
        warnings=(),
        failures=(),
        daily_comparisons_file="daily_price_comparisons.csv",
        quote_comparisons_file="live_quote_comparisons.csv",
        result_id="a" * 64,
    )


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


def test_negative_tolerance_is_rejected_before_classification(tmp_path: Path) -> None:
    with pytest.raises(core.ConsistencyError, match="cannot be negative"):
        integrity.run_consistency_check(
            output_root=tmp_path,
            required_days=20,
            price_tolerance_won=Decimal(-1),
            live_tolerance_bps=Decimal(50),
            max_snapshot_age_minutes=30,
            max_capture_gap_seconds=60,
            now=datetime(2026, 8, 4, 8, 0, tzinfo=UTC),
        )


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


def test_core_consumes_the_exact_pinned_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_at = datetime(2026, 8, 4, 8, 0, 30, tzinfo=UTC)
    toss = (tmp_path / "pinned-toss").resolve()
    kiwoom = (tmp_path / "pinned-kiwoom").resolve()
    evidence = integrity.PinnedEvidence(toss, "pinned", kiwoom)
    observed: dict[str, object] = {}
    sentinel = tmp_path / "staged" / "consistency.json"

    def fake_core(**kwargs: object) -> tuple[core.ConsistencyResult, Path]:
        observed["toss"] = core._resolve_toss_directory(Path("changed-root"))
        observed["kiwoom"] = core._resolve_kiwoom_directory(Path("changed-root"))
        observed["now"] = kwargs["now"]
        return _result(checked_at=checked_at), sentinel

    monkeypatch.setattr(core, "run_consistency_check", fake_core)

    result, result_path = integrity._run_core_with_pinned_evidence(
        staging_root=tmp_path / "staging",
        evidence=evidence,
        required_days=20,
        price_tolerance_won=Decimal(0),
        live_tolerance_bps=Decimal(50),
        max_snapshot_age_minutes=30,
        max_capture_gap_seconds=60,
        checked_at=checked_at,
    )

    assert result.result_id == "a" * 64
    assert result_path == sentinel
    assert observed["toss"] == (toss, "pinned")
    assert observed["kiwoom"] == kiwoom
    assert observed["now"] == checked_at


def test_publish_reserves_unique_directory_without_rewinding_clock(
    tmp_path: Path,
) -> None:
    checked_at = datetime(2026, 8, 4, 8, 0, 30, 123456, tzinfo=UTC)
    result = _result(checked_at=checked_at)
    staging = tmp_path / "staging" / "raw"
    staging.mkdir(parents=True)
    for name in (
        result.daily_comparisons_file,
        result.quote_comparisons_file,
        "consistency.json",
    ):
        (staging / name).write_text(name, encoding="utf-8")

    first = integrity._publish_result(
        output_root=tmp_path,
        result=result,
        staging_result_path=staging / "consistency.json",
        checked_at=checked_at,
    )

    second_staging = tmp_path / "staging-2" / "raw"
    second_staging.mkdir(parents=True)
    for name in (
        result.daily_comparisons_file,
        result.quote_comparisons_file,
        "consistency.json",
    ):
        (second_staging / name).write_text(name, encoding="utf-8")
    second = integrity._publish_result(
        output_root=tmp_path,
        result=result,
        staging_result_path=second_staging / "consistency.json",
        checked_at=checked_at,
    )

    assert first != second
    assert first.is_file()
    assert second.is_file()
    prefix = "20260804T170030123456+0900__aaaaaaaaaaaa__"
    assert first.parent.name.startswith(prefix)
    assert second.parent.name.startswith(prefix)
    pointer = json.loads(
        (tmp_path / "latest_market_consistency.json").read_text(encoding="utf-8")
    )
    assert pointer["checked_at_utc"] == checked_at.isoformat()
    assert pointer["result_path"] == str(second)


def test_csv_parser_failure_invalidates_latest_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integrity,
        "_resolve_and_validate_evidence",
        lambda _root: (_ for _ in ()).throw(csv.Error("field too large")),
    )

    with pytest.raises(core.ConsistencyError, match="malformed CSV evidence"):
        integrity.run_consistency_check(
            output_root=tmp_path,
            required_days=20,
            price_tolerance_won=Decimal(0),
            live_tolerance_bps=Decimal(50),
            max_snapshot_age_minutes=30,
            max_capture_gap_seconds=60,
            now=datetime(2026, 8, 4, 8, 0, tzinfo=UTC),
        )

    pointer = json.loads(
        (tmp_path / "latest_market_consistency.json").read_text(encoding="utf-8")
    )
    assert pointer["status"] == "failed_validation"
    assert pointer["decision_integration_eligible"] is False


def test_windows_command_uses_integrity_protected_runner() -> None:
    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "check_market_source_consistency.cmd"
    ).read_text(encoding="utf-8")

    assert "alpha_cycle.market_consistency_integrity_runner_cli" in script
    assert "run_alpha_cycle_module.ps1" in script
