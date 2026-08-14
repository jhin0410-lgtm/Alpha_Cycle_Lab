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
$RefreshOutput = Join-Path $OutputRoot "official-semiconductor-ir-refresh"
$DocumentOutput = Join-Path $OutputRoot "official-semiconductor-ir-documents"
$BaselineOutput = Join-Path $OutputRoot "semiconductor-baseline-reconciliation"
$ForwardOutput = Join-Path $OutputRoot "semiconductor-forward-input-evidence"
$AccountingOutput = Join-Path $OutputRoot "semiconductor-accounting-identity"
$Timeout = Get-OptionValue -Arguments $PipelineArguments -Name "--timeout-seconds"
if ([string]::IsNullOrWhiteSpace($Timeout)) {
    $Timeout = "20"
}

Write-Host "Refreshing registered official semiconductor IR evidence for $EvaluationDate (best effort)."
& $ProjectPython -m alpha_cycle.official_semiconductor_ir_refresh_cli `
    --evaluation-date $EvaluationDate `
    --output $RefreshOutput `
    --document-output $DocumentOutput `
    --baseline-output $BaselineOutput `
    --forward-output $ForwardOutput `
    --accounting-output $AccountingOutput `
    --timeout-seconds $Timeout
$exitCode = $LASTEXITCODE
if ($null -eq $exitCode) {
    $exitCode = 1
}
if ($exitCode -ne 0) {
    [Console]::Error.WriteLine(
        "Official semiconductor IR refresh failed with exit code $exitCode; live pipeline will continue without treating stale official IR evidence as current."
    )
}
exit 0
