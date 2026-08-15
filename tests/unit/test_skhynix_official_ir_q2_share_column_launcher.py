from __future__ import annotations

from pathlib import Path


def test_share_column_launcher_uses_project_python_and_stays_offline() -> None:
    script = Path(
        "scripts/report_skhynix_official_ir_q2_share_column_certification.ps1"
    ).read_text(encoding="utf-8")

    override_index = script.index('GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")')
    venv_index = script.index('".venv\\Scripts\\python.exe"')
    preflight_index = script.index('& $ProjectPython -c "import alpha_cycle, pypdf"')
    command_index = script.index(
        "& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_q2_share_column_certification_cli"
    )

    assert override_index < venv_index < preflight_index < command_index
    assert "SEC_EDGAR_USER_AGENT" not in script
    assert "download" not in script.casefold()
    assert "product assignment and Other=0 stay disabled" in script
