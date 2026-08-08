"""Bootstrap the Kiwoom investor-flow probe on minimal Windows x86 Python.

The isolated bridge may not have the optional ``tzdata`` package installed.
Install the same narrow Asia/Seoul/UTC fixed-offset fallback used by the market
exporter before importing ``investor_flow_export.py``, which imports
``market_export.py`` and constructs its KST timezone at module import time.
"""

from __future__ import annotations

import runpy
from pathlib import Path

from market_export_bootstrap import ensure_export_timezones

EXPORTER_PATH = Path(__file__).with_name("investor_flow_export.py")


def main() -> None:
    """Prepare timezone support, then execute the read-only investor-flow probe."""

    ensure_export_timezones()
    runpy.run_path(str(EXPORTER_PATH), run_name="__main__")


if __name__ == "__main__":
    main()
