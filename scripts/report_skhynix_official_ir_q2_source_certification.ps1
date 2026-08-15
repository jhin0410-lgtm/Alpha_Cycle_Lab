[CmdletBinding()]
param(
    [string]$EvaluationDate = "",
    [string]$AttachmentPointer = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultAttachmentPointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-attachment/latest_skhynix_ir_q2_attachment.json"
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-source-certification"

Set-Location $RepositoryRoot
$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $VenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $ProjectPython = (Resolve-Path $VenvPython).Path
    }
    else {
        $ProjectPython = "python"
    }
}

& $ProjectPython -c "import alpha_cycle, pypdf" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw (
        "Alpha Cycle Python dependencies are not ready for SK hynix Q2 source certification. " +
        "Resolved Python: $ProjectPython`n" +
        "Create/install the project environment with:`n" +
        "  py -3.12 -m venv .venv`n" +
        "  .\.venv\Scripts\python.exe -m pip install --upgrade pip`n" +
        "  .\.venv\Scripts\python.exe -m pip install -e ."
    )
}
if ([string]::IsNullOrWhiteSpace($EvaluationDate)) {
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $EvaluationDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow,
        $korea
    ).ToString("yyyy-MM-dd")
}
if ([string]::IsNullOrWhiteSpace($AttachmentPointer)) {
    $AttachmentPointer = $DefaultAttachmentPointer
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = $DefaultOutput
}

Write-Host "Reverifying the archived official SK hynix 2Q26 PDF and preserving product-page layout."
Write-Host "Board displayDate is retained as provenance only; publication date must come from PDF bytes."
Write-Host "Numeric semantics, registry activation, forecasts, and decision scores remain disabled."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_q2_source_certification_cli `
    --evaluation-date $EvaluationDate `
    --attachment-pointer $AttachmentPointer `
    --output $Output
exit $LASTEXITCODE
