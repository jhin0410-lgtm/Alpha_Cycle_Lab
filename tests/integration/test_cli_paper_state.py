from __future__ import annotations

import json

from alpha_cycle.cli import main


def test_cli_initializes_verifies_and_exports_empty_paper_state(tmp_path, capsys) -> None:
    database = tmp_path / "paper.sqlite"
    output = tmp_path / "audit"

    assert (
        main(
            [
                "paper-state",
                "init",
                "--database",
                str(database),
                "--run-id",
                "cli-run",
                "--strategy",
                "momentum",
                "--initial-cash",
                "80000000",
                "--config-digest",
                "config-sha256",
            ]
        )
        == 0
    )
    assert database.is_file()

    assert main(["paper-state", "verify", "--database", str(database)]) == 0
    verify_output = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(verify_output)
    assert payload["ok"] is True
    assert payload["sessions"] == 0

    assert (
        main(
            [
                "paper-state",
                "export",
                "--database",
                str(database),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert {path.name for path in output.iterdir()} == {
        "paper_sessions.csv",
        "paper_orders.csv",
        "paper_fills.csv",
        "paper_checkpoints.csv",
        "paper_positions.csv",
        "paper_metadata.json",
    }


def test_cli_rejects_missing_paper_database(tmp_path, capsys) -> None:
    code = main(
        [
            "paper-state",
            "verify",
            "--database",
            str(tmp_path / "missing.sqlite"),
        ]
    )
    assert code == 2
    assert "does not exist" in capsys.readouterr().err
