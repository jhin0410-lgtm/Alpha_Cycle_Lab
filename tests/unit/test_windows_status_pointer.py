"""Windows-safe latest-run pointer serialization tests."""

from __future__ import annotations

import json
from pathlib import Path

from alpha_cycle.live_pipeline_provenance_cli import _rewrite_status_ascii_safe


def test_latest_run_pointer_is_ascii_and_round_trips_korean_path(tmp_path: Path) -> None:
    destination = tmp_path / "latest_run.json"
    payload = {
        "status": "completed",
        "decision_directory": r"C:\Download\쿠쿠\coding\Alpha_Cycle_Lab\data",
    }

    _rewrite_status_ascii_safe(destination, payload)

    raw = destination.read_bytes()
    raw.decode("ascii")
    text = raw.decode("ascii")
    assert "쿠쿠" not in text
    assert "\\u" in text
    assert json.loads(text) == payload
    assert not (tmp_path / ".latest_run.json.ascii.tmp").exists()
