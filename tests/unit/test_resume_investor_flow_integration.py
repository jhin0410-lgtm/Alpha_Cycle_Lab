"""Regression tests for investor-flow evidence in the Toss-block resume path."""

from __future__ import annotations

from pathlib import Path


def test_resume_pipeline_keeps_live_investor_flow_contract() -> None:
    """The fallback decision path must not silently drop live flow evidence."""

    live_source = Path("src/alpha_cycle/live_pipeline_cli.py").read_text(encoding="utf-8")
    resume_source = Path("src/alpha_cycle/resume_pipeline_cli.py").read_text(
        encoding="utf-8"
    )

    contract_tokens = (
        "DEFAULT_INVESTOR_FLOW_POINTER",
        "investor_flow_pointer=flow_pointer",
        "**_flow_status(scorecards)",
    )
    for token in contract_tokens:
        assert token in live_source
        assert token in resume_source


def test_resume_pipeline_only_uses_existing_flow_pointer() -> None:
    """Resume remains optional/fail-closed when no local flow artifact exists."""

    source = Path("src/alpha_cycle/resume_pipeline_cli.py").read_text(encoding="utf-8")

    assert "if DEFAULT_INVESTOR_FLOW_POINTER.is_file()" in source
    assert "else None" in source
    assert "investor_flow_pointer=flow_pointer" in source
