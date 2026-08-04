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


def test_resolver_points_to_automatic_setup_when_x64_is_missing() -> None:
    resolver = _read("scripts/resolve_project_python.ps1")

    assert ".\\scripts\\setup_project_python.cmd -InstallPython" in resolver
    assert "64-bit Python 3.12+" in resolver
    assert "x86 bridge Python is intentionally excluded" in resolver


def test_windows_timezone_data_is_a_direct_project_dependency() -> None:
    pyproject = _read("pyproject.toml")

    assert '"tzdata>=2024.1; platform_system == \'Windows\'"' in pyproject
