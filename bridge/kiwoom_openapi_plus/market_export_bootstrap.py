"""Bootstrap the Kiwoom market exporter on minimal Windows Python installs.

Windows does not ship the IANA time-zone database used by ``zoneinfo``. The
isolated x86 bridge intentionally has very few dependencies, so this entry point
supplies fixed UTC and Korea Standard Time offsets only when those zones are
unavailable. KST has no daylight-saving transitions and is permanently UTC+09:00.
"""

from __future__ import annotations

import runpy
import sys
import zoneinfo
from collections.abc import Callable
from datetime import UTC, timedelta, timezone, tzinfo
from pathlib import Path
from types import ModuleType
from typing import Any

ZoneFactory = Callable[[str], tzinfo]


def _fixed_supported_zone(key: str) -> tzinfo:
    if key == "Asia/Seoul":
        return timezone(timedelta(hours=9), name="KST")
    if key == "UTC":
        return UTC
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


def main() -> Any:
    ensure_export_timezones()
    exporter = Path(__file__).with_name("market_export.py")
    if not exporter.is_file():
        raise FileNotFoundError("Kiwoom market exporter is missing")
    sys.argv[0] = str(exporter)
    return runpy.run_path(str(exporter), run_name="__main__")


if __name__ == "__main__":
    main()
