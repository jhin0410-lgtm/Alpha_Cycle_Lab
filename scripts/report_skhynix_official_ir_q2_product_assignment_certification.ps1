[CmdletBinding()]
param(
    [string]$EvaluationDate = "",
    [string]$ShareColumnPointer = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultShareColumnPointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-share-column-certification/latest_skhynix_ir_q2_share_column_certification.json"
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-product-assignment-certification"

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
if ([string]::IsNullOrWhiteSpace($ShareColumnPointer)) {
    $ShareColumnPointer = $DefaultShareColumnPointer
}
if ([string]::IsNullOrWhiteSpace($Output)) { $Output = $DefaultOutput }

Write-Host "Reverifying SK hynix 2Q26 share columns and official PDF vector colours."
Write-Host "DRAM=73% and NAND=27% may be certified; numeric Other share and allocation remain disabled."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_q2_product_assignment_certification_cli `
    --evaluation-date $EvaluationDate `
    --share-column-pointer $ShareColumnPointer `
    --output $Output
exit $LASTEXITCODE
