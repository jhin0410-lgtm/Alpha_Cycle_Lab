[CmdletBinding()]
param(
    [string]$EvaluationDate = "",
    [string]$Registry = "",
    [string]$Output = "",
    [string]$IrAssignmentPointer = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultRegistry = Join-Path $RepositoryRoot "config/semiconductor_periodic_product_revenue.yaml"
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-opendart-q2-product-revenue-certification"
$DefaultIrAssignmentPointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-product-assignment-certification/latest_skhynix_ir_q2_product_assignment_certification.json"

Set-Location $RepositoryRoot
$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $VenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) { $ProjectPython = (Resolve-Path $VenvPython).Path }
    else { $ProjectPython = "python" }
}

& $ProjectPython -c "import alpha_cycle, yaml" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Alpha Cycle Python dependencies are not ready. Resolved Python: $ProjectPython"
}
if ([string]::IsNullOrWhiteSpace($EvaluationDate)) {
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $EvaluationDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow, $korea
    ).ToString("yyyy-MM-dd")
}
if ([string]::IsNullOrWhiteSpace($Registry)) { $Registry = $DefaultRegistry }
if ([string]::IsNullOrWhiteSpace($Output)) { $Output = $DefaultOutput }
if ([string]::IsNullOrWhiteSpace($IrAssignmentPointer)) {
    $IrAssignmentPointer = $DefaultIrAssignmentPointer
}

$FailedRoot = Join-Path $Output "failed"
if (Test-Path $FailedRoot) {
    $LatestFailure = Get-ChildItem -Path $FailedRoot -Directory |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if ($null -ne $LatestFailure) {
        $FailureArchive = Join-Path $LatestFailure.FullName "opendart_document.zip"
        $FailureText = Join-Path $LatestFailure.FullName "normalized_document.txt"
        if ((Test-Path $FailureArchive) -and (Test-Path $FailureText)) {
            Write-Host "Offline-preflighting the latest preserved OpenDART failure before any new network request."
            & $ProjectPython -m alpha_cycle.sk_hynix_opendart_q2_product_revenue_offline_preflight_cli `
                --archive $FailureArchive `
                --normalized-text $FailureText `
                --registry $Registry
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
}

if ([string]::IsNullOrWhiteSpace($env:OPENDART_API_KEY)) {
    throw "OPENDART_API_KEY is required for official OpenDART discovery. The key is never printed or archived."
}

if (-not (Test-Path $IrAssignmentPointer)) {
    Write-Host "Official IR product-assignment evidence is missing; rebuilding the local certified IR chain first."
    & (Join-Path $ScriptDirectory "report_skhynix_official_ir_q2_product_assignment_certification.ps1") `
        -EvaluationDate $EvaluationDate
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Discovering the exact SK hynix 2026 half-year filing through official OpenDART."
Write-Host "Structural replay certifies one current consolidated product header and unit from the archived raw source."
Write-Host "The exact ZIP bytes will be archived; Q2 DRAM/NAND/Other amounts must be directly reported and reconcile."
Write-Host "Direct product revenue does not certify product profitability, numeric forecast, fair value, or decision score."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_opendart_q2_product_revenue_semantic_cli `
    --evaluation-date $EvaluationDate `
    --registry $Registry `
    --output $Output `
    --ir-assignment-pointer $IrAssignmentPointer
exit $LASTEXITCODE
