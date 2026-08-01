"""Static safety checks for the Windows credential bootstrap scripts."""

from __future__ import annotations

from pathlib import Path

REQUIRED = (
    "TOSSINVEST_CLIENT_ID",
    "TOSSINVEST_CLIENT_SECRET",
    "OPENDART_API_KEY",
    "ECOS_API_KEY",
)
ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_setup_script_persists_required_credentials_without_echoing_values() -> None:
    script = _read("scripts/setup_local_credentials.ps1")
    for name in REQUIRED:
        assert name in script
    assert 'Read-Host "Enter $name" -AsSecureString' in script
    assert 'SetEnvironmentVariable($name, $plainValue, "User")' in script
    assert 'SetEnvironmentVariable($name, $plainValue, "Process")' in script
    assert "ZeroFreeBSTR" in script
    assert "Write-Host $plainValue" not in script
    assert "Write-Output $plainValue" not in script


def test_runner_loads_user_credentials_and_never_reads_missing_report_path() -> None:
    script = _read("scripts/run_live_pipeline.ps1")
    for name in REQUIRED:
        assert name in script
    assert 'GetEnvironmentVariable($name, "User")' in script
    assert '& $SetupScript' in script
    assert "python -m alpha_cycle.live_pipeline_cli" in script
    assert '$status.status -eq "completed" -and $status.report_path' in script
    assert "Get-Content $status.report_path" in script


def test_cmd_launcher_bypasses_local_execution_policy_for_repo_script() -> None:
    launcher = _read("scripts/run_live_pipeline.cmd")
    assert "-ExecutionPolicy Bypass" in launcher
    assert '"%~dp0run_live_pipeline.ps1"' in launcher
    assert "%*" in launcher
