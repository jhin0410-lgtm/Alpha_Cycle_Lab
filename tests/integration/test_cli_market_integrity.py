from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from alpha_cycle.reporting.writer import CORPORATE_ACTION_COLUMNS

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def test_cli_writes_empty_corporate_action_audit_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "market-integrity-output"
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(SRC_ROOT)
        if not existing_pythonpath
        else f"{SRC_ROOT}{os.pathsep}{existing_pythonpath}"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alpha_cycle.cli",
            "backtest",
            "--input",
            str(REPO_ROOT / "data" / "sample" / "prices.csv"),
            "--strategy",
            "momentum",
            "--initial-cash",
            "80000000",
            "--config",
            str(REPO_ROOT / "config" / "example.yaml"),
            "--output",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "8 output files" in result.stdout
    action_path = output_dir / "corporate_actions.csv"
    assert action_path.exists()
    frame = pd.read_csv(action_path)
    assert frame.empty
    assert frame.columns.tolist() == CORPORATE_ACTION_COLUMNS
