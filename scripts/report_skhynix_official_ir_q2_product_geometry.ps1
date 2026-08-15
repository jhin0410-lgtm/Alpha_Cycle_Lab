[CmdletBinding()]
param(
    [string]$EvaluationDate = "",
    [string]$CertificationPointer = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultCertificationPointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-source-certification/latest_skhynix_ir_q2_source_certification.json"
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-product-geometry"

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
if ([string]::IsNullOrWhiteSpace($CertificationPointer)) {
    $CertificationPointer = $DefaultCertificationPointer
}
if ([string]::IsNullOrWhiteSpace($Output)) { $Output = $DefaultOutput }

Write-Host "Reverifying the archived SK hynix 2Q26 PDF and preserving text-fragment geometry."
Write-Host "Coordinates are review evidence only; numeric semantics remain disabled."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_q2_product_geometry_cli `
    --evaluation-date $EvaluationDate `
    --certification-pointer $CertificationPointer `
    --output $Output
exit $LASTEXITCODE
