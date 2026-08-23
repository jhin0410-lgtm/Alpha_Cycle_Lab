from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import alpha_cycle.research_package_assembler_v2_1 as assembler

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)


def _fake_opportunity_persist(object_name: str):
    def persist(snapshot: object, *, output_root: str | Path) -> Path:
        root = Path(output_root)
        snapshot_id = str(getattr(snapshot, "snapshot_id"))
        captured_at = getattr(snapshot, "captured_at")
        directory = assembler._opportunity_snapshot_directory(
            root,
            object_name=object_name,
            captured_at=captured_at,
            snapshot_id=snapshot_id,
        )
        directory.mkdir(parents=True)
        (directory / f"{object_name}.json").write_text("{}\n", encoding="utf-8")
        pointer = root / object_name / f"latest_{object_name}.json"
        pointer.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "object_type": object_name,
                    "snapshot_id": snapshot_id,
                    "snapshot_path": str(directory),
                }
            ),
            encoding="utf-8",
        )
        return pointer

    return persist


def test_ledger_publish_failure_rolls_back_all_new_downstream_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = SimpleNamespace(snapshot_id="a" * 64, captured_at=NOW)
    opportunity_set = SimpleNamespace(snapshot_id="b" * 64, captured_at=NOW)
    artifacts = SimpleNamespace(
        opportunity_candidates=(candidate,),
        opportunity_set=opportunity_set,
        snapshot=object(),
    )
    round_path = tmp_path / "research_round_v2_1" / "round.json"
    run_path = tmp_path / "research_round_run_v2_1" / "run.json"

    monkeypatch.setattr(
        assembler,
        "persist_opportunity_candidate",
        _fake_opportunity_persist("opportunity_candidate"),
    )
    monkeypatch.setattr(
        assembler,
        "persist_opportunity_set",
        _fake_opportunity_persist("opportunity_set"),
    )

    def persist_round(snapshot: object, *, output_root: str | Path) -> Path:
        del snapshot, output_root
        round_path.parent.mkdir(parents=True)
        round_path.write_text("{}\n", encoding="utf-8")
        return round_path

    def persist_run(run: object, *, output_root: str | Path) -> Path:
        del run, output_root
        run_path.parent.mkdir(parents=True)
        run_path.write_text("{}\n", encoding="utf-8")
        return run_path

    def fail_ledger(ledger: object, *, output_root: str | Path) -> Path:
        del ledger, output_root
        raise RuntimeError("injected ledger publication failure")

    monkeypatch.setattr(assembler, "persist_research_round", persist_round)
    monkeypatch.setattr(assembler, "persist_research_run", persist_run)
    monkeypatch.setattr(assembler, "persist_research_run_ledger", fail_ledger)

    with pytest.raises(RuntimeError, match="injected ledger publication failure"):
        assembler._publish_orchestrated_artifacts(
            artifacts=artifacts,
            run=object(),
            ledger=object(),
            root=tmp_path,
        )

    assert not round_path.exists()
    assert not run_path.exists()
    assert not (tmp_path / "opportunity_candidate").exists()
    assert not (tmp_path / "opportunity_set").exists()
