from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from alpha_cycle.intelligence.decision_guardrails_v2_1 import (
    load_decision_system_v21_guardrails,
)
from alpha_cycle.intelligence.payoff_surface import (
    PayoffScenario,
    PayoffSurfaceSnapshot,
    ScenarioLabel,
    persist_payoff_surface,
)
from alpha_cycle.research_component_repository_v2_1 import (
    build_research_component_repository_index,
)

NOW = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
GUARDRAIL = load_decision_system_v21_guardrails().evidence_id


def _scenario(label: ScenarioLabel, lower: float, upper: float) -> PayoffScenario:
    return PayoffScenario(
        scenario_id=f"{label.value}-relative-pointer",
        label=label,
        horizon_trading_days=120,
        trigger_conditions=("fixture trigger",),
        fundamental_assumptions=("fixture assumption",),
        catalyst_refs=("fixture:catalyst",),
        source_evidence_ids=("a" * 64,),
        return_lower=lower,
        return_upper=upper,
        thesis_break_conditions=("fixture break",),
    )


def test_relative_pointer_is_resolved_independently_of_reader_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    writer_cwd = tmp_path / "writer"
    writer_cwd.mkdir()
    relative_artifact_root = Path("artifacts")
    payoff_root = relative_artifact_root / "payoff_surface"
    snapshot = PayoffSurfaceSnapshot(
        captured_at=NOW,
        thesis_snapshot_id="b" * 64,
        security_id="000660",
        horizon_trading_days=120,
        scenarios=(
            _scenario(ScenarioLabel.BEAR, -0.30, -0.10),
            _scenario(ScenarioLabel.BASE, 0.10, 0.30),
            _scenario(ScenarioLabel.BULL, 0.35, 0.60),
        ),
        source_snapshot_ids=("c" * 64,),
        guardrail_evidence_id=GUARDRAIL,
    )

    monkeypatch.chdir(writer_cwd)
    persist_payoff_surface(snapshot, output_root=payoff_root)
    absolute_artifact_root = (writer_cwd / relative_artifact_root).resolve()

    reader_cwd = tmp_path / "reader"
    reader_cwd.mkdir()
    monkeypatch.chdir(reader_cwd)
    index = build_research_component_repository_index(
        absolute_artifact_root,
        as_of=NOW,
    )

    selected = index.latest_payoff(
        "000660",
        thesis_snapshot_id=snapshot.thesis_snapshot_id,
        horizon_trading_days=120,
        guardrail_evidence_id=GUARDRAIL,
    )
    assert selected is not None
    assert selected.snapshot_id == snapshot.snapshot_id
