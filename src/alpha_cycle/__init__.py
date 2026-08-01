"""Alpha Cycle Lab deterministic backtesting package."""

from __future__ import annotations

import os
from collections.abc import Callable, MutableMapping
from contextlib import AbstractContextManager
from importlib import import_module
from typing import Protocol, cast

__version__ = "0.1.0"

_USER_ENVIRONMENT_NAMES = (
    "TOSSINVEST_CLIENT_ID",
    "TOSSINVEST_CLIENT_SECRET",
    "OPENDART_API_KEY",
    "BOK_ECOS_API_KEY",
    "ECOS_API_KEY",
)


class _WinRegModule(Protocol):
    HKEY_CURRENT_USER: object

    def OpenKey(self, key: object, sub_key: str) -> AbstractContextManager[object]: ...

    def QueryValueEx(self, key: object, value_name: str) -> tuple[object, int]: ...


def _windows_user_environment_value(name: str) -> str | None:
    """Read one Windows user-scoped environment value without printing it."""

    if os.name != "nt":
        return None
    try:
        winreg = cast(_WinRegModule, import_module("winreg"))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except (FileNotFoundError, OSError):
        return None
    text = str(value).strip()
    return text or None


def _apply_environment_compatibility(
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Map the established BOK key name to the provider's process-local alias."""

    values = os.environ if environ is None else environ
    if not values.get("ECOS_API_KEY", "").strip():
        bok_key = values.get("BOK_ECOS_API_KEY", "").strip()
        if bok_key:
            values["ECOS_API_KEY"] = bok_key


def _hydrate_windows_user_environment(
    environ: MutableMapping[str, str] | None = None,
    *,
    reader: Callable[[str], str | None] | None = None,
) -> None:
    """Restore saved Windows user credentials into the current Python process.

    Windows does not retroactively update already-open shells after user-level
    environment variables are changed. Direct ``python -m`` runs therefore read the
    current user's registry-backed environment only when a process value is missing.
    Existing process values always win.
    """

    values = os.environ if environ is None else environ
    lookup = _windows_user_environment_value if reader is None else reader
    for name in _USER_ENVIRONMENT_NAMES:
        if values.get(name, "").strip():
            continue
        saved = lookup(name)
        if saved is not None and saved.strip():
            values[name] = saved.strip()
    _apply_environment_compatibility(values)


_hydrate_windows_user_environment()
