from __future__ import annotations

import json
from pathlib import Path

from alpha_cycle.intelligence.decision_industry_evidence_calibrated import (
    _kosis_capture_date_in_korea,
)


def test_kosis_capture_date_uses_korea_calendar_day(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    manifest = artifact / "manifest.json"
    manifest.write_text(
        json.dumps({"captured_at": "2026-08-09T16:30:00+00:00"}),
        encoding="utf-8",
    )
    pointer = tmp_path / "latest.json"
    pointer.write_text(
        json.dumps({"manifest_path": str(manifest.resolve())}),
        encoding="utf-8",
    )

    capture_date = _kosis_capture_date_in_korea(pointer)

    assert capture_date.isoformat() == "2026-08-10"
