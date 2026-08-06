"""Bootstrap the hardened Kiwoom exporter on minimal Windows Python installs.

The isolated x86 bridge exports public quote and daily-bar evidence only. It
supplies fixed time-zone fallbacks, applies the stdlib-only hardening layer, and
terminates the successful Windows process without running unstable ActiveX DLL
process-detach handlers.
"""

from __future__ import annotations

import importlib.util
import json
import os
import runpy
import sys
import zoneinfo
from collections.abc import Callable
from dataclasses import asdict
from datetime import timedelta, timezone, tzinfo
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, TextIO

ZoneFactory = Callable[[str], tzinfo]
ExitProcess = Callable[[int], NoReturn]


def _fixed_supported_zone(key: str) -> tzinfo:
    if key == "Asia/Seoul":
        return timezone(timedelta(hours=9), name="KST")
    if key == "UTC":
        return timezone.utc  # noqa: UP017 - bridge supports Python 3.10
    raise zoneinfo.ZoneInfoNotFoundError(f"No fixed fallback for time zone {key}")


def ensure_export_timezones(module: ModuleType = zoneinfo) -> bool:
    """Install a narrow fixed-offset fallback when Windows has no tzdata."""

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


def _terminate_with_kernel32(
    code: int,
    *,
    kernel32: Any,
    get_last_error: Callable[[], int],
) -> NoReturn:
    """Terminate the current process without DLL_PROCESS_DETACH callbacks."""

    if not 0 <= code <= 255:
        raise ValueError("bridge exit code must be between 0 and 255")

    import ctypes

    get_current_process = kernel32.GetCurrentProcess
    terminate_process = kernel32.TerminateProcess
    get_current_process.argtypes = []
    get_current_process.restype = ctypes.c_void_p
    terminate_process.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    terminate_process.restype = ctypes.c_int

    process_handle = get_current_process()
    result = terminate_process(process_handle, code)
    if not result:
        error_code = int(get_last_error())
        raise OSError(error_code, "TerminateProcess failed")
    raise RuntimeError("TerminateProcess unexpectedly returned for current process")


def _terminate_current_process(code: int) -> NoReturn:
    """Invoke Kernel32 TerminateProcess for the current Windows bridge process."""

    if os.name != "nt":
        raise RuntimeError("Kiwoom bridge termination requires Windows")

    import ctypes

    loader = getattr(ctypes, "WinDLL", None)
    get_last_error = getattr(ctypes, "get_last_error", None)
    if loader is None or not callable(get_last_error):
        raise RuntimeError("Windows process-termination APIs are unavailable")
    kernel32 = loader("kernel32", use_last_error=True)
    _terminate_with_kernel32(
        code,
        kernel32=kernel32,
        get_last_error=get_last_error,
    )


def _flush_and_hard_exit(
    code: int,
    *,
    exit_process: ExitProcess = _terminate_current_process,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> NoReturn:
    """Flush diagnostics, then bypass Python and ActiveX DLL teardown."""

    if not 0 <= code <= 255:
        raise ValueError("bridge exit code must be between 0 and 255")
    output = stdout if stdout is not None else sys.stdout
    error = stderr if stderr is not None else sys.stderr
    output.flush()
    error.flush()
    exit_process(code)


def _print_export_success(
    manifest: Any,
    export_directory: Any,
    *,
    json_output: bool,
    stdout: TextIO,
) -> None:
    """Render the exporter's success contract before native objects can unwind."""

    if json_output:
        print(
            json.dumps(
                asdict(manifest),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=stdout,
        )
        return
    print("KIWOOM OPENAPI+ MARKET EXPORT: PASS", file=stdout)
    print(f"snapshot: {manifest.snapshot_id}", file=stdout)
    print(f"symbols: {', '.join(manifest.symbols)}", file=stdout)
    print(f"quotes: {manifest.quote_count}", file=stdout)
    print(f"daily bars: {manifest.daily_bar_count}", file=stdout)
    print(f"adjusted prices: {manifest.adjusted_prices}", file=stdout)
    print(f"requests: {manifest.request_count}", file=stdout)
    print("account API: disabled", file=stdout)
    print("order API: disabled", file=stdout)
    print(f"export directory: {export_directory}", file=stdout)


def _install_success_exit(
    runtime_globals: dict[str, Any],
    *,
    exit_process: ExitProcess = _terminate_current_process,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Exit from inside ``write_export`` while the caller still owns QAxWidget."""

    original = runtime_globals.get("write_export")
    if not callable(original):
        raise RuntimeError("Kiwoom exporter has no callable write_export")
    output = stdout if stdout is not None else sys.stdout
    error = stderr if stderr is not None else sys.stderr
    json_output = "--json" in sys.argv[1:]

    def write_export_and_exit(*args: Any, **kwargs: Any) -> NoReturn:
        manifest, export_directory = original(*args, **kwargs)
        _print_export_success(
            manifest,
            export_directory,
            json_output=json_output,
            stdout=output,
        )
        _flush_and_hard_exit(
            0,
            exit_process=exit_process,
            stdout=output,
            stderr=error,
        )

    runtime_globals["write_export"] = write_export_and_exit


def _run_entrypoint_with_success_exit(
    entrypoint: Callable[[], Any],
    runtime_globals: dict[str, Any],
    *,
    exit_process: ExitProcess = _terminate_current_process,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> NoReturn:
    """Run the exporter and terminate before success-path ActiveX destruction."""

    _install_success_exit(
        runtime_globals,
        exit_process=exit_process,
        stdout=stdout,
        stderr=stderr,
    )
    result = entrypoint()
    _flush_and_hard_exit(
        0 if result is None else int(result),
        exit_process=exit_process,
        stdout=stdout,
        stderr=stderr,
    )


def main(
    *,
    exit_before_teardown: bool = False,
    exit_process: ExitProcess = _terminate_current_process,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> Any:
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
        return _run_entrypoint_with_success_exit(
            entrypoint,
            runtime_globals,
            exit_process=exit_process,
            stdout=stdout,
            stderr=stderr,
        )
    return entrypoint()


if __name__ == "__main__":
    main(exit_before_teardown=True)
