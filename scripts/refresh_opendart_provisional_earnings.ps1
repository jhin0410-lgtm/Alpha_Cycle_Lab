[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyCollection()]
    [string[]]$PipelineArguments = @()
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultOutputRoot = Join-Path $RepositoryRoot "data/private/live-research"
$DocumentId = "skhynix_000660_2026q2_provisional"

function Get-OptionValue {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Name
    )
    for ($index = 0; $index -lt $Arguments.Count; $index++) {
        $argument = [string]$Arguments[$index]
        if ($argument -eq $Name -and $index + 1 -lt $Arguments.Count) {
            return [string]$Arguments[$index + 1]
        }
        $prefix = "$Name="
        if ($argument.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            return $argument.Substring($prefix.Length)
        }
    }
    return $null
}

function Resolve-OutputRoot {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )
    $value = Get-OptionValue -Arguments $Arguments -Name "--output"
    if ([string]::IsNullOrWhiteSpace($value)) {
        return [System.IO.Path]::GetFullPath($DefaultOutputRoot)
    }
    if ([System.IO.Path]::IsPathRooted($value)) {
        return [System.IO.Path]::GetFullPath($value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $value))
}

function Resolve-EvaluationDate {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )
    $configured = Get-OptionValue -Arguments $Arguments -Name "--evaluation-date"
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        return $configured
    }
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    return [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow,
        $korea
    ).ToString("yyyy-MM-dd")
}

Set-Location $RepositoryRoot
$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $ProjectPython = "python"
}
$EvaluationDate = Resolve-EvaluationDate -Arguments $PipelineArguments
$OutputRoot = Resolve-OutputRoot -Arguments $PipelineArguments
$Output = Join-Path $OutputRoot "opendart-provisional-earnings"

Write-Host "Refreshing registered SK hynix OpenDART provisional earnings for $EvaluationDate (best effort)."
& $ProjectPython -m alpha_cycle.opendart_provisional_earnings_cli `
    --document-id $DocumentId `
    --evaluation-date $EvaluationDate `
    --output $Output
$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) {
    $exitCode = 1
}
if ($exitCode -ne 0) {
    [Console]::Error.WriteLine(
        "OpenDART provisional-earnings refresh failed with exit code $exitCode; live pipeline will continue and company-level provisional actual evidence will remain unavailable."
    )
}
exit 0
