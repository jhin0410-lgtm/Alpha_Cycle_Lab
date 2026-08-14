[CmdletBinding()]
param(
    [string]$ObservedDate = "",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/sec-product-mix-calibration"
$DocumentId = "skhynix_000660_2026q1_sec_424b4_product_mix"

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
        "Alpha Cycle Python dependencies are not ready for SEC research. " +
        "Resolved Python: $ProjectPython`n" +
        "Create/install the project environment with:`n" +
        "  py -3.12 -m venv .venv`n" +
        "  .\.venv\Scripts\python.exe -m pip install --upgrade pip`n" +
        "  .\.venv\Scripts\python.exe -m pip install -e .`n" +
        "Then rerun this script. You may also set ALPHA_CYCLE_PYTHON to an explicit interpreter."
    )
}

$SecUserAgent = [Environment]::GetEnvironmentVariable("SEC_EDGAR_USER_AGENT", "Process")
if ([string]::IsNullOrWhiteSpace($SecUserAgent)) {
    throw (
        "SEC_EDGAR_USER_AGENT is required. Set an application name and contact email, " +
        "for example: AlphaCycleLab contact@example.com"
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

Write-Host "Capturing official SEC SK hynix 1Q26 product-mix calibration evidence."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sec_product_mix_calibration_cli `
    --document-id $DocumentId `
    --observed-date $ObservedDate `
    --output $Output
exit $LASTEXITCODE
