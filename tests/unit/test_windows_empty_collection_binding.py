"""Regression checks for empty generic collections in Windows PowerShell helpers."""

from pathlib import Path

RESOLVER = Path("scripts/resolve_project_python.ps1").read_text(encoding="utf-8")


def test_seen_hashset_accepts_an_empty_collection() -> None:
    marker = "[System.Collections.Generic.HashSet[string]]$Seen"
    position = RESOLVER.index(marker)
    prefix = RESOLVER[max(0, position - 180) : position]

    assert "[Parameter(Mandatory = $true)]" in prefix
    assert "[AllowEmptyCollection()]" in prefix


def test_all_mandatory_generic_collection_parameters_allow_empty_input() -> None:
    lines = RESOLVER.splitlines()
    generic_markers = (
        "[System.Collections.Generic.List[object]]$Candidates",
        "[System.Collections.Generic.List[object]]$Results",
        "[System.Collections.Generic.HashSet[string]]$Seen",
    )

    for index, line in enumerate(lines):
        if any(marker in line for marker in generic_markers):
            window = "\n".join(lines[max(0, index - 3) : index + 1])
            if "[Parameter(Mandatory = $true)]" in window:
                assert "[AllowEmptyCollection()]" in window
