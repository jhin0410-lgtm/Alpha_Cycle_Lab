from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "script_name",
    [
        "capture_sec_product_mix_calibration.ps1",
        "scout_sec_post_earnings_product_mix.ps1",
        "inventory_sec_post_earnings_all_forms.ps1",
    ],
)
def test_sec_windows_scripts_prefer_project_venv_and_preflight_dependencies(
    script_name: str,
) -> None:
    script = (Path("scripts") / script_name).read_text(encoding="utf-8")

    override_index = script.index('GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")')
    venv_index = script.index('".venv\\Scripts\\python.exe"')
    fallback_index = script.index('$ProjectPython = "python"')
    preflight_index = script.index('& $ProjectPython -c "import alpha_cycle, pypdf"')
    command_index = script.index('& $ProjectPython -m alpha_cycle.')

    assert override_index < venv_index < fallback_index < preflight_index < command_index
    assert "Test-Path $VenvPython" in script
    assert "Resolve-Path $VenvPython" in script
    assert "py -3.12 -m venv .venv" in script
    assert ".\\.venv\\Scripts\\python.exe -m pip install -e ." in script
    assert "SEC_EDGAR_USER_AGENT" in script
