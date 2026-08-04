"""Report Python runtime identity and verify the Alpha Cycle Lab environment."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


def runtime_identity() -> dict[str, object]:
    """Return machine-readable runtime identity without third-party imports."""
    return {
        "schema_version": "1.0",
        "bitness": struct.calcsize("P") * 8,
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
        "micro": sys.version_info.micro,
        "executable": sys.executable,
    }


def verify_project_environment() -> None:
    """Fail unless the main analysis environment is complete and 64-bit."""
    import alpha_cycle
    import numpy
    import pandas
    import yaml

    identity = runtime_identity()
    if identity["bitness"] != 64:
        raise RuntimeError("Alpha Cycle Lab requires 64-bit Python")
    if (int(identity["major"]), int(identity["minor"])) < (3, 12):
        raise RuntimeError("Alpha Cycle Lab requires Python 3.12+")
    if datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Seoul")).utcoffset() is None:
        raise RuntimeError("Asia/Seoul timezone data is unavailable")

    print("PROJECT PYTHON: PASS")
    print(f"Python bitness: {identity['bitness']}")
    print(f"NumPy: {numpy.__version__}")
    print(f"pandas: {pandas.__version__}")
    print(f"PyYAML: {yaml.__version__}")
    print(f"Python executable: {identity['executable']}")
    _ = alpha_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-project", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verify_project:
        verify_project_environment()
    else:
        print(json.dumps(runtime_identity(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
