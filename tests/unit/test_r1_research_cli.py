from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from test_persisted_research_plan_v1 import model
from test_valuation_authority_v2_1 import _raw_opendart, _research

from alpha_cycle.intelligence.fundamental_macro import write_fundamental_macro_snapshot
from alpha_cycle.intelligence.observable_universe import load_current_universe_state
from alpha_cycle.r1_research_cli import main

FIELD = "000660|memory_semiconductor|reported_profit|CIS:ifrs-full_ProfitLoss#29|2025-12-31|FY"


def source(root: Path, delta: int = 0) -> Path:
    fixture = _research("a" * 64)
    frame = fixture.financials.copy()
    frame.loc[frame["metric"].eq("CIS:ifrs-full_ProfitLoss#29"), "value"] += delta
    fixture = replace(fixture, financials=frame, raw_opendart=_raw_opendart(frame))
    return write_fundamental_macro_snapshot(root, fixture)[0].parent


def args(path: Path, store: Path) -> list[str]:
    return [
        "--research-source", str(path), "--store", str(store),
        "--universe-id", "reported", "--version", "1", "--field", FIELD,
    ]


def test_baseline_unchanged_then_changed_builds_partial_research(tmp_path, capsys):
    original = source(tmp_path / "source")
    store = tmp_path / "universe"
    assert main(args(original, store)) == 0
    baseline = json.loads(capsys.readouterr().out)
    assert baseline["status"] == "baseline_recorded"
    assert baseline["rounds"] == []
    assert main(args(original, store)) == 0
    unchanged = json.loads(capsys.readouterr().out)
    assert unchanged["rounds"] == []
    changed = source(tmp_path / "changed", 100)
    assert main(args(changed, store)) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["rounds"]) == 1
    assert result["rounds"][0]["plan"]
    assert result["rounds"][0]["research"]
    assert "forecast_not_registered" in result["rounds"][0]["unavailable"]
    assert not result["provider_origin_authenticated"]
    assert not result["independent_authority_established"]
    assert not result["product_r1_accepted"]


def test_failed_new_attempt_hides_old_success_and_new_valid_source_recovers(tmp_path, capsys):
    original = source(tmp_path / "source")
    store = tmp_path / "universe"
    assert main(args(original, store)) == 0
    capsys.readouterr()
    assert main(args(tmp_path / "missing", store)) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "failed"
    assert not load_current_universe_state(store).ready
    assert main(args(original, store)) == 0
    recovery = json.loads(capsys.readouterr().out)
    assert recovery["status"] == "baseline_recorded"
    assert recovery["rounds"] == []
    assert load_current_universe_state(store).ready


def test_pack_driver_reads_stored_source_and_preserves_partial_state(tmp_path, capsys):
    original = source(tmp_path / "source")
    store = tmp_path / "universe"
    pack = model()
    pack = replace(
        pack,
        drivers=(replace(pack.drivers[0], driver_id="reported_profit"),), content_id="",
    )
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(pack.payload()), encoding="utf-8")
    assert main(args(original, store) + ["--pack", str(pack_path)]) == 0
    capsys.readouterr()
    assert main(args(source(tmp_path / "changed", 100), store) + [
        "--pack", str(pack_path),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    plan = result["rounds"][0]["plan"]
    assert plan["resolutions"][0]["status"] == "usable"
    assert plan["resolutions"][0]["maturity"] == "replayable_provider_evidence"
    assert not result["product_r1_accepted"]
