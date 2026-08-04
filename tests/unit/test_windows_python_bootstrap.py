"""Static checks for Windows wrappers that must run from an uninstalled checkout."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _script(path: str) -> str:
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8").casefold()


def test_market_consistency_cmd_bootstraps_repository_src() -> None:
    script = _script("scripts/check_market_source_consistency.cmd")
    assert "%~dp0.." in script
    assert "pythonpath" in script
    assert "\\src" in script
    assert "pushd" in script
    assert "alpha_cycle.market_consistency_cli" in script


def test_existing_read_only_cmd_wrappers_bootstrap_repository_src() -> None:
    for path, module in (
        ("scripts/verify_latest_run.cmd", "alpha_cycle.live_verify_cli"),
        ("scripts/show_latest_corrections.cmd", "alpha_cycle.correction_lineage_cli"),
    ):
        script = _script(path)
        assert "%~dp0.." in script
        assert "pythonpath" in script
        assert "\\src" in script
        assert "pushd" in script
        assert module in script


def test_live_pipeline_powershell_bootstraps_repository_src() -> None:
    script = _script("scripts/run_live_pipeline.ps1")
    assert "$repositoryroot" in script
    assert "$env:pythonpath" in script
    assert "src" in script
