"""Regression checks for late runtime-boundary Codex findings."""

from pathlib import Path


def test_kiwoom_bootstrap_propagates_exporter_exit_status() -> None:
    bootstrap = Path(
        "bridge/kiwoom_openapi_plus/market_export_bootstrap.py"
    ).read_text(encoding="utf-8")

    assert 'if __name__ == "__main__":' in bootstrap
    assert "raise SystemExit(main())" in bootstrap
    assert "\n    main()\n" not in bootstrap


def test_windows_pipeline_helpers_accept_default_empty_arguments() -> None:
    script = Path("scripts/run_live_pipeline.ps1").read_text(encoding="utf-8")

    assert script.count("[AllowEmptyCollection()]") >= 4
    assert "[string[]]$PipelineArguments = @()" in script
    for function_name in (
        "Get-PipelineOptionValue",
        "New-ResumeArguments",
        "Resolve-OutputRoot",
    ):
        section = script[script.index(f"function {function_name}") :]
        assert "[AllowEmptyCollection()]" in section.split("}", 1)[0]
