[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyCollection()]
    [string[]]$PipelineArguments = @()
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$LivePipeline = Join-Path $ScriptDirectory "run_live_pipeline.ps1"
$KiwoomExporter = Join-Path $ScriptDirectory "export_kiwoom_openapi_plus_market.ps1"
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

function Read-Status {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not [System.IO.File]::Exists($Path)) {
        return $null
    }
    try {
        return Get-Content $Path -Raw -Encoding utf8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

Set-Location $RepositoryRoot
$OutputRoot = Resolve-OutputRoot -Arguments $PipelineArguments
$StatusPath = Join-Path $OutputRoot "latest_run.json"
$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $ProjectPython = "python"
}

& $LivePipeline -NoReport @PipelineArguments
$exitCode = $LASTEXITCODE
$status = Read-Status -Path $StatusPath
$shouldFallback = $false
if ($null -ne $status) {
    $shouldFallback = (
        $status.reason -eq "tossinvest_ip_allowlist" -or
        $status.reason -eq "resume_unavailable"
    )
}

if ($exitCode -ne 0 -and $shouldFallback) {
    Write-Host "TossInvest is unavailable from this IP. Collecting fresh Kiwoom read-only market evidence."
    & $KiwoomExporter -DailyCount 120 -TimeoutSeconds 600
    $kiwoomExitCode = $LASTEXITCODE
    if ($kiwoomExitCode -ne 0) {
        [Console]::Error.WriteLine(
            "Kiwoom read-only market export failed; no single-provider decision was published."
        )
        exit $kiwoomExitCode
    }

    Write-Host "Running the research pipeline in explicit Kiwoom-primary-only mode."
    & $ProjectPython -m alpha_cycle.kiwoom_primary_pipeline_cli @PipelineArguments
    $exitCode = $LASTEXITCODE
    $status = Read-Status -Path $StatusPath
}

if ($null -ne $status -and $status.status -eq "completed" -and $status.report_path) {
    Write-Host "Live research pipeline completed."
    Write-Host "Market provenance: $($status.market_provenance_status)"
    Write-Host "Reference price cross-provider certified: $($status.reference_price_cross_provider_certified)"
    Write-Host "Decision evidence envelope: $($status.decision_evidence_envelope_path)"
    Write-Host "Report: $($status.report_path)"
    Get-Content $status.report_path -Encoding utf8
}
elseif ($null -ne $status) {
    Write-Host "No completed report is available for this run."
    $status | ConvertTo-Json -Depth 8
}

exit $exitCode
