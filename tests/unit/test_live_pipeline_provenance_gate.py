"""Tests for exact-snapshot live and resume decision provenance gating."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from alpha_cycle import market_consistency_cli as core
from alpha_cycle import pipeline_decision_provenance as runtime_module
from alpha_cycle import pipeline_market_consistency as gate_module
from alpha_cycle.intelligence.decision import InvestmentDecisionSnapshot
from alpha_cycle.pipeline_decision_provenance import (
    PipelineDecisionProvenanceRuntime,
)

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_explicit_gate_evidence_pins_the_supplied_toss_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "live-research"
    market_directory = output_root / "market-intelligence" / "exact-snapshot"
    kiwoom_directory = output_root / "kiwoom-openapi-plus-market" / "snapshot"
    market_directory.mkdir(parents=True)
    kiwoom_directory.mkdir(parents=True)
    (market_directory / "prices.csv").write_text("symbol\n005930\n", encoding="utf-8")
    (kiwoom_directory / "quotes.csv").write_text("ticker\n005930\n", encoding="utf-8")
    validated: list[tuple[Path, str, str]] = []

    monkeypatch.setattr(
        core,
        "_resolve_kiwoom_directory",
        lambda root: kiwoom_directory if root == output_root else Path("wrong"),
    )
    monkeypatch.setattr(
        gate_module.raw_integrity,
        "_validate_unique_rows",
        lambda path, *, symbol_field, provider: validated.append(
            (path, symbol_field, provider)
        ),
    )

    evidence = gate_module._explicit_evidence(
        output_root=output_root,
        market_directory=market_directory,
    )

    assert evidence.toss_directory == market_directory.resolve()
    assert evidence.toss_resolution_source == "explicit_pipeline_market_directory"
    assert evidence.kiwoom_directory == kiwoom_directory.resolve()
    assert validated == [
        (market_directory / "prices.csv", "symbol", "TossInvest"),
        (kiwoom_directory / "quotes.csv", "ticker", "Kiwoom"),
    ]


def test_runtime_runs_gate_before_original_decision_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "live-research"
    market_directory = output_root / "market-intelligence" / "exact-snapshot"
    research_directory = output_root / "research-intelligence" / "snapshot"
    market_directory.mkdir(parents=True)
    research_directory.mkdir(parents=True)
    calls: list[str] = []
    fake_gate = SimpleNamespace(provenance=SimpleNamespace())

    def fake_run_gate(**kwargs: object) -> object:
        calls.append("gate")
        assert kwargs["output_root"] == output_root.resolve()
        assert kwargs["market_directory"] == market_directory.resolve()
        assert kwargs["decision_symbols"] == ("005930", "000660")
        return fake_gate

    sentinel = object()

    def fake_builder(*_args: object, **_kwargs: object) -> object:
        calls.append("builder")
        return sentinel

    monkeypatch.setattr(
        runtime_module,
        "run_pipeline_market_consistency_gate",
        fake_run_gate,
    )
    runtime = PipelineDecisionProvenanceRuntime(("005930", "000660"))

    result = runtime.build(
        cast(Any, fake_builder),
        research_directory,
        market_directory,
    )

    assert result is sentinel
    assert runtime.gate is fake_gate
    assert calls == ["gate", "builder"]


def test_runtime_refuses_decision_write_without_completed_gate(tmp_path: Path) -> None:
    runtime = PipelineDecisionProvenanceRuntime(("005930", "000660"))
    snapshot = cast(InvestmentDecisionSnapshot, object())

    with pytest.raises(ValueError, match="gate did not run"):
        runtime.write(cast(Any, lambda *_args: (tmp_path / "manifest.json",)), tmp_path, snapshot)


def test_installed_and_windows_entrypoints_use_provenance_wrappers() -> None:
    pyproject = _read("pyproject.toml")
    powershell = _read("scripts/run_live_pipeline.ps1")

    assert (
        'alpha-cycle-live = "alpha_cycle.live_pipeline_provenance_cli:main"'
        in pyproject
    )
    assert (
        'alpha-cycle-resume = "alpha_cycle.resume_pipeline_provenance_cli:main"'
        in pyproject
    )
    assert "-m alpha_cycle.live_pipeline_provenance_cli" in powershell
    assert "-m alpha_cycle.resume_pipeline_provenance_cli" in powershell
    assert "-m alpha_cycle.live_pipeline_cli @PipelineArguments" not in powershell
    assert "-m alpha_cycle.resume_pipeline_cli @ResumeArguments" not in powershell


def test_live_and_resume_wrappers_preserve_stage_and_restore_contracts() -> None:
    live_wrapper = _read("src/alpha_cycle/live_pipeline_provenance_cli.py")
    resume_wrapper = _read("src/alpha_cycle/resume_pipeline_provenance_cli.py")

    for wrapper in (live_wrapper, resume_wrapper):
        assert 'PipelineStageError("market_consistency", exc)' in wrapper
        assert 'PipelineStageError("decision_provenance", exc)' in wrapper
        assert "runtime.status_payload()" in wrapper
        assert "finally:" in wrapper
        assert "setattr" in wrapper


def test_gate_defaults_remain_strict_and_non_substituting() -> None:
    source = _read("src/alpha_cycle/pipeline_market_consistency.py")

    assert "DEFAULT_REQUIRED_DAYS = 20" in source
    assert "DEFAULT_PRICE_TOLERANCE_WON = Decimal(0)" in source
    assert "DEFAULT_LIVE_TOLERANCE_BPS = Decimal(50)" in source
    assert 'toss_resolution_source="explicit_pipeline_market_directory"' in source
    assert "load_market_consistency_provenance" in source
    assert "automatic_provider_substitution" not in source
