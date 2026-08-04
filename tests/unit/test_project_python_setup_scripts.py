"""Checks for the Windows main-project Python setup boundary."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_project_python_probe_reports_machine_readable_identity() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/project_python_probe.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["schema_version"] == "1.0"
    assert payload["bitness"] == struct.calcsize("P") * 8
    assert payload["major"] == sys.version_info.major
    assert payload["minor"] == sys.version_info.minor
    assert Path(payload["executable"]).resolve() == Path(sys.executable).resolve()


def test_project_python_probe_verifies_installed_project_environment() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/project_python_probe.py"),
            "--verify-project",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "PROJECT PYTHON: PASS" in completed.stdout
    assert "Python bitness:" in completed.stdout
    assert "NumPy:" in completed.stdout
    assert "pandas:" in completed.stdout
    assert "PyYAML:" in completed.stdout


def test_setup_installs_x64_python_and_creates_main_virtual_environment() -> None:
    script = _read("scripts/setup_project_python.ps1")

    assert "Python.Python.3.12" in script
    assert "--architecture x64" in script
    assert "--scope user" in script
    assert "--force" in script
    assert 'Join-Path $RepositoryRoot ".venv"' in script
    assert 'Join-Path $VirtualEnvironmentRoot "Scripts\\python.exe"' in script
    assert "-m venv" in script
    assert '--editable ".[dev]"' in script
    assert '"ALPHA_CYCLE_PYTHON"' in script


def test_setup_uses_probe_script_instead_of_inline_python_code() -> None:
    script = _read("scripts/setup_project_python.ps1")

    assert 'Join-Path $ScriptDirectory "project_python_probe.py"' in script
    assert "& $PythonPath $ProbeScript" in script
    assert "$VirtualEnvironmentPython $ProbeScript --verify-project" in script
    assert "python -c" not in script.casefold()
    assert "-c @\"" not in script


def test_setup_waits_for_post_install_python_registration() -> None:
    script = _read("scripts/setup_project_python.ps1")

    assert "function Wait-X64ProjectPython" in script
    assert "Start-Sleep -Seconds $DelaySeconds" in script
    assert "$BasePython = Wait-X64ProjectPython" in script
    assert 'Write-Host "Using main x64 Python: $BasePython"' in script


def test_setup_rejects_kiwoom_x86_runtime_for_main_analysis() -> None:
    script = _read("scripts/setup_project_python.ps1")

    assert "$bitness -eq 64" in script
    assert '$resolved -notlike "*.venv-kiwoom-x86*"' in script
    assert "Kiwoom bridge Python remains isolated in .venv-kiwoom-x86" in script


def test_setup_cmd_preserves_arguments_and_exit_code() -> None:
    launcher = _read("scripts/setup_project_python.cmd")

    assert "-ExecutionPolicy Bypass" in launcher
    assert '"%~dp0setup_project_python.ps1" %*' in launcher
    assert "ERRORLEVEL" in launcher
    assert "exit /b %EXIT_CODE%" in launcher


def test_resolver_uses_script_probe_without_native_argument_quoting_risk() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert 'Join-Path $ScriptDirectory "project_python_probe.py"' in resolver
    assert "$arguments = @($PrefixArguments) + @($ProbeScript)" in resolver
    assert "$raw = & $Executable @arguments 2>&1" in resolver
    assert "ConvertFrom-Json" in resolver
    assert "$probeCode" not in resolver
    assert "ALPHA_CYCLE_PYTHON|" not in resolver


def test_resolver_discovers_direct_launcher_registry_and_install_roots() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert "Python312\\python.exe" in resolver
    assert "Python312-32\\python.exe" in resolver
    assert '"-3.12-64"' in resolver
    assert '"-3-64"' in resolver
    assert "-0p" in resolver
    assert "function Add-RegistryCandidates" in resolver
    assert "RegistryView]::Registry64" in resolver
    assert "RegistryView]::Registry32" in resolver
    assert 'OpenSubKey("Software\\Python\\PythonCore")' in resolver
    assert 'Join-Path $env:LOCALAPPDATA "Programs\\Python"' in resolver
    assert 'Join-Path $env:LOCALAPPDATA "Microsoft\\WindowsApps"' in resolver


def test_resolver_excludes_python_venv_templates_from_recursive_candidates() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert '-Filter "python.exe"' in resolver
    assert "-Recurse" in resolver
    assert "\\\\Lib\\\\venv\\\\scripts\\\\" in resolver
    assert "\\\\.venv-kiwoom-x86\\\\" in resolver


def test_resolver_records_candidate_rejection_reasons() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    for status in (
        "launch_failed",
        "invalid_probe",
        "rejected_32_bit",
        "version_too_old",
        "rejected_kiwoom_bridge",
        "resolved_path_missing",
        "accepted",
    ):
        assert status in resolver
    assert "project_python_resolution.json" in resolver
    assert "Write-DiagnosticReport" in resolver
    assert 'schema_version = "1.1"' in resolver


def test_diagnostic_cmd_preserves_exit_code_and_reports_artifact() -> None:
    script = _read("scripts/diagnose_project_python.cmd")

    assert "resolve_project_python.ps1" in script
    assert "-Diagnostic" in script
    assert "ERRORLEVEL" in script
    assert "project_python_resolution.json" in script
    assert "exit /b %EXIT_CODE%" in script


def test_windows_timezone_data_is_a_direct_project_dependency() -> None:
    pyproject = _read("pyproject.toml")

    assert '"tzdata>=2024.1; platform_system == \'Windows\'"' in pyproject
