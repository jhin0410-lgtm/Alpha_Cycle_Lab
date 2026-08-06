"""Regression tests for explicit read-only Kiwoom market failover."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from alpha_cycle import pipeline_decision_provenance as runtime_module
from alpha_cycle.intelligence.kiwoom_primary_market import (
    EXPECTED_SYMBOLS,
    PRIMARY_PROVIDER,
    KiwoomPrimaryMarketError,
    build_kiwoom_primary_snapshot,
    write_kiwoom_primary_snapshot,
)
from alpha_cycle.intelligence.kiwoom_primary_market_loader import (
    load_kiwoom_primary_snapshot,
)
from alpha_cycle.intelligence.kiwoom_primary_provenance import (
    CLASSIFICATION,
    run_kiwoom_primary_market_gate,
)
from alpha_cycle.pipeline_decision_provenance import (
    PipelineDecisionProvenanceRuntime,
)

ROOT = Path(__file__).resolve().parents[2]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _source_case(
    tmp_path: Path,
    *,
    captured_at: datetime,
    daily_count: int = 25,
    account_api_enabled: bool = False,
) -> Path:
    output_root = tmp_path / "live-research"
    source_root = output_root / "kiwoom-openapi-plus-market"
    export_directory = source_root / "export"
    quotes = [
        {
            "ticker": ticker,
            "current_price": 100_000 + index * 10_000,
        }
        for index, ticker in enumerate(EXPECTED_SYMBOLS)
    ]
    bars: list[dict[str, object]] = []
    first = datetime(2026, 6, 1, tzinfo=UTC)
    for symbol_index, ticker in enumerate(EXPECTED_SYMBOLS):
        base = 100_000 + symbol_index * 10_000
        for index in range(daily_count):
            session = first + timedelta(days=index)
            bars.append(
                {
                    "ticker": ticker,
                    "date": session.strftime("%Y%m%d"),
                    "open_price": base + index,
                    "high_price": base + index + 10,
                    "low_price": base + index - 10,
                    "close_price": base + index + 5,
                    "volume": 1_000_000 + index,
                    "adjusted": False,
                }
            )
    _write_csv(export_directory / "quotes.csv", quotes)
    _write_csv(export_directory / "daily_bars.csv", bars)
    source_id = hashlib.sha256(b"kiwoom-export").hexdigest()
    manifest = {
        "schema_version": "1.0",
        "status": "completed",
        "provider": "kiwoom_openapi_plus",
        "snapshot_id": source_id,
        "captured_at_utc": captured_at.isoformat(),
        "captured_at_kst": captured_at.astimezone().isoformat(),
        "connected": True,
        "symbols": list(EXPECTED_SYMBOLS),
        "quote_count": len(quotes),
        "daily_bar_count": len(bars),
        "adjusted_prices": False,
        "quotes_file": "quotes.csv",
        "daily_bars_file": "daily_bars.csv",
        "account_api_enabled": account_api_enabled,
        "order_api_enabled": False,
    }
    manifest_path = export_directory / "manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(
        source_root / "latest_market_export.json",
        {
            "status": "completed",
            "provider": "kiwoom_openapi_plus",
            "snapshot_id": source_id,
            "captured_at_utc": captured_at.isoformat(),
            "symbols": list(EXPECTED_SYMBOLS),
            "export_directory": str(export_directory),
            "manifest_path": str(manifest_path),
            "account_api_enabled": False,
            "order_api_enabled": False,
        },
    )
    return output_root


def test_fresh_kiwoom_export_becomes_replayable_market_snapshot(tmp_path: Path) -> None:
    captured_at = datetime.now(UTC) - timedelta(minutes=1)
    output_root = _source_case(tmp_path, captured_at=captured_at)

    primary = build_kiwoom_primary_snapshot(
        output_root,
        candle_count=21,
        max_age_minutes=30,
        fallback_reason="tossinvest_ip_allowlist",
        now=captured_at + timedelta(minutes=1),
    )
    files = write_kiwoom_primary_snapshot(output_root, primary)
    loaded = load_kiwoom_primary_snapshot(files[0].parent, max_age_minutes=30)

    assert loaded.provider == PRIMARY_PROVIDER
    assert loaded.snapshot_id == primary.snapshot.snapshot_id
    assert loaded.symbols == EXPECTED_SYMBOLS
    assert len(loaded.prices) == 3
    assert len(loaded.candles) == 63
    assert all(item.currency == "KRW" for item in loaded.prices)
    raw = json.loads((files[0].parent / "raw_prices.json").read_text(encoding="utf-8"))
    assert raw["fallback_reason"] == "tossinvest_ip_allowlist"
    assert raw["cross_provider_price_certified"] is False
    assert raw["account_api_enabled"] is False
    assert raw["order_api_enabled"] is False


def test_stale_or_account_enabled_kiwoom_export_is_rejected(tmp_path: Path) -> None:
    stale = datetime.now(UTC) - timedelta(hours=2)
    output_root = _source_case(tmp_path / "stale", captured_at=stale)
    with pytest.raises(KiwoomPrimaryMarketError, match="stale"):
        build_kiwoom_primary_snapshot(
            output_root,
            candle_count=21,
            max_age_minutes=30,
            fallback_reason="tossinvest_ip_allowlist",
        )

    unsafe_root = _source_case(
        tmp_path / "unsafe",
        captured_at=datetime.now(UTC),
        account_api_enabled=True,
    )
    with pytest.raises(KiwoomPrimaryMarketError, match="account_api_enabled"):
        build_kiwoom_primary_snapshot(
            unsafe_root,
            candle_count=21,
            max_age_minutes=30,
            fallback_reason="tossinvest_ip_allowlist",
        )


def test_kiwoom_primary_gate_records_single_provider_limitations(tmp_path: Path) -> None:
    captured_at = datetime.now(UTC) - timedelta(minutes=1)
    output_root = _source_case(tmp_path, captured_at=captured_at)
    primary = build_kiwoom_primary_snapshot(
        output_root,
        candle_count=21,
        max_age_minutes=30,
        fallback_reason="tossinvest_ip_allowlist",
    )
    files = write_kiwoom_primary_snapshot(output_root, primary)

    gate = run_kiwoom_primary_market_gate(
        output_root=output_root,
        market_directory=files[0].parent,
        decision_symbols=("005930", "000660"),
    )

    assert gate.provenance.mode == "kiwoom_primary_readonly"
    assert gate.provenance.raw_status == "primary_source_only"
    assert gate.provenance.classification == CLASSIFICATION
    assert gate.provenance.historical_verified is False
    assert gate.provenance.live_price_certified is False
    assert gate.provenance.decision_integration_eligible is False
    assert gate.raw_result_path.is_file()
    assert gate.assessment_path.is_file()
    pointer = json.loads(
        (output_root / "latest_primary_market_provenance.json").read_text(
            encoding="utf-8"
        )
    )
    assert pointer["status"] == "primary_source_only"
    assert pointer["automatic_provider_substitution_enabled"] is False
    assert pointer["account_api_enabled"] is False
    assert pointer["order_api_enabled"] is False


def test_runtime_selects_kiwoom_gate_by_manifest_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "live-research"
    market_directory = output_root / "market-intelligence" / "snapshot"
    market_directory.mkdir(parents=True)
    _write_json(
        market_directory / "manifest.json",
        {"provider": PRIMARY_PROVIDER},
    )
    sentinel = SimpleNamespace(
        raw_result_path=tmp_path / "raw.json",
        assessment_path=tmp_path / "assessment.json",
        provenance=SimpleNamespace(),
    )
    calls: list[dict[str, object]] = []

    def fake_gate(**kwargs: object) -> object:
        calls.append(dict(kwargs))
        return sentinel

    monkeypatch.setattr(runtime_module, "run_kiwoom_primary_market_gate", fake_gate)
    monkeypatch.setattr(
        runtime_module,
        "run_pipeline_market_consistency_gate",
        lambda **_kwargs: pytest.fail("strict cross-provider gate should not run"),
    )
    runtime = PipelineDecisionProvenanceRuntime(("005930", "000660"))

    runtime.prepare(market_directory)

    assert runtime.gate is sentinel
    assert calls == [
        {
            "output_root": output_root,
            "market_directory": market_directory.resolve(),
            "decision_symbols": ("005930", "000660"),
        }
    ]


def test_windows_bootstrap_continues_resume_failure_through_kiwoom() -> None:
    bootstrap = (ROOT / "scripts/run_live_pipeline_bootstrap.ps1").read_text(
        encoding="utf-8"
    )
    failover = (ROOT / "scripts/run_kiwoom_primary_failover.ps1").read_text(
        encoding="utf-8"
    )
    exporter = (ROOT / "scripts/export_kiwoom_openapi_plus_market.ps1").read_text(
        encoding="utf-8"
    )
    wrapper = (ROOT / "src/alpha_cycle/live_pipeline_provenance_cli.py").read_text(
        encoding="utf-8"
    )

    assert '$status.reason -ne "resume_unavailable"' in bootstrap
    assert "run_kiwoom_primary_failover.ps1" in bootstrap
    assert "export_kiwoom_openapi_plus_market.ps1" in failover
    assert "alpha_cycle.kiwoom_primary_market_cli" in failover
    assert "ALPHA_CYCLE_PRIMARY_MARKET_SNAPSHOT" in failover
    assert "ALPHA_CYCLE_PRIMARY_MARKET_REASON" in failover
    assert "-OutputRoot $KiwoomOutputRoot" in failover
    assert '"--output-root"' in exporter
    assert "_PinnedTossBoundary" in wrapper
    assert "load_kiwoom_primary_snapshot" in wrapper
    assert '"automatic_provider_substitution_enabled": False' in wrapper
    assert '"account_api_enabled": False' in wrapper
    assert '"order_api_enabled": False' in wrapper
