[CmdletBinding()]
param(
    [string]$ObservedDate = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-attachment-discovery"

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
        "Alpha Cycle Python dependencies are not ready for SK hynix IR discovery. " +
        "Resolved Python: $ProjectPython`n" +
        "Create/install the project environment with:`n" +
        "  py -3.12 -m venv .venv`n" +
        "  .\.venv\Scripts\python.exe -m pip install --upgrade pip`n" +
        "  .\.venv\Scripts\python.exe -m pip install -e .`n" +
        "Then rerun this script. You may also set ALPHA_CYCLE_PYTHON to an explicit interpreter."
    )
}
if ([string]::IsNullOrWhiteSpace($ObservedDate)) {
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $ObservedDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow,
        $korea
    ).ToString("yyyy-MM-dd")
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = $DefaultOutput
}

Write-Host "Discovering the SK hynix 2Q26 official IR attachment without guessing CDN IDs."
Write-Host "Only URLs explicitly present in issuer-controlled page/JavaScript bytes are accepted."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_attachment_discovery_cli `
    --observed-date $ObservedDate `
    --output $Output
exit $LASTEXITCODE
