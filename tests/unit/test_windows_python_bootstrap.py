"""Static checks for Windows wrappers that must run from an uninstalled checkout."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _script(path: str) -> str:
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8").casefold()


def test_python_module_cmd_wrappers_bootstrap_repository_src() -> None:
    for path, module in (
        (
            "scripts/check_market_source_consistency.cmd",
            "alpha_cycle.market_consistency_cli",
        ),
        ("scripts/verify_latest_run.cmd", "alpha_cycle.live_verify_cli"),
        (
            "scripts/show_latest_corrections.cmd",
            "alpha_cycle.correction_lineage_cli",
        ),
    ):
        script = _script(path)
        assert "%~dp0.." in script
        assert "repository_root" in script
        assert "pythonpath" in script
        assert "\\src" in script
        assert "pushd" in script
        assert module in script


def test_live_pipeline_wrapper_passes_repository_src_to_powershell() -> None:
    script = _script("scripts/run_live_pipeline.cmd")
    assert "%~dp0.." in script
    assert "repository_root" in script
    assert "pythonpath" in script
    assert "\\src" in script
    assert "pushd" in script
    assert "run_live_pipeline.ps1" in script
