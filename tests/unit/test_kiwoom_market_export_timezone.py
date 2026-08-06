"""Tests for Windows-safe Kiwoom market-export time zones."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import NoReturn

import pytest

BOOTSTRAP_PATH = Path(
    "bridge/kiwoom_openapi_plus/market_export_bootstrap.py"
)


def _load_bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "kiwoom_market_export_bootstrap_test",
        BOOTSTRAP_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_missing_windows_tzdata_uses_narrow_fixed_offsets() -> None:
    bootstrap = _load_bootstrap()
    fake = ModuleType("fake_zoneinfo")

    class MissingZoneError(Exception):
        pass

    def missing_factory(key: str) -> timezone:
        raise MissingZoneError(key)

    fake.ZoneInfo = missing_factory
    fake.ZoneInfoNotFoundError = MissingZoneError

    replaced = bootstrap.ensure_export_timezones(fake)

    assert replaced is True
    kst = fake.ZoneInfo("Asia/Seoul")
    utc = fake.ZoneInfo("UTC")
    assert datetime(2026, 8, 4, tzinfo=kst).utcoffset() == timedelta(hours=9)
    assert datetime(2026, 8, 4, tzinfo=kst).tzname() == "KST"
    assert datetime(2026, 8, 4, tzinfo=utc).utcoffset() == timedelta(0)
    with pytest.raises(MissingZoneError):
        fake.ZoneInfo("America/New_York")


def test_available_zoneinfo_is_not_replaced() -> None:
    bootstrap = _load_bootstrap()
    fake = ModuleType("available_zoneinfo")

    class MissingZoneError(Exception):
        pass

    def available_factory(_key: str) -> timezone:
        return UTC

    fake.ZoneInfo = available_factory
    fake.ZoneInfoNotFoundError = MissingZoneError

    replaced = bootstrap.ensure_export_timezones(fake)

    assert replaced is False
    assert fake.ZoneInfo is available_factory


def test_fixed_fallback_is_limited_to_kst_and_utc() -> None:
    bootstrap = _load_bootstrap()

    kst = bootstrap._fixed_supported_zone("Asia/Seoul")
    utc = bootstrap._fixed_supported_zone("UTC")

    assert datetime(2026, 1, 1, tzinfo=kst).utcoffset() == timedelta(hours=9)
    assert datetime(2026, 7, 1, tzinfo=kst).utcoffset() == timedelta(hours=9)
    assert utc is UTC
    with pytest.raises(bootstrap.zoneinfo.ZoneInfoNotFoundError):
        bootstrap._fixed_supported_zone("Europe/London")


def test_windows_launcher_uses_timezone_bootstrap() -> None:
    script = Path("scripts/export_kiwoom_openapi_plus_market.ps1").read_text(
        encoding="utf-8"
    )
    bootstrap = BOOTSTRAP_PATH.read_text(encoding="utf-8")

    assert "market_export_bootstrap.py" in script
    assert "market_export.py" in bootstrap
    assert "Asia/Seoul" in bootstrap
    assert "timedelta(hours=9)" in bootstrap
    assert "tzdata" not in script


def test_hard_exit_flushes_output_and_preserves_exporter_status() -> None:
    bootstrap = _load_bootstrap()
    events: list[tuple[str, int | None]] = []

    class Stream:
        def __init__(self, name: str) -> None:
            self.name = name

        def flush(self) -> None:
            events.append((self.name, None))

    def exit_process(code: int) -> NoReturn:
        events.append(("exit", code))
        raise SystemExit(code)

    with pytest.raises(SystemExit) as captured:
        bootstrap._flush_and_hard_exit(
            2,
            exit_process=exit_process,
            stdout=Stream("stdout"),
            stderr=Stream("stderr"),
        )

    assert captured.value.code == 2
    assert events == [("stdout", None), ("stderr", None), ("exit", 2)]


def test_hard_exit_rejects_invalid_process_status() -> None:
    bootstrap = _load_bootstrap()

    with pytest.raises(ValueError, match="between 0 and 255"):
        bootstrap._flush_and_hard_exit(256)
