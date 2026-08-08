[CmdletBinding()]
param(
    [string[]]$Symbols = @("005930", "000660"),
    [ValidateRange(1, 120)]
    [int]$Limit = 60,
    [ValidatePattern("^$|^[0-9]{8}$")]
    [string]$ReferenceDate = "",
    [ValidateRange(30, 900)]
    [int]$TimeoutSeconds = 600,
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Exporter = Join-Path $RepositoryRoot "bridge\kiwoom_openapi_plus\investor_flow_export.py"
$QtInitializer = Join-Path $ScriptDirectory "initialize_kiwoom_openapi_plus_qt.ps1"
$DefaultPython = Join-Path $RepositoryRoot ".venv-kiwoom-x86\Scripts\python.exe"
$DefaultOutputRoot = Join-Path $RepositoryRoot "data\private\live-research\kiwoom-openapi-plus-investor-flow"

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
    throw "Kiwoom read-only investor-flow exporter is missing."
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
Write-Host "This probe requests OPT10059 net-buy quantity in single-share units."
Write-Host "No aggregate signal or investment score is produced before live validation."
Write-Host "Account, holdings, balance, and order APIs remain disabled."

$arguments = @("--symbols")
$arguments += $Symbols
$arguments += @(
    "--limit",
    $Limit.ToString(),
    "--timeout-seconds",
    $TimeoutSeconds.ToString(),
    "--output-root",
    $OutputRoot
)
if (-not [string]::IsNullOrWhiteSpace($ReferenceDate)) {
    $arguments += @("--reference-date", $ReferenceDate)
}

& $BridgePython $Exporter @arguments
exit $LASTEXITCODE
