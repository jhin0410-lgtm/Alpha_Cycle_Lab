"""Regression tests for Kiwoom bridge Qt platform plugin initialization."""

from __future__ import annotations

from pathlib import Path


INITIALIZER = Path("scripts/initialize_kiwoom_openapi_plus_qt.ps1")
LAUNCHERS = (
    Path("scripts/setup_kiwoom_openapi_plus_bridge.ps1"),
    Path("scripts/check_kiwoom_openapi_plus_bridge.ps1"),
    Path("scripts/login_probe_kiwoom_openapi_plus.ps1"),
)


def test_qt_initializer_requires_windows_platform_plugin() -> None:
    script = INITIALIZER.read_text(encoding="utf-8")

    assert "qwindows.dll" in script
    assert "QT_QPA_PLATFORM_PLUGIN_PATH" in script
    assert "QT_PLUGIN_PATH" in script
    assert 'Join-Path $PyQtRoot "Qt5"' in script
    assert 'Join-Path $QtRoot "bin"' in script
    assert '$env:PATH = "$QtBinDirectory;$env:PATH"' in script


def test_all_kiwoom_bridge_launchers_initialize_qt_runtime() -> None:
    for launcher in LAUNCHERS:
        script = launcher.read_text(encoding="utf-8")
        assert "initialize_kiwoom_openapi_plus_qt.ps1" in script
        initialization = script.rindex(". $QtInitializer -BridgePython")
        if launcher.name == "setup_kiwoom_openapi_plus_bridge.ps1":
            invocation = script.rindex("& $VenvPython $Probe")
        else:
            invocation = script.rindex("& $BridgePython $Probe")
        assert initialization < invocation
