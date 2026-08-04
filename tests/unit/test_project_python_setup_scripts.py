"""Static checks for the Windows main-project Python setup boundary."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


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
    assert "ZoneInfo('Asia/Seoul')" in script
    assert '"ALPHA_CYCLE_PYTHON"' in script


def test_setup_waits_for_post_install_python_registration() -> None:
    script = _read("scripts/setup_project_python.ps1")

    assert "function Wait-X64ProjectPython" in script
    assert "Start-Sleep -Seconds $DelaySeconds" in script
    assert "$BasePython = Wait-X64ProjectPython" in script
    assert 'Write-Host "Using main x64 Python: $BasePython"' in script


def test_setup_can_create_venv_through_verified_python_launcher() -> None:
    script = _read("scripts/setup_project_python.ps1")

    assert "function Test-X64PythonInvocation" in script
    assert "function Resolve-X64PythonInvocation" in script
    assert '"-V:3.13"' in script
    assert '"-V:3.12"' in script
    assert "$BaseInvocation = Resolve-X64PythonInvocation" in script
    assert "Using verified main x64 Python command" in script
    assert "& $BaseInvocation.Executable" in script
    assert "@($BaseInvocation.PrefixArguments)" in script
    assert "-m venv $VirtualEnvironmentRoot" in script


def test_setup_rejects_kiwoom_x86_runtime_for_main_analysis() -> None:
    script = _read("scripts/setup_project_python.ps1")

    assert "struct.calcsize('P') * 8" in script
    assert "$bitness -ne 64" in script
    assert '$resolved -notlike "*.venv-kiwoom-x86*"' in script
    assert "Kiwoom bridge Python remains isolated in .venv-kiwoom-x86" in script


def test_setup_cmd_preserves_arguments_and_exit_code() -> None:
    launcher = _read("scripts/setup_project_python.cmd")

    assert "-ExecutionPolicy Bypass" in launcher
    assert '"%~dp0setup_project_python.ps1" %*' in launcher
    assert "ERRORLEVEL" in launcher
    assert "exit /b %EXIT_CODE%" in launcher


def test_resolver_discovers_launcher_registry_and_common_install_roots() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert "function Add-LauncherCandidates" in resolver
    assert '"-3.12-64"' in resolver
    assert '"-V:3.12"' in resolver
    assert "-0p" in resolver
    assert "function Add-RegistryCandidates" in resolver
    assert "RegistryView]::Registry64" in resolver
    assert "RegistryView]::Registry32" in resolver
    assert 'OpenSubKey("Software\\Python\\PythonCore")' in resolver
    assert 'GetValue("ExecutablePath", "")' in resolver
    assert '$env:ProgramFiles' in resolver
    assert '$env:ProgramW6432' in resolver
    assert 'Join-Path $env:LOCALAPPDATA "Programs\\Python"' in resolver


def test_resolver_captures_python_launcher_inventory_from_both_streams() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert "$installed = & $launcher -0p 2>&1" in resolver
    assert '"-3.13-64"' in resolver
    assert '"-V:3.13"' in resolver
    assert '"-3"' in resolver
    assert "runtime inventory to stderr" in resolver
    assert "python(?:w)?\\.exe" in resolver


def test_resolver_candidate_collectors_accept_an_initially_empty_list() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert resolver.count("[AllowEmptyCollection()]") == 3
    for function_name in (
        "Add-DirectoryCandidates",
        "Add-RegistryCandidates",
        "Add-LauncherCandidates",
    ):
        function_start = resolver.index(f"function {function_name}")
        function_body = resolver[function_start : function_start + 400]
        assert "[AllowEmptyCollection()]" in function_body
        assert "List[object]]$Candidates" in function_body


def test_resolver_points_to_automatic_setup_when_x64_is_missing() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert ".\\scripts\\setup_project_python.cmd -InstallPython" in resolver
    assert "64-bit Python 3.12+" in resolver
    assert "x86 bridge Python is intentionally excluded" in resolver


def test_windows_timezone_data_is_a_direct_project_dependency() -> None:
    pyproject = _read("pyproject.toml")

    assert '"tzdata>=2024.1; platform_system == \'Windows\'"' in pyproject
