"""Tests for the isolated Kiwoom OpenAPI+ x86 ActiveX bridge."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PROBE_PATH = Path("bridge/kiwoom_openapi_plus/probe.py")


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("kiwoom_bridge_probe_test", PROBE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeSignal:
    def __init__(self) -> None:
        self.callback: Any = None

    def connect(self, callback: Any) -> None:
        self.callback = callback

    def emit(self, *arguments: object) -> None:
        assert self.callback is not None
        self.callback(*arguments)


class FakeEventLoop:
    def __init__(self) -> None:
        self.quit_requested = False

    def quit(self) -> None:
        self.quit_requested = True

    def exec_(self) -> int:
        return 0


class FakeTimer:
    def __init__(self) -> None:
        self.timeout = FakeSignal()

    def setSingleShot(self, _single_shot: bool) -> None:
        return None

    def start(self, _milliseconds: int) -> None:
        return None

    def stop(self) -> None:
        return None


class FakeApplication:
    @staticmethod
    def instance() -> None:
        return None

    def __init__(self, _arguments: list[str]) -> None:
        pass

    def processEvents(self) -> None:
        return None


class FakeControl:
    def __init__(self) -> None:
        self.OnEventConnect = FakeSignal()
        self.connected = False

    def setControl(self, value: str) -> bool:
        return value == "KHOPENAPI.KHOpenAPICtrl.1"

    def isNull(self) -> bool:
        return False

    def dynamicCall(self, signature: str) -> int:
        if signature == "GetConnectState()":
            return 1 if self.connected else 0
        if signature == "CommConnect()":
            self.connected = True
            self.OnEventConnect.emit(0)
            return 0
        raise AssertionError(f"unexpected ActiveX call: {signature}")


def _fake_qt() -> tuple[object, object, object, str, str]:
    qt_core = SimpleNamespace(QEventLoop=FakeEventLoop, QTimer=FakeTimer)
    qt_widgets = SimpleNamespace(QApplication=FakeApplication)
    return qt_core, qt_widgets, FakeControl, "5.15.11", "5.15.2"


def test_wrong_python_bitness_fails_before_loading_activex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe.platform, "system", lambda: "Windows")
    monkeypatch.setattr(probe.struct, "calcsize", lambda _format: 8)
    monkeypatch.setattr(
        probe,
        "_load_qt",
        lambda: pytest.fail("Qt should not be loaded under 64-bit Python"),
    )

    report = probe.run_probe(mode="environment", timeout_seconds=30)

    assert report.status == "wrong_python_bitness"
    assert report.python_bitness == 64
    assert report.account_api_enabled is False
    assert report.order_api_enabled is False


def test_environment_probe_creates_control_without_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe.platform, "system", lambda: "Windows")
    monkeypatch.setattr(probe.struct, "calcsize", lambda _format: 4)
    monkeypatch.setattr(probe, "_load_qt", _fake_qt)

    report = probe.run_probe(mode="environment", timeout_seconds=30)

    assert report.status == "passed_environment"
    assert report.control_created is True
    assert report.login_attempted is False
    assert report.connected is False
    assert report.market_data_session_ready is False
    assert report.market_data_enabled is False


def test_login_probe_verifies_connection_without_account_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe.platform, "system", lambda: "Windows")
    monkeypatch.setattr(probe.struct, "calcsize", lambda _format: 4)
    monkeypatch.setattr(probe, "_load_qt", _fake_qt)

    report = probe.run_probe(mode="login", timeout_seconds=30)

    assert report.status == "passed_login"
    assert report.login_event_code == 0
    assert report.connected is True
    assert report.service_registration_verified is True
    assert report.market_data_session_ready is True
    assert report.market_data_enabled is False
    assert report.account_api_enabled is False
    assert report.order_api_enabled is False


def test_bridge_files_expose_no_account_or_order_functions() -> None:
    bridge_text = PROBE_PATH.read_text(encoding="utf-8")
    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            Path("scripts/setup_kiwoom_openapi_plus_bridge.ps1"),
            Path("scripts/check_kiwoom_openapi_plus_bridge.ps1"),
            Path("scripts/login_probe_kiwoom_openapi_plus.ps1"),
        )
    )
    combined = bridge_text + scripts

    for forbidden in (
        "SendOrder",
        "GetLoginInfo",
        "계좌번호",
        "주문비밀번호",
        "OPW000",
    ):
        assert forbidden not in combined
    assert "CommConnect()" in bridge_text
    assert "GetConnectState()" in bridge_text


def test_bridge_dependencies_are_pinned_to_win32_capable_versions() -> None:
    requirements = Path(
        "bridge/kiwoom_openapi_plus/requirements-win32.txt"
    ).read_text(encoding="utf-8")

    assert requirements.splitlines() == [
        "PyQt5==5.15.11",
        "PyQt5-Qt5==5.15.2",
        "PyQt5-sip==12.15.0",
    ]


def test_qt_initializer_requires_windows_platform_plugin() -> None:
    initializer = Path("scripts/initialize_kiwoom_openapi_plus_qt.ps1")
    script = initializer.read_text(encoding="utf-8")

    assert "qwindows.dll" in script
    assert "QT_QPA_PLATFORM_PLUGIN_PATH" in script
    assert "QT_PLUGIN_PATH" in script
    assert 'Join-Path $PyQtRoot "Qt5"' in script
    assert 'Join-Path $QtRoot "bin"' in script
    assert '$env:PATH = "$QtBinDirectory;$env:PATH"' in script


def test_all_kiwoom_bridge_launchers_initialize_qt_runtime() -> None:
    launchers = (
        Path("scripts/setup_kiwoom_openapi_plus_bridge.ps1"),
        Path("scripts/check_kiwoom_openapi_plus_bridge.ps1"),
        Path("scripts/login_probe_kiwoom_openapi_plus.ps1"),
    )

    for launcher in launchers:
        script = launcher.read_text(encoding="utf-8")
        assert "initialize_kiwoom_openapi_plus_qt.ps1" in script
        initialization = script.rindex(". $QtInitializer -BridgePython")
        if launcher.name == "setup_kiwoom_openapi_plus_bridge.ps1":
            invocation = script.rindex("& $VenvPython $Probe")
        else:
            invocation = script.rindex("& $BridgePython $Probe")
        assert initialization < invocation
