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
    $ProjectPython = "python"
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
& $ProjectPython -m alpha_cycle.sec_product_mix_calibration_cli `
    --document-id $DocumentId `
    --observed-date $ObservedDate `
    --output $Output
exit $LASTEXITCODE
