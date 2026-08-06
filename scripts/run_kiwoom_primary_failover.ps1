[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ProjectPython,
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyCollection()]
    [string[]]$PipelineArguments = @()
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultOutputRoot = Join-Path $RepositoryRoot "data/private/live-research"
$Exporter = Join-Path $ScriptDirectory "export_kiwoom_openapi_plus_market.ps1"
$Pipeline = Join-Path $ScriptDirectory "run_live_pipeline.ps1"

function Get-OptionValue {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$OptionName
    )

    $value = $null
    for ($index = 0; $index -lt $Arguments.Count; $index++) {
        $argument = [string]$Arguments[$index]
        if ($argument -eq $OptionName) {
            if ($index + 1 -ge $Arguments.Count) {
                throw "$OptionName requires a value"
            }
            $value = [string]$Arguments[$index + 1]
            $index++
            continue
        }
        $prefix = "$OptionName="
        if ($argument.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $value = $argument.Substring($prefix.Length)
        }
    }
    return $value
}

function Resolve-OutputRoot {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )

    $configured = Get-OptionValue -Arguments $Arguments -OptionName "--output"
    if ([string]::IsNullOrWhiteSpace($configured)) {
        return [System.IO.Path]::GetFullPath($DefaultOutputRoot)
    }
    if ([System.IO.Path]::IsPathRooted($configured)) {
        return [System.IO.Path]::GetFullPath($configured)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $configured))
}

function Resolve-CandleCount {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )

    $configured = Get-OptionValue -Arguments $Arguments -OptionName "--candle-count"
    if ([string]::IsNullOrWhiteSpace($configured)) {
        return 100
    }
    $value = 0
    if (-not [int]::TryParse($configured, [ref]$value)) {
        throw "--candle-count must be an integer"
    }
    if ($value -lt 1 -or $value -gt 200) {
        throw "--candle-count must be between 1 and 200"
    }
    return $value
}

function Write-FailoverStatus {
    param(
        [Parameter(Mandatory = $true)][string]$OutputRoot,
        [Parameter(Mandatory = $true)][string]$Reason,
        [Parameter(Mandatory = $true)][string]$ErrorMessage
    )

    [System.IO.Directory]::CreateDirectory($OutputRoot) | Out-Null
    $destination = Join-Path $OutputRoot "latest_run.json"
    $temporary = Join-Path $OutputRoot ".latest_run.kiwoom-failover.tmp"
    $payload = [ordered]@{
        status = "failed"
        stage = "kiwoom_primary_market"
        reason = $Reason
        error = $ErrorMessage
        next_action = "Resolve the Kiwoom read-only login/export error and rerun the same command."
        rerun_command = ".\scripts\run_live_pipeline.cmd"
        outputs_available = $false
        read_only_market_failover_used = $false
        automatic_provider_substitution_enabled = $false
        account_api_enabled = $false
        order_api_enabled = $false
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $destination -Force
}

Set-Location $RepositoryRoot
$OutputRoot = Resolve-OutputRoot -Arguments $PipelineArguments
$CandleCount = Resolve-CandleCount -Arguments $PipelineArguments
$KiwoomOutputRoot = Join-Path $OutputRoot "kiwoom-openapi-plus-market"
$PrimaryPointer = Join-Path $OutputRoot "latest_kiwoom_primary_market.json"

Write-Host "No fresh linked TossInvest snapshot is available."
Write-Host "Starting explicit read-only Kiwoom market failover."
Write-Host "The official Kiwoom login window may require the normal login action."
Write-Host "Account, holdings, balance, and order APIs remain disabled."

& $Exporter `
    -DailyCount $CandleCount `
    -TimeoutSeconds 600 `
    -OutputRoot $KiwoomOutputRoot
$exportExitCode = $LASTEXITCODE
if ($exportExitCode -ne 0) {
    Write-FailoverStatus `
        -OutputRoot $OutputRoot `
        -Reason "kiwoom_export_failed" `
        -ErrorMessage "Kiwoom read-only market export exited with code $exportExitCode."
    exit $exportExitCode
}

& $ProjectPython -m alpha_cycle.kiwoom_primary_market_cli `
    --output-root $OutputRoot `
    --candle-count $CandleCount `
    --max-age-minutes 30 `
    --fallback-reason tossinvest_ip_allowlist
$conversionExitCode = $LASTEXITCODE
if ($conversionExitCode -ne 0 -or -not [System.IO.File]::Exists($PrimaryPointer)) {
    Write-FailoverStatus `
        -OutputRoot $OutputRoot `
        -Reason "kiwoom_primary_conversion_failed" `
        -ErrorMessage "Kiwoom export could not be converted into a primary market snapshot."
    exit 2
}

$primary = Get-Content -LiteralPath $PrimaryPointer -Raw -Encoding utf8 | ConvertFrom-Json
if (
    $primary.status -ne "completed" -or
    [string]::IsNullOrWhiteSpace([string]$primary.market_directory)
) {
    Write-FailoverStatus `
        -OutputRoot $OutputRoot `
        -Reason "kiwoom_primary_pointer_invalid" `
        -ErrorMessage "The Kiwoom primary market pointer is incomplete."
    exit 2
}

$previousSnapshot = [Environment]::GetEnvironmentVariable(
    "ALPHA_CYCLE_PRIMARY_MARKET_SNAPSHOT",
    "Process"
)
$previousReason = [Environment]::GetEnvironmentVariable(
    "ALPHA_CYCLE_PRIMARY_MARKET_REASON",
    "Process"
)
[Environment]::SetEnvironmentVariable(
    "ALPHA_CYCLE_PRIMARY_MARKET_SNAPSHOT",
    [string]$primary.market_directory,
    "Process"
)
[Environment]::SetEnvironmentVariable(
    "ALPHA_CYCLE_PRIMARY_MARKET_REASON",
    "tossinvest_ip_allowlist",
    "Process"
)
try {
    Write-Host "Kiwoom read-only market snapshot is ready. Continuing the same pipeline."
    & $Pipeline @PipelineArguments
    exit $LASTEXITCODE
}
finally {
    [Environment]::SetEnvironmentVariable(
        "ALPHA_CYCLE_PRIMARY_MARKET_SNAPSHOT",
        $previousSnapshot,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "ALPHA_CYCLE_PRIMARY_MARKET_REASON",
        $previousReason,
        "Process"
    )
}
