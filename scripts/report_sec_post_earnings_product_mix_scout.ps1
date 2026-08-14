[CmdletBinding()]
param(
    [string]$EvaluationDate = "",
    [string]$Pointer = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultPointer = Join-Path $RepositoryRoot "data/private/research/sec-post-earnings-product-mix-scout/latest_sec_post_earnings_product_mix_scout.json"

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

& $ProjectPython -c "import alpha_cycle" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw (
        "Alpha Cycle Python environment is not ready. Resolved Python: $ProjectPython`n" +
        "Run .\.venv\Scripts\python.exe -m pip install -e . first."
    )
}

if ([string]::IsNullOrWhiteSpace($EvaluationDate)) {
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $EvaluationDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow,
        $korea
    ).ToString("yyyy-MM-dd")
}
if ([string]::IsNullOrWhiteSpace($Pointer)) {
    $Pointer = $DefaultPointer
}

Write-Host "Reverifying archived SEC scout bytes and reporting filing-level classifications."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sec_post_earnings_product_mix_scout_report_cli `
    --evaluation-date $EvaluationDate `
    --pointer $Pointer
exit $LASTEXITCODE
