"""Regression coverage for the Toss-IP-blocked Kiwoom primary fallback."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alpha_cycle.intelligence.kiwoom_primary_market import (
    KiwoomPrimaryEvidenceError,
    build_kiwoom_primary_snapshot,
)
from alpha_cycle.intelligence.kiwoom_primary_provenance import (
    load_kiwoom_primary_provenance,
)
from alpha_cycle.intelligence.market import write_market_intelligence_snapshot

SYMBOLS = ("000660", "005930", "005935")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _case(
    tmp_path: Path,
    *,
    age_minutes: int = 1,
    adjusted: bool = True,
    include_adjustment_evidence: bool = True,
) -> Path:
    root = tmp_path / "live-research"
    source_root = root / "kiwoom-openapi-plus-market"
    export = source_root / "snapshot"
    captured = datetime.now(UTC) - timedelta(minutes=age_minutes)
    snapshot_id = "a" * 64
    quotes = [
        {
            "ticker": symbol,
            "current_price": 100_000 + index * 10_000,
        }
        for index, symbol in enumerate(SYMBOLS)
    ]
    bars: list[dict[str, object]] = []
    adjustment_rows: list[dict[str, object]] = []
    for symbol_index, symbol in enumerate(SYMBOLS):
        base = 100_000 + symbol_index * 10_000
        for index in range(40):
            day = f"20260{6 + (index // 28)}{(index % 28) + 1:02d}"
            bars.append(
                {
                    "ticker": symbol,
                    "date": day,
                    "open_price": base + index,
                    "high_price": base + index + 10,
                    "low_price": base + index - 10,
                    "close_price": base + index + 5,
                    "volume": 1_000_000 + index,
                    "adjusted": adjusted,
                }
            )
            adjustment_rows.append(
                {
                    "ticker": symbol,
                    "date": day,
                    "requested_price_basis": "adjusted",
                    "adjustment_request_value": "1",
                    "response_adjustment_code_raw": "",
                    "response_adjustment_ratio_raw": "",
                    "response_adjustment_event_raw": "",
                    "previous_close_raw": str(base + index),
                }
            )
    _write_csv(export / "quotes.csv", quotes)
    _write_csv(export / "daily_bars.csv", bars)
    if include_adjustment_evidence:
        _write_csv(export / "adjustment_evidence.csv", adjustment_rows)
    manifest = {
        "schema_version": "1.2",
        "status": "completed",
        "provider": "kiwoom_openapi_plus",
        "snapshot_id": snapshot_id,
        "captured_at_utc": captured.isoformat(),
        "symbols": list(SYMBOLS),
        "quotes_file": "quotes.csv",
        "daily_bars_file": "daily_bars.csv",
        "adjustment_evidence_file": "adjustment_evidence.csv",
        "adjusted_prices": adjusted,
        "price_basis": "adjusted" if adjusted else "unadjusted",
        "adjustment_request_value": "1" if adjusted else "0",
        "corporate_action_row_count": 0,
        "account_api_enabled": False,
        "order_api_enabled": False,
    }
    export.mkdir(parents=True, exist_ok=True)
    (export / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pointer = {
        "status": "completed",
        "provider": "kiwoom_openapi_plus",
        "snapshot_id": snapshot_id,
        "export_directory": str(export),
        "adjusted_prices": adjusted,
        "price_basis": "adjusted" if adjusted else "unadjusted",
    }
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "latest_market_export.json").write_text(
        json.dumps(pointer), encoding="utf-8"
    )
    return root


def test_fresh_adjusted_kiwoom_export_builds_standard_market_snapshot(
    tmp_path: Path,
) -> None:
    root = _case(tmp_path)

    snapshot = build_kiwoom_primary_snapshot(root, count=30)

    assert snapshot.provider == "kiwoom_openapi_plus_primary_readonly"
    assert snapshot.symbols == SYMBOLS
    assert len(snapshot.prices) == 3
    assert len(snapshot.candles) == 90
    assert snapshot.adjusted is True
    assert all(item.adjusted is True for item in snapshot.candles)
    assert all(item.currency == "KRW" for item in snapshot.prices)
    assert snapshot.raw_prices["price_basis"] == "adjusted"


def test_unadjusted_kiwoom_export_remains_fail_closed(tmp_path: Path) -> None:
    root = _case(tmp_path, adjusted=False)

    with pytest.raises(KiwoomPrimaryEvidenceError, match="must be true"):
        build_kiwoom_primary_snapshot(root, count=30)


def test_missing_adjustment_evidence_remains_fail_closed(tmp_path: Path) -> None:
    root = _case(tmp_path, include_adjustment_evidence=False)

    with pytest.raises(KiwoomPrimaryEvidenceError, match="evidence file is missing"):
        build_kiwoom_primary_snapshot(root, count=30)


def test_stale_kiwoom_export_remains_fail_closed(tmp_path: Path) -> None:
    root = _case(tmp_path, age_minutes=60)

    with pytest.raises(KiwoomPrimaryEvidenceError, match="not fresh enough"):
        build_kiwoom_primary_snapshot(root, count=30, max_age_minutes=30)


def test_market_snapshot_links_explicit_single_provider_provenance(tmp_path: Path) -> None:
    root = _case(tmp_path)
    snapshot = build_kiwoom_primary_snapshot(root, count=30)
    files = write_market_intelligence_snapshot(root / "market-intelligence", snapshot)
    market_directory = files[0].parent

    provenance = load_kiwoom_primary_provenance(
        market_directory,
        decision_symbols=("005930", "000660"),
    )

    assert provenance.mode == "kiwoom_primary_only"
    assert provenance.market_snapshot_id == snapshot.snapshot_id
    assert provenance.kiwoom_snapshot_id == "a" * 64
    assert provenance.historical_verified is False
    assert provenance.live_price_certified is False
    assert provenance.decision_integration_eligible is False
    assert provenance.classification == "kiwoom_primary_tossinvest_ip_blocked"
    assert "account_api_disabled" in provenance.warnings
    assert "order_api_disabled" in provenance.warnings
    assert "automatic_provider_substitution_disabled" in provenance.warnings


def test_windows_bootstrap_routes_through_provider_orchestrator() -> None:
    root = Path(__file__).resolve().parents[2]
    bootstrap = (root / "scripts" / "run_live_pipeline_bootstrap.ps1").read_text(
        encoding="utf-8"
    )
    orchestrator = (root / "scripts" / "run_live_pipeline_orchestrator.ps1").read_text(
        encoding="utf-8"
    )
    exporter = (root / "scripts" / "export_kiwoom_openapi_plus_market.ps1").read_text(
        encoding="utf-8"
    )

    assert '"run_live_pipeline_orchestrator.ps1"' in bootstrap
    assert "export_kiwoom_openapi_plus_market.ps1" in orchestrator
    assert "alpha_cycle.kiwoom_primary_pipeline_cli" in orchestrator
    assert 'status.reason -eq "tossinvest_ip_allowlist"' in orchestrator
    assert 'status.reason -eq "resume_unavailable"' in orchestrator
    assert "adjusted daily-bar evidence" in exporter
    assert "Account, holdings, balance, and order APIs remain disabled." in exporter


def test_windows_orchestrator_validates_post_write_export_before_recovery() -> None:
    root = Path(__file__).resolve().parents[2]
    exporter = (
        root / "scripts" / "export_kiwoom_openapi_plus_market.ps1"
    ).read_text(encoding="utf-8")
    orchestrator = (
        root / "scripts" / "run_live_pipeline_orchestrator.ps1"
    ).read_text(encoding="utf-8")

    assert '[string]$OutputRoot = ""' in exporter
    assert '"--output-root"' in exporter
    assert "$exportExitCode = $LASTEXITCODE" in exporter

    assert "function Test-NewKiwoomExport" in orchestrator
    assert "$pointerBefore = Read-JsonFile" in orchestrator
    assert "$pointerAfter = Read-JsonFile" in orchestrator
    assert "-OutputRoot $KiwoomOutputRoot" in orchestrator
    assert "if (-not $freshKiwoomExport)" in orchestrator
    assert "after publishing a new valid evidence bundle" in orchestrator
    assert "Continuing through downstream provenance validation." in orchestrator
    assert (
        'if ($null -ne $Before -and [string]$Before.snapshot_id -eq $snapshotId)'
        in orchestrator
    )
    assert (
        '-not (Test-FalseBooleanProperty -Value $manifest '
        '-Name "account_api_enabled")'
        in orchestrator
    )
