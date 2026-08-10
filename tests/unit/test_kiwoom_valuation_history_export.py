"""Tests for isolated unadjusted Kiwoom valuation-history evidence."""

from __future__ import annotations

import importlib.util
import json
import runpy
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

HARDENING_PATH = Path(
    "bridge/kiwoom_openapi_plus/valuation_history_export_hardening.py"
)
EXPORTER_PATH = Path("bridge/kiwoom_openapi_plus/market_export.py")
BOOTSTRAP_PATH = Path(
    "bridge/kiwoom_openapi_plus/valuation_history_export_bootstrap.py"
)
POWERSHELL_PATH = Path("scripts/export_kiwoom_openapi_plus_valuation_history.ps1")


def _load_hardening() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kiwoom_valuation_history_hardening_test",
        HARDENING_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class StubQuote:
    ticker: str
    value: int


@dataclass(frozen=True)
class StubBar:
    ticker: str
    date: str
    value: int
    adjusted: bool = False


def _exporter() -> SimpleNamespace:
    return SimpleNamespace(
        login_event_code=0,
        connected=True,
        request_count=6,
        request_gate=SimpleNamespace(interval_seconds=0.25),
        provider_messages=(),
    )


def _namespace() -> tuple[dict[str, Any], ModuleType]:
    hardening = _load_hardening()
    namespace = runpy.run_path(
        str(EXPORTER_PATH),
        run_name="kiwoom_valuation_history_writer_namespace",
    )
    fixed = datetime(2026, 8, 10, 6, 30, 0, 123456, tzinfo=UTC)
    namespace["_capture_now"] = lambda zone: fixed.astimezone(zone)
    hardening.apply_hardening(namespace)
    return namespace, hardening


def test_hardening_preserves_base_unadjusted_collector() -> None:
    hardening = _load_hardening()
    namespace = runpy.run_path(
        str(EXPORTER_PATH),
        run_name="kiwoom_valuation_history_collector_namespace",
    )
    original_daily_bars = namespace["KiwoomMarketExporter"].daily_bars

    hardening.apply_hardening(namespace)

    assert namespace["RequestGate"] is hardening.RollingRequestGate
    assert namespace["ExportManifest"] is hardening.ValuationHistoryExportManifest
    assert namespace["KiwoomMarketExporter"].daily_bars is original_daily_bars
    assert "수정주가구분\", \"0" in EXPORTER_PATH.read_text(encoding="utf-8")


def test_writer_publishes_separate_unadjusted_non_scoring_contract(tmp_path: Path) -> None:
    namespace, hardening = _namespace()
    writer = namespace["write_export"]

    manifest, directory = writer(
        output_root=tmp_path,
        symbols=("005930", "005935", "000660"),
        daily_count=600,
        quotes=[StubQuote("005930", 1)],
        bars=[StubBar("005930", "20260810", 2)],
        exporter=_exporter(),
    )

    assert manifest.source_scope == hardening.SOURCE_SCOPE
    assert manifest.purpose == hardening.PURPOSE
    assert manifest.adjusted_prices is False
    assert manifest.price_basis == "unadjusted"
    assert manifest.adjustment_request_value == "0"
    assert manifest.historical_valuation_use_only is True
    assert manifest.primary_market_evidence_eligible is False
    assert manifest.technical_indicator_eligible is False
    assert manifest.decision_score_enabled is False
    assert manifest.point_in_time_backtest_eligible is False
    assert manifest.account_api_enabled is False
    assert manifest.order_api_enabled is False
    assert directory.name.startswith("20260810T153000123456+0900__")

    pointer_path = tmp_path / hardening.LATEST_POINTER_NAME
    assert pointer_path.is_file()
    assert not (tmp_path / "latest_market_export.json").exists()
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    payload = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for document in (pointer, payload):
        assert document["adjusted_prices"] is False
        assert document["price_basis"] == "unadjusted"
        assert document["adjustment_request_value"] == "0"
        assert document["primary_market_evidence_eligible"] is False
        assert document["technical_indicator_eligible"] is False
        assert document["decision_score_enabled"] is False
        assert document["account_api_enabled"] is False
        assert document["order_api_enabled"] is False


def test_writer_rejects_adjusted_history_rows(tmp_path: Path) -> None:
    namespace, _ = _namespace()
    writer = namespace["write_export"]

    with pytest.raises(ValueError, match="unadjusted daily bars only"):
        writer(
            output_root=tmp_path,
            symbols=("005930",),
            daily_count=600,
            quotes=[StubQuote("005930", 1)],
            bars=[StubBar("005930", "20260810", 2, adjusted=True)],
            exporter=_exporter(),
        )

    assert not tmp_path.exists()


def test_bootstrap_and_windows_launcher_are_isolated_from_primary_export() -> None:
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    powershell = POWERSHELL_PATH.read_text(encoding="utf-8")

    assert "from datetime import UTC" not in bootstrap
    assert "valuation_history_export_hardening.py" in bootstrap
    assert 'run_name="alpha_cycle_kiwoom_valuation_history_export"' in bootstrap
    assert "hardening.apply_hardening(runtime_globals)" in bootstrap
    assert "market_export_hardening.py" not in bootstrap
    assert "kiwoom-openapi-plus-valuation-history" in powershell
    assert '[int]$DailyCount = 600' in powershell
    assert "valuation_history_export_bootstrap.py" in powershell
