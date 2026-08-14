[CmdletBinding()]
param(
    [string]$EvaluationDate = "",
    [string]$SourcePointer = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultSourcePointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-attachment-discovery/latest_skhynix_ir_attachment_discovery.json"
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-runtime-route-diagnostic"

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
        "Alpha Cycle Python dependencies are not ready for SK hynix IR runtime-route diagnostics. " +
        "Resolved Python: $ProjectPython`n" +
        "Create/install the project environment with:`n" +
        "  py -3.12 -m venv .venv`n" +
        "  .\.venv\Scripts\python.exe -m pip install --upgrade pip`n" +
        "  .\.venv\Scripts\python.exe -m pip install -e .`n" +
        "Then rerun this script. You may also set ALPHA_CYCLE_PYTHON to an explicit interpreter."
    )
}
if ([string]::IsNullOrWhiteSpace($EvaluationDate)) {
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $EvaluationDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow,
        $korea
    ).ToString("yyyy-MM-dd")
}
if ([string]::IsNullOrWhiteSpace($SourcePointer)) {
    $SourcePointer = $DefaultSourcePointer
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = $DefaultOutput
}

Write-Host "Reverifying archived SK hynix IR page/JavaScript bytes and extracting runtime-route signals."
Write-Host "This diagnostic is offline: it performs no network request and does not guess endpoints."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_runtime_route_diagnostic_cli `
    --evaluation-date $EvaluationDate `
    --source-pointer $SourcePointer `
    --output $Output
exit $LASTEXITCODE
