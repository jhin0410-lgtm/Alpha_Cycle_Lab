from __future__ import annotations

from pathlib import Path


def test_refresh_historical_pb_script_preserves_source_sequence() -> None:
    source = Path("scripts/refresh_historical_pb.ps1").read_text(encoding="utf-8")

    assert "latest_run.json" in source
    assert "status -ne \"completed\"" in source
    assert "export_kiwoom_openapi_plus_valuation_history.ps1" in source
    assert "alpha_cycle.opendart_stock_totals_history_cli" in source
    assert "alpha_cycle.historical_pb_cli" in source
    assert "alpha_cycle.historical_pb_readiness_cli" in source
    assert "[int]$DailyCount = 600" in source
    assert "[int]$TimeoutSeconds = 600" in source
    assert "run_live_pipeline.cmd" in source

    kiwoom = source.index("kiwoom_valuation_history")
    shares = source.index("alpha_cycle.opendart_stock_totals_history_cli")
    pb = source.index("alpha_cycle.historical_pb_cli")
    readiness = source.index("alpha_cycle.historical_pb_readiness_cli")
    assert kiwoom < shares < pb < readiness


def test_refresh_launcher_delegates_to_powershell() -> None:
    source = Path("scripts/refresh_historical_pb.cmd").read_text(encoding="utf-8")

    assert "refresh_historical_pb.ps1" in source
    assert "ExecutionPolicy Bypass" in source
    assert "exit /b %EXIT_CODE%" in source
