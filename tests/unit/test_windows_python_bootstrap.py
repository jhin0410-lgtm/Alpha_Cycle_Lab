"""Static checks for Windows source-tree and interpreter isolation wrappers."""

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _script(path: str) -> str:
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8").casefold()


def test_project_python_resolver_rejects_kiwoom_x86_runtime() -> None:
    resolver = _script("scripts/resolve_project_python.ps1")

    assert "alpha_cycle_python" in resolver
    assert ".venv\\scripts\\python.exe" in resolver
    assert "-3.12-64" in resolver
    assert '"-3"' in resolver
    assert "$bitness -ne 64" in resolver
    assert "rejected_32_bit" in resolver
    assert ".venv-kiwoom-x86" in resolver
    assert "python 3.12+" in resolver


def test_python_module_cmd_wrappers_use_project_python_launcher() -> None:
    for path, module in (
        (
            "scripts/check_market_source_consistency.cmd",
            "alpha_cycle.market_consistency_runner_cli",
        ),
        ("scripts/verify_latest_run.cmd", "alpha_cycle.live_verify_cli"),
        (
            "scripts/show_latest_corrections.cmd",
            "alpha_cycle.correction_lineage_cli",
        ),
    ):
        script = _script(path)
        assert "run_alpha_cycle_module.ps1" in script
        assert f'-module "{module}"' in script
        assert "python -m" not in script


def test_module_launcher_uses_resolved_interpreter_and_source_tree() -> None:
    launcher = _script("scripts/run_alpha_cycle_module.ps1")

    assert "resolve_project_python.ps1" in launcher
    assert "$projectpython -m $module" in launcher
    assert "pythonpath" in launcher
    assert 'join-path $repositoryroot "src"' in launcher
    assert "alpha_cycle_python" in launcher


def test_live_pipeline_bootstrap_prepends_resolved_python_to_path() -> None:
    command = _script("scripts/run_live_pipeline.cmd")
    bootstrap = _script("scripts/run_live_pipeline_bootstrap.ps1")
    orchestrator = _script("scripts/run_live_pipeline_orchestrator.ps1")

    assert "run_live_pipeline_bootstrap.ps1" in command
    assert "resolve_project_python.ps1" in bootstrap
    assert "$env:path" in bootstrap
    assert "$projectpythondirectory" in bootstrap
    assert "alpha_cycle_python" in bootstrap
    assert "run_live_pipeline_orchestrator.ps1" in bootstrap
    assert "run_live_pipeline.ps1" in orchestrator
