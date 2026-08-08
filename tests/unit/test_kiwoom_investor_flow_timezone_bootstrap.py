"""Regression tests for the Windows investor-flow timezone bootstrap."""

from pathlib import Path

BOOTSTRAP_PATH = Path(
    "bridge/kiwoom_openapi_plus/investor_flow_export_bootstrap.py"
)
LAUNCHER_PATH = Path("scripts/export_kiwoom_openapi_plus_investor_flow.ps1")


def test_investor_flow_launcher_routes_through_timezone_bootstrap() -> None:
    launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert "investor_flow_export_bootstrap.py" in launcher
    assert "investor_flow_export.py" in bootstrap
    assert "ensure_export_timezones()" in bootstrap
    assert "runpy.run_path" in bootstrap
    assert bootstrap.index("ensure_export_timezones()") < bootstrap.index("runpy.run_path")
    assert "tzdata" not in launcher
