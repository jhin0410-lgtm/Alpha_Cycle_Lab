[CmdletBinding()]
param(
    [ValidateRange(1, 600)]
    [int]$DailyCount = 600,
    [ValidateRange(30, 900)]
    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Resolver = Join-Path $ScriptDirectory "resolve_project_python.ps1"
$ValuationHistoryExporter = Join-Path $ScriptDirectory "export_kiwoom_openapi_plus_valuation_history.ps1"
$LatestRunPath = Join-Path $RepositoryRoot "data\private\live-research\latest_run.json"

function Stop-OnFailure {
    param(
        [Parameter(Mandatory = $true)][int]$ExitCode,
        [Parameter(Mandatory = $true)][string]$Stage
    )
    if ($ExitCode -ne 0) {
        [Console]::Error.WriteLine("Historical P/B refresh failed at $Stage (exit $ExitCode).")
        exit $ExitCode
    }
}

Set-Location $RepositoryRoot
if (-not [System.IO.File]::Exists($LatestRunPath)) {
    [Console]::Error.WriteLine(
        "No completed live run is available. Run .\scripts\run_live_pipeline.cmd first."
    )
    exit 2
}
$latestRun = Get-Content $LatestRunPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($latestRun.status -ne "completed" -or [string]::IsNullOrWhiteSpace([string]$latestRun.evaluation_date)) {
    [Console]::Error.WriteLine(
        "The latest live run is not completed. Run .\scripts\run_live_pipeline.cmd first."
    )
    exit 2
}
$evaluationDate = [string]$latestRun.evaluation_date

$ProjectPython = & $Resolver
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ProjectPython)) {
    exit 2
}
$ProjectPython = @($ProjectPython)[-1].ToString().Trim()
$SourceRoot = Join-Path $RepositoryRoot "src"
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $SourceRoot
}
else {
    $env:PYTHONPATH = "$SourceRoot;$($env:PYTHONPATH)"
}

Write-Host "Refreshing historical P/B evidence for live evaluation date $evaluationDate."
Write-Host "Step 1/4: collect fresh Kiwoom unadjusted valuation history."
& powershell.exe `
    -NoProfile `
    -ExecutionPolicy Bypass `
    -File $ValuationHistoryExporter `
    -DailyCount $DailyCount `
    -TimeoutSeconds $TimeoutSeconds
Stop-OnFailure -ExitCode $LASTEXITCODE -Stage "kiwoom_valuation_history"

Write-Host "Step 2/4: capture OpenDART stock-total history for the latest live research snapshot."
& $ProjectPython -m alpha_cycle.opendart_stock_totals_history_cli
Stop-OnFailure -ExitCode $LASTEXITCODE -Stage "opendart_stock_totals_history"

Write-Host "Step 3/4: rebuild source-bounded historical P/B evidence."
& $ProjectPython -m alpha_cycle.historical_pb_cli
Stop-OnFailure -ExitCode $LASTEXITCODE -Stage "historical_pb_build"

Write-Host "Step 4/4: inspect historical P/B readiness."
& $ProjectPython -m alpha_cycle.historical_pb_readiness_cli
Stop-OnFailure -ExitCode $LASTEXITCODE -Stage "historical_pb_readiness"

Write-Host "Historical P/B refresh completed for $evaluationDate."
Write-Host "Re-run .\scripts\run_live_pipeline.cmd to attach the refreshed non-scoring evidence."
exit 0
