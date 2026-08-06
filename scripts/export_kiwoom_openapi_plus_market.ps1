[CmdletBinding()]
param(
    [string[]]$Symbols = @("005930", "005935", "000660"),
    [ValidateRange(1, 600)]
    [int]$DailyCount = 120,
    [ValidateRange(30, 900)]
    [int]$TimeoutSeconds = 600,
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Exporter = Join-Path $RepositoryRoot "bridge\kiwoom_openapi_plus\market_export_bootstrap.py"
$QtInitializer = Join-Path $ScriptDirectory "initialize_kiwoom_openapi_plus_qt.ps1"
$DefaultPython = Join-Path $RepositoryRoot ".venv-kiwoom-x86\Scripts\python.exe"
$DefaultOutputRoot = Join-Path $RepositoryRoot "data\private\live-research\kiwoom-openapi-plus-market"

Set-Location $RepositoryRoot
$BridgePython = [Environment]::GetEnvironmentVariable(
    "KIWOOM_OPENAPI_BRIDGE_PYTHON",
    "Process"
)
if ([string]::IsNullOrWhiteSpace($BridgePython)) {
    $BridgePython = [Environment]::GetEnvironmentVariable(
        "KIWOOM_OPENAPI_BRIDGE_PYTHON",
        "User"
    )
}
if ([string]::IsNullOrWhiteSpace($BridgePython)) {
    $BridgePython = $DefaultPython
}
if (-not [System.IO.File]::Exists($BridgePython)) {
    Write-Host "Kiwoom OpenAPI+ x86 bridge is not configured."
    Write-Host "Run: .\scripts\setup_kiwoom_openapi_plus_bridge.cmd -InstallPython"
    exit 2
}
if (-not [System.IO.File]::Exists($Exporter)) {
    throw "Kiwoom read-only market exporter bootstrap is missing."
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = $DefaultOutputRoot
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
    $OutputRoot = Join-Path $RepositoryRoot $OutputRoot
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)

. $QtInitializer -BridgePython $BridgePython
Write-Host "The official Kiwoom login window will open."
Write-Host "This command exports public quotes and adjusted daily-bar evidence."
Write-Host "opt10081 adjustment response fields are preserved for verification."
Write-Host "Account, holdings, balance, and order APIs remain disabled."

$arguments = @("--symbols")
$arguments += $Symbols
$arguments += @(
    "--daily-count",
    $DailyCount.ToString(),
    "--timeout-seconds",
    $TimeoutSeconds.ToString(),
    "--output-root",
    $OutputRoot
)

& $BridgePython $Exporter @arguments
$exportExitCode = $LASTEXITCODE
exit $exportExitCode
