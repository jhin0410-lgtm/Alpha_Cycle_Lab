"""Static checks for Windows live and resume option integrity."""

from pathlib import Path

SCRIPT = Path("scripts/run_live_pipeline.ps1").read_text(encoding="utf-8")


def test_custom_output_controls_the_status_pointer_path() -> None:
    assert "function Get-PipelineOptionValue" in SCRIPT
    assert 'Get-PipelineOptionValue -Arguments $Arguments -OptionName "--output"' in SCRIPT
    assert "$OutputRoot = Resolve-OutputRoot -Arguments $PipelineArguments" in SCRIPT
    assert '$StatusPath = Join-Path $OutputRoot "latest_run.json"' in SCRIPT
    assert '$StatusPath = Join-Path $RepositoryRoot "data/private/live-research' not in SCRIPT


def test_stale_status_files_are_not_reported_as_the_current_run() -> None:
    assert "function Get-StatusWriteTicks" in SCRIPT
    assert "function Test-CurrentStatusFile" in SCRIPT
    assert "$statusTicksBefore = Get-StatusWriteTicks -Path $StatusPath" in SCRIPT
    assert "$statusIsCurrent = Test-CurrentStatusFile" in SCRIPT
    assert "Pipeline did not create a current status file" in SCRIPT


def test_resume_preserves_all_shared_live_options() -> None:
    for option in (
        "--evaluation-date",
        "--output",
        "--history-years",
        "--timeout-seconds",
        "--max-retries",
    ):
        assert f'"{option}"' in SCRIPT
    assert "$ResumeArguments = New-ResumeArguments -Arguments $PipelineArguments" in SCRIPT
    assert "$ProjectPython -m alpha_cycle.resume_pipeline_cli @ResumeArguments" in SCRIPT
    assert "$ProjectPython -m alpha_cycle.resume_pipeline_cli\n" not in SCRIPT


def test_both_option_syntaxes_are_supported() -> None:
    assert '$argument -eq $OptionName' in SCRIPT
    assert '$prefix = "$OptionName="' in SCRIPT
    assert "$argument.Substring($prefix.Length)" in SCRIPT
