from __future__ import annotations

from pathlib import Path

import pytest

from alpha_cycle.kis_forward_estimate_revision_cli import main


def test_revision_cli_blocks_before_reading_legacy_forward_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_root = tmp_path / "changes"

    exit_code = main(
        [
            "--forward-root",
            str(tmp_path / "missing-forward"),
            "--output",
            str(output_root),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "KIS forward numeric evidence is blocked" in captured.err
    assert "Forward estimate root does not exist" not in captured.err
    assert not output_root.exists()
