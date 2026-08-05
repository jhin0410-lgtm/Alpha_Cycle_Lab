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
import runpy
import sys
import zoneinfo
from collections.abc import Callable
from datetime import timedelta, timezone, tzinfo
from pathlib import Path
from types import ModuleType
from typing import Any

ZoneFactory = Callable[[str], tzinfo]


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


def main() -> Any:
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
    return entrypoint()


if __name__ == "__main__":
    raise SystemExit(main())
