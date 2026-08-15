SCRIPT = "scripts/report_skhynix_opendart_q2_product_revenue_certification.ps1"


def _script_text() -> str:
    with open(SCRIPT, encoding="utf-8") as handle:
        return handle.read()


def test_launcher_requires_opendart_secret_without_printing_it() -> None:
    text = _script_text()
    assert "$env:OPENDART_API_KEY" in text
    assert "OPENDART_API_KEY is required" in text
    assert "Write-Host $env:OPENDART_API_KEY" not in text
    assert "Write-Output $env:OPENDART_API_KEY" not in text


def test_launcher_rebuilds_ir_assignment_before_live_product_revenue_when_missing() -> None:
    text = _script_text()
    assert "Test-Path $IrAssignmentPointer" in text
    assert "report_skhynix_official_ir_q2_product_assignment_certification.ps1" in text
    assert "alpha_cycle.sk_hynix_opendart_q2_product_revenue_certification_cli" in text
    assert "--ir-assignment-pointer $IrAssignmentPointer" in text
