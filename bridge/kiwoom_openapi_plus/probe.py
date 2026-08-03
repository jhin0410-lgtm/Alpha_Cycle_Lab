"""32-bit Kiwoom OpenAPI+ ActiveX bridge environment and login probe.

This standalone module is executed by a dedicated Windows x86 Python environment.
It never reads account identifiers, passwords, certificates, holdings, or orders.
"""

from __future__ import annotations

import argparse
import json
import platform
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

OPENAPI_PROGID = "KHOPENAPI.KHOpenAPICtrl.1"
DEFAULT_OUTPUT_PATH = Path(
    "data/private/live-research/kiwoom_openapi_plus_bridge_readiness.json"
)
SUCCESS_STATUSES = frozenset({"passed_environment", "passed_login"})


@dataclass(frozen=True)
class BridgeProbeReport:
    status: str
    mode: str
    system_name: str
    python_version: str
    python_bitness: int
    pyqt_version: str | None
    qt_version: str | None
    active_x_available: bool
    control_created: bool
    login_attempted: bool
    login_event_code: int | None
    connected: bool
    service_registration_verified: bool
    market_data_session_ready: bool
    market_data_enabled: bool
    account_api_enabled: bool
    order_api_enabled: bool
    failure: str | None


def _base_report(
    *,
    status: str,
    mode: str,
    pyqt_version: str | None = None,
    qt_version: str | None = None,
    active_x_available: bool = False,
    control_created: bool = False,
    login_attempted: bool = False,
    login_event_code: int | None = None,
    connected: bool = False,
    service_registration_verified: bool = False,
    market_data_session_ready: bool = False,
    market_data_enabled: bool = False,
    failure: str | None = None,
) -> BridgeProbeReport:
    return BridgeProbeReport(
        status=status,
        mode=mode,
        system_name=platform.system(),
        python_version=platform.python_version(),
        python_bitness=struct.calcsize("P") * 8,
        pyqt_version=pyqt_version,
        qt_version=qt_version,
        active_x_available=active_x_available,
        control_created=control_created,
        login_attempted=login_attempted,
        login_event_code=login_event_code,
        connected=connected,
        service_registration_verified=service_registration_verified,
        market_data_session_ready=market_data_session_ready,
        market_data_enabled=market_data_enabled,
        account_api_enabled=False,
        order_api_enabled=False,
        failure=failure,
    )


def _load_qt() -> tuple[Any, Any, Any, str, str]:
    try:
        from PyQt5 import QtCore, QtWidgets
        from PyQt5.QAxContainer import QAxWidget
    except ImportError as exc:
        raise RuntimeError(
            "PyQt5 with QAxContainer is not installed in the x86 bridge environment"
        ) from exc
    return QtCore, QtWidgets, QAxWidget, QtCore.PYQT_VERSION_STR, QtCore.QT_VERSION_STR


def _create_control(qax_widget: Any) -> Any:
    control = qax_widget()
    created = bool(control.setControl(OPENAPI_PROGID))
    if not created or bool(control.isNull()):
        raise RuntimeError(
            "KHOpenAPI ActiveX control could not be created in this Python process"
        )
    return control


def _connection_state(control: Any) -> bool:
    try:
        return int(control.dynamicCall("GetConnectState()")) == 1
    except (TypeError, ValueError):
        return False


