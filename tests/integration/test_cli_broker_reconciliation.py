"""CLI integration tests for read-only broker reconciliation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.cli import main


def _initialize(database: Path) -> None:
    exit_code = main(
        [
            "paper-state",
            "init",
            "--database",
            str(database),
            "--run-id",
            "test-run",
            "--strategy",
            "momentum",
            "--initial-cash",
            "80000000",
            "--config-digest",
            "c" * 64,
        ]
    )
    assert exit_code == 0


def _snapshot(path: Path, *, cash: str = "80000000") -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "broker": "synthetic-read-only",
                "account_ref_hash": "a" * 64,
                "snapshot_id": "snapshot-001",
                "captured_at": datetime.now(UTC).isoformat(),
                "cash": cash,
                "positions": [],
                "open_orders": [],
                "fills": [],
                "fill_history_complete": True,
            }
        ),
        encoding="utf-8",
    )


def test_cli_reconciliation_ready_writes_two_outputs(tmp_path, capsys) -> None:
    database = tmp_path / "paper.sqlite"
    snapshot = tmp_path / "broker.json"
    output = tmp_path / "reconciliation"
    _initialize(database)
    _snapshot(snapshot)

    exit_code = main(
        [
            "broker-reconcile",
            "--database",
            str(database),
            "--snapshot",
            str(snapshot),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    payload = json.loads((output / "reconciliation_report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["can_submit_orders"] is True
    assert (output / "reconciliation_issues.csv").is_file()
    assert '"status": "ready"' in capsys.readouterr().out


def test_cli_reconciliation_blocked_returns_two_after_writing(tmp_path, capsys) -> None:
    database = tmp_path / "paper.sqlite"
    snapshot = tmp_path / "broker.json"
    output = tmp_path / "reconciliation"
    _initialize(database)
    _snapshot(snapshot, cash="79999999")

    exit_code = main(
        [
            "broker-reconcile",
            "--database",
            str(database),
            "--snapshot",
            str(snapshot),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 2
    payload = json.loads((output / "reconciliation_report.json").read_text(encoding="utf-8"))
    assert payload["status"] == "blocked"
    assert payload["blocking_count"] == 1
    assert "did not authorize order submission" in capsys.readouterr().err
