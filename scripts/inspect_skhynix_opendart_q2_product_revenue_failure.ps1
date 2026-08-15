[CmdletBinding()]
param(
    [string]$Diagnostic = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultRoot = Join-Path $RepositoryRoot "data/private/research/skhynix-opendart-q2-product-revenue-certification"
Set-Location $RepositoryRoot

$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $VenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) { $ProjectPython = (Resolve-Path $VenvPython).Path }
    else { $ProjectPython = "python" }
}

Write-Host "Inspecting preserved SK hynix OpenDART failure evidence offline."
Write-Host "No OpenDART API call is made and OPENDART_API_KEY is not read."
Write-Host "Python: $ProjectPython"

$Arguments = @(
    "-m", "alpha_cycle.sk_hynix_opendart_q2_product_revenue_failure_diagnostic_cli",
    "--root", $DefaultRoot
)
if (-not [string]::IsNullOrWhiteSpace($Diagnostic)) {
    $Arguments += @("--diagnostic", $Diagnostic)
}
& $ProjectPython @Arguments
exit $LASTEXITCODE
