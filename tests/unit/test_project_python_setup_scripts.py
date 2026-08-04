"""Checks for the Windows main-project Python setup boundary."""

from __future__ import annotations

import importlib.util
import json
import struct
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _load_probe() -> ModuleType:
    path = ROOT / "scripts/project_python_probe.py"
    spec = importlib.util.spec_from_file_location("project_python_probe_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_project_python_probe_reports_machine_readable_identity() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/project_python_probe.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["schema_version"] == "1.1"
    assert payload["bitness"] == struct.calcsize("P") * 8
    assert payload["major"] == sys.version_info.major
    assert payload["minor"] == sys.version_info.minor
    assert Path(payload["executable"]).resolve() == Path(sys.executable).resolve()


def test_project_python_probe_serializes_unicode_paths_as_ascii_json() -> None:
    probe = _load_probe()
    sample_path = r"C:\Download\쿠쿠\coding\Alpha_Cycle_Lab\.venv\Scripts\python.exe"

    serialized = probe.serialize_runtime_identity(
        {"schema_version": "1.1", "executable": sample_path}
    )

    assert serialized.isascii()
    assert "쿠쿠" not in serialized
    assert json.loads(serialized)["executable"] == sample_path


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


def test_forced_setup_resolves_an_external_base_before_deleting_venv() -> None:
    script = _read("scripts/setup_project_python.ps1")

    resolve = script.index(
        "$BasePython = Resolve-X64ProjectPython -ExcludeProjectVenv:$Force"
    )
    remove = script.index("Remove-Item -Recurse -Force $VirtualEnvironmentRoot")
    assert resolve < remove
    assert "[switch]$ExcludeProjectVenv" in script
    assert '"-ExcludeProjectVenv"' in script


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


def test_resolver_prioritizes_active_candidates_before_recursive_scans() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    phase_one = resolver.index("# Phase 1:")
    path_candidate = resolver.index('Get-Command "python.exe"', phase_one)
    phase_two = resolver.index("# Phase 2:")
    recursive_phase = resolver.index("# Phase 3:")
    assert phase_one < path_candidate < phase_two < recursive_phase
    assert "Find-AcceptedCandidate" in resolver
    assert "HashSet[string]" in resolver


def test_resolver_guards_optional_windows_environment_roots() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert 'IsNullOrWhiteSpace($env:LOCALAPPDATA)' in resolver
    assert 'IsNullOrWhiteSpace($env:WINDIR)' in resolver
    assert 'IsNullOrWhiteSpace($env:ProgramFiles)' in resolver
    assert "@($env:ProgramFiles, $env:ProgramW6432)" in resolver


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
        "rejected_project_venv",
        "resolved_path_missing",
        "accepted",
    ):
        assert status in resolver
    assert "project_python_resolution.json" in resolver
    assert "Write-DiagnosticReport" in resolver
    assert 'schema_version = "1.1"' in resolver


def test_resolver_diagnostics_cannot_mask_resolution_failure() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    diagnostic = resolver[resolver.index("function Write-DiagnosticReport") :]
    assert "try {" in diagnostic
    assert "catch {" in diagnostic
    assert "[Console]::Error.WriteLine" in diagnostic
    assert "Write-Error" not in resolver
    assert "exit 2" in resolver


def test_diagnostic_cmd_preserves_exit_code_and_reports_artifact() -> None:
    script = _read("scripts/diagnose_project_python.cmd")

    assert "resolve_project_python.ps1" in script
    assert "-Diagnostic" in script
    assert "ERRORLEVEL" in script
    assert "project_python_resolution.json" in script
    assert "exit /b %EXIT_CODE%" in script


def test_live_pipeline_scripts_preserve_remaining_arguments() -> None:
    bootstrap = _read("scripts/run_live_pipeline_bootstrap.ps1")
    pipeline = _read("scripts/run_live_pipeline.ps1")

    for script in (bootstrap, pipeline):
        assert "ValueFromRemainingArguments = $true" in script
        assert "[string[]]$PipelineArguments = @()" in script
        assert "@PipelineArguments" in script
    assert "@args" not in pipeline
    assert "[Console]::Error.WriteLine" in pipeline
    assert "Write-Error" not in pipeline


def test_windows_timezone_data_is_a_direct_project_dependency() -> None:
    pyproject = _read("pyproject.toml")

    assert '"tzdata>=2024.1; platform_system == \'Windows\'"' in pyproject
