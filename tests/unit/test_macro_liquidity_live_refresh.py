from __future__ import annotations

from pathlib import Path


def test_live_bootstrap_refreshes_macro_liquidity_before_pipeline() -> None:
    bootstrap = Path("scripts/run_live_pipeline_bootstrap.ps1").read_text(encoding="utf-8")
    refresh = Path("scripts/refresh_macro_liquidity.ps1").read_text(encoding="utf-8")

    assert "$MacroLiquidityRefresh" in bootstrap
    assert "& $MacroLiquidityRefresh @PipelineArguments" in bootstrap
    assert bootstrap.index("& $MacroLiquidityRefresh @PipelineArguments") < bootstrap.index(
        "& $Pipeline @PipelineArguments"
    )

    assert "alpha_cycle.macro_liquidity_cli" in refresh
    assert "--evaluation-date" in refresh
    assert "--timeout-seconds" in refresh
    assert "live pipeline will continue" in refresh
    assert "exit 0" in refresh
    assert "Korea Standard Time" in refresh
