"""Alpha Cycle Lab deterministic backtesting package."""

from __future__ import annotations

import os

__version__ = "0.1.0"


def _apply_environment_compatibility() -> None:
    """Map the established BOK key name to the provider's process-local alias."""

    if not os.environ.get("ECOS_API_KEY", "").strip():
        bok_key = os.environ.get("BOK_ECOS_API_KEY", "").strip()
        if bok_key:
            os.environ["ECOS_API_KEY"] = bok_key


_apply_environment_compatibility()
