"""Bootstrap the hardened Kiwoom exporter on minimal Windows Python installs.

Windows does not ship the IANA time-zone database used by ``zoneinfo``. The
isolated x86 bridge intentionally has very few dependencies, so this entry point
supplies fixed UTC and Korea Standard Time offsets only when those zones are
unavailable. KST has no daylight-saving transitions and is permanently UTC+09:00.

The bootstrap also applies the stdlib-only rolling request gate and immutable
artifact writer before invoking the exporter. It remains compatible with the
supported Python 3.10 x86 bridge.
"""

from __future__ import annotations

import importlib.util
import os
import runpy
import sys
import zoneinfo
from collections.abc import Callable
from datetime import timedelta, timezone, tzinfo
from pathlib import Path
from types import FrameType, ModuleType
from typing import Any, NoReturn, TextIO

ZoneFactory = Callable[[str], tzinfo]
ExitProcess = Callable[[int], NoReturn]


def _fixed_supported_zone(key: str) -> tzinfo:
    if key == "Asia/Seoul":
        return timezone(timedelta(hours=9), name="KST")
    if key == "UTC":
        return timezone.utc  # noqa: UP017 - bridge supports Python 3.10
    raise zoneinfo.ZoneInfoNotFoundError(f"No fixed fallback for time zone {key}")


def ensure_export_timezones(
    module: ModuleType = zoneinfo,
) -> bool:
    """Install a narrow fixed-offset fallback when Windows has no tzdata.

    Returns ``True`` only when the module's ``ZoneInfo`` attribute was replaced.
    Unknown zones continue through the original factory and retain its failure
    semantics.
    """

    original: ZoneFactory = module.ZoneInfo
    missing_error: type[BaseException] = module.ZoneInfoNotFoundError
    try:
        original("Asia/Seoul")
        original("UTC")
    except missing_error:

        def fallback(key: str) -> tzinfo:
            if key in {"Asia/Seoul", "UTC"}:
                return _fixed_supported_zone(key)
            return original(key)

        module.ZoneInfo = fallback
        return True
    return False


def _load_hardening(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "alpha_cycle_kiwoom_market_export_hardening",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Kiwoom export hardening module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _flush_and_hard_exit(
    code: int,
    *,
    exit_process: ExitProcess = os._exit,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> NoReturn:
    """Flush diagnostics and bypass unstable Qt/ActiveX interpreter teardown."""

    if not 0 <= code <= 255:
        raise ValueError("bridge exit code must be between 0 and 255")
    output = stdout if stdout is not None else sys.stdout
    error = stderr if stderr is not None else sys.stderr
    output.flush()
    error.flush()
    exit_process(code)


def _run_entrypoint_before_teardown(
    entrypoint: Callable[[], Any],
    *,
    exit_process: ExitProcess = os._exit,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> NoReturn:
    """Terminate on the exporter's return event before its locals are released.

    A successful export leaves the live QAxWidget in the exporter ``main`` frame.
    Returning normally first decrements that frame's local references, which can
    invoke unstable native ActiveX destruction before the bootstrap regains
    control. A Python return trace fires while the frame and its locals are still
    alive, allowing the isolated bridge to flush output and terminate before any
    Qt/ActiveX object teardown begins.

    If an unexpected exception is propagating out of the entry point, the trace
    does not convert it into a successful exit. Expected exporter failures are
    caught by the exporter itself and returned as its normal nonzero status.
    """

    target_code = getattr(entrypoint, "__code__", None)
    if target_code is None:
        raise TypeError("Kiwoom exporter entrypoint must be a Python function")
    exception_in_flight = False

    def trace(frame: FrameType, event: str, argument: Any) -> Any:
        nonlocal exception_in_flight
        if frame.f_code is not target_code:
            return trace
        if event == "exception":
            exception_in_flight = True
        elif event == "line":
            exception_in_flight = False
        elif event == "return":
            if exception_in_flight and argument is None:
                sys.settrace(None)
                return None
            sys.settrace(None)
            status = 0 if argument is None else int(argument)
            _flush_and_hard_exit(
                status,
                exit_process=exit_process,
                stdout=stdout,
                stderr=stderr,
            )
        return trace

    sys.settrace(trace)
    try:
        result = entrypoint()
    finally:
        sys.settrace(None)

    # Defensive fallback for runtimes where return tracing is unavailable. The
    # supported CPython bridge is expected to terminate from the trace callback.
    _flush_and_hard_exit(
        0 if result is None else int(result),
        exit_process=exit_process,
        stdout=stdout,
        stderr=stderr,
    )


def main(*, exit_before_teardown: bool = False) -> Any:
    ensure_export_timezones()
    directory = Path(__file__).resolve().parent
    exporter = directory / "market_export.py"
    hardening_path = directory / "market_export_hardening.py"
    if not exporter.is_file():
        raise FileNotFoundError("Kiwoom market exporter is missing")
    if not hardening_path.is_file():
        raise FileNotFoundError("Kiwoom market exporter hardening is missing")

    namespace = runpy.run_path(
        str(exporter),
        run_name="alpha_cycle_kiwoom_market_export",
    )
    entrypoint = namespace.get("main")
    if not callable(entrypoint):
        raise RuntimeError("Kiwoom market exporter has no callable main")
    runtime_globals = entrypoint.__globals__
    hardening = _load_hardening(hardening_path)
    hardening.apply_hardening(runtime_globals)
    sys.argv[0] = str(exporter)
    if exit_before_teardown:
        return _run_entrypoint_before_teardown(entrypoint)
    return entrypoint()


if __name__ == "__main__":
    main(exit_before_teardown=True)
