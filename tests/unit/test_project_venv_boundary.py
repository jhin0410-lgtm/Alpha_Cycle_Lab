"""Static regression checks for exact project venv boundary handling."""

from pathlib import Path

SCRIPT = Path("scripts/setup_project_python.ps1").read_text(encoding="utf-8")


def test_forced_setup_uses_an_exact_directory_boundary() -> None:
    assert "function Test-PathInsideDirectory" in SCRIPT
    assert ".TrimEnd(" in SCRIPT
    assert "$boundary = $directory + [System.IO.Path]::DirectorySeparatorChar" in SCRIPT
    assert "$candidate.StartsWith(" in SCRIPT
    assert "[System.StringComparison]::OrdinalIgnoreCase" in SCRIPT


def test_invalid_configured_paths_are_skipped_before_fallback() -> None:
    configured = SCRIPT.index("function Resolve-ConfiguredExternalPython")
    candidate_loop = SCRIPT.index("foreach ($candidate in $candidates)", configured)
    fallback = SCRIPT.index(
        "return Resolve-X64ProjectPython -ExcludeProjectVenv:$ForcedRebuild"
    )
    segment = SCRIPT[candidate_loop:fallback]
    assert "$candidate.Trim('\"')" in segment
    assert "catch {\n            continue\n        }" in segment
    assert "Resolve-ProbedX64ProjectPython -PythonPath $candidatePath" in segment


def test_probed_executable_controls_project_venv_rejection() -> None:
    assert "function Resolve-ProbedX64ProjectPython" in SCRIPT
    assert "$resolved = [System.IO.Path]::GetFullPath([string]$payload.executable)" in SCRIPT
    assert "-CandidatePath $resolved" in SCRIPT
    assert "return $resolved" in SCRIPT
    assert "return $candidatePath" not in SCRIPT


def test_sibling_venv_names_remain_valid_external_candidates() -> None:
    assert "function Resolve-ConfiguredExternalPython" in SCRIPT
    assert "Resolve-SetupBasePython -ForcedRebuild:$Force" in SCRIPT
    assert "$boundary = $directory + [System.IO.Path]::DirectorySeparatorChar" in SCRIPT


def test_exact_external_candidate_is_selected_before_general_fallback() -> None:
    configured = SCRIPT.index("$configuredExternal = Resolve-ConfiguredExternalPython")
    fallback = SCRIPT.index(
        "return Resolve-X64ProjectPython -ExcludeProjectVenv:$ForcedRebuild"
    )
    assert configured < fallback
    assert "-not (Test-PathInsideDirectory" in SCRIPT