def run_probe(*, mode: str, timeout_seconds: int) -> BridgeProbeReport:
    if mode not in {"environment", "login"}:
        raise ValueError("mode must be environment or login")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    if platform.system() != "Windows":
        return _base_report(
            status="unsupported_platform",
            mode=mode,
            failure="Kiwoom OpenAPI+ bridge requires Windows",
        )
    if struct.calcsize("P") * 8 != 32:
        return _base_report(
            status="wrong_python_bitness",
            mode=mode,
            failure="Kiwoom OpenAPI+ bridge must run under 32-bit Python",
        )

    try:
        qt_core, qt_widgets, qax_widget, pyqt_version, qt_version = _load_qt()
    except RuntimeError as exc:
        return _base_report(
            status="runtime_dependency_missing",
            mode=mode,
            failure=str(exc),
        )

    application = qt_widgets.QApplication.instance()
    owns_application = application is None
    if application is None:
        application = qt_widgets.QApplication(["alpha-cycle-kiwoom-bridge"])

    try:
        control = _create_control(qax_widget)
    except RuntimeError as exc:
        return _base_report(
            status="activex_control_unavailable",
            mode=mode,
            pyqt_version=pyqt_version,
            qt_version=qt_version,
            active_x_available=True,
            failure=str(exc),
        )

    if mode == "environment":
        connected = _connection_state(control)
        if owns_application:
            application.processEvents()
        return _base_report(
            status="passed_environment",
            mode=mode,
            pyqt_version=pyqt_version,
            qt_version=qt_version,
            active_x_available=True,
            control_created=True,
            connected=connected,
            service_registration_verified=False,
            market_data_session_ready=False,
            market_data_enabled=False,
        )

    login_event_code: int | None = None
    timed_out = False
    event_loop = qt_core.QEventLoop()

    def on_event_connect(error_code: int) -> None:
        nonlocal login_event_code
        login_event_code = int(error_code)
        event_loop.quit()

    def on_timeout() -> None:
        nonlocal timed_out
        timed_out = True
        event_loop.quit()

    control.OnEventConnect.connect(on_event_connect)
    timer = qt_core.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(on_timeout)
    timer.start(timeout_seconds * 1000)

    try:
        request_result = int(control.dynamicCall("CommConnect()"))
    except (TypeError, ValueError) as exc:
        return _base_report(
            status="login_request_failed",
            mode=mode,
            pyqt_version=pyqt_version,
            qt_version=qt_version,
            active_x_available=True,
            control_created=True,
            login_attempted=True,
            failure=f"CommConnect returned an invalid result: {exc}",
        )
    if request_result != 0:
        return _base_report(
            status="login_request_failed",
            mode=mode,
            pyqt_version=pyqt_version,
            qt_version=qt_version,
            active_x_available=True,
            control_created=True,
            login_attempted=True,
            failure=f"CommConnect returned {request_result}",
        )

    event_loop.exec_()
    timer.stop()
    connected = _connection_state(control)

    if timed_out:
        return _base_report(
            status="login_timeout",
            mode=mode,
            pyqt_version=pyqt_version,
            qt_version=qt_version,
            active_x_available=True,
            control_created=True,
            login_attempted=True,
            connected=connected,
            failure="Kiwoom login event was not received before the timeout",
        )
    if login_event_code != 0 or not connected:
        return _base_report(
            status="login_failed",
            mode=mode,
            pyqt_version=pyqt_version,
            qt_version=qt_version,
            active_x_available=True,
            control_created=True,
            login_attempted=True,
            login_event_code=login_event_code,
            connected=connected,
            failure=f"Kiwoom OnEventConnect returned {login_event_code}",
        )

    return _base_report(
        status="passed_login",
        mode=mode,
        pyqt_version=pyqt_version,
        qt_version=qt_version,
        active_x_available=True,
        control_created=True,
        login_attempted=True,
        login_event_code=login_event_code,
        connected=True,
        service_registration_verified=True,
        market_data_session_ready=True,
        market_data_enabled=False,
    )


def _write_report(report: BridgeProbeReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the dedicated x86 Kiwoom OpenAPI+ ActiveX bridge environment "
            "or run an interactive login probe"
        )
    )
    parser.add_argument(
        "--mode",
        choices=("environment", "login"),
        default="environment",
    )
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_probe(mode=args.mode, timeout_seconds=args.timeout_seconds)
    _write_report(report, args.output)

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
    else:
        success = report.status in SUCCESS_STATUSES
        stream = sys.stdout if success else sys.stderr
        label = "PASS" if success else "FAIL"
        print(f"KIWOOM OPENAPI+ BRIDGE: {label}", file=stream)
        print(f"status: {report.status}", file=stream)
        print(f"mode: {report.mode}", file=stream)
        print(
            f"Python: {report.python_version} ({report.python_bitness}-bit)",
            file=stream,
        )
        print(f"PyQt: {report.pyqt_version}", file=stream)
        print(f"Qt: {report.qt_version}", file=stream)
        print(f"ActiveX control created: {report.control_created}", file=stream)
        print(f"connected: {report.connected}", file=stream)
        print(
            "service registration verified: "
            f"{report.service_registration_verified}",
            file=stream,
        )
        print(
            f"market data session ready: {report.market_data_session_ready}",
            file=stream,
        )
        print(f"market data adapter enabled: {report.market_data_enabled}", file=stream)
        print("account API: disabled", file=stream)
        print("order API: disabled", file=stream)
        if report.failure:
            print(f"failure: {report.failure}", file=stream)
        print(f"readiness artifact: {args.output}", file=stream)
    return 0 if report.status in SUCCESS_STATUSES else 2


if __name__ == "__main__":
    raise SystemExit(main())
