"""Static regression checks for exact project venv boundary handling."""

from pathlib import Path

SCRIPT = Path("scripts/setup_project_python.ps1").read_text(encoding="utf-8")


def test_forced_setup_uses_an_exact_directory_boundary() -> None:
    assert "function Test-PathInsideDirectory" in SCRIPT
    assert ".TrimEnd(" in SCRIPT
    assert "$boundary = $directory + [System.IO.Path]::DirectorySeparatorChar" in SCRIPT
    assert "$candidate.StartsWith(" in SCRIPT
    assert "[System.StringComparison]::OrdinalIgnoreCase" in SCRIPT


def test_sibling_venv_names_remain_valid_external_candidates() -> None:
    assert ".venv-tools" in SCRIPT
    assert ".venv-backup" in SCRIPT
    assert "function Resolve-ConfiguredExternalPython" in SCRIPT
    assert "Resolve-SetupBasePython -ForcedRebuild:$Force" in SCRIPT


def test_exact_external_candidate_is_selected_before_prefix_based_fallback() -> None:
    configured = SCRIPT.index("$configuredExternal = Resolve-ConfiguredExternalPython")
    fallback = SCRIPT.index(
        "return Resolve-X64ProjectPython -ExcludeProjectVenv:$ForcedRebuild"
    )
    assert configured < fallback
    assert "-not (Test-PathInsideDirectory" in SCRIPT
    assert "Test-X64ProjectPython -PythonPath $fullPath" in SCRIPT
