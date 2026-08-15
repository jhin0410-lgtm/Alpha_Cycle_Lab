[CmdletBinding()]
param(
    [string]$EvaluationDate = "",
    [string]$GeometryPointer = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultGeometryPointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-product-geometry/latest_skhynix_ir_q2_product_geometry.json"
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-share-column-certification"

Set-Location $RepositoryRoot
$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $VenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) { $ProjectPython = (Resolve-Path $VenvPython).Path }
    else { $ProjectPython = "python" }
}

& $ProjectPython -c "import alpha_cycle, pypdf" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Alpha Cycle Python dependencies are not ready. Resolved Python: $ProjectPython"
}
if ([string]::IsNullOrWhiteSpace($EvaluationDate)) {
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $EvaluationDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow, $korea
    ).ToString("yyyy-MM-dd")
}
if ([string]::IsNullOrWhiteSpace($GeometryPointer)) {
    $GeometryPointer = $DefaultGeometryPointer
}
if ([string]::IsNullOrWhiteSpace($Output)) { $Output = $DefaultOutput }

Write-Host "Reverifying SK hynix 2Q26 product geometry and certifying period columns only."
Write-Host "The rightmost current column may expose 73%/27%, but product assignment and Other=0 stay disabled."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_q2_share_column_certification_cli `
    --evaluation-date $EvaluationDate `
    --geometry-pointer $GeometryPointer `
    --output $Output
exit $LASTEXITCODE
