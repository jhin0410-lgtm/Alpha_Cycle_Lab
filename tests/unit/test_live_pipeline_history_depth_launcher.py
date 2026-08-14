from __future__ import annotations

from pathlib import Path


def test_supported_live_launcher_defaults_to_five_year_history() -> None:
    script = Path("scripts/run_live_pipeline.cmd").read_text(encoding="utf-8")
    command_line = next(
        line for line in script.splitlines() if "run_live_pipeline_bootstrap.ps1" in line
    )

    assert "--history-years 5" in command_line
    assert command_line.index("--history-years 5") < command_line.index("%*")
