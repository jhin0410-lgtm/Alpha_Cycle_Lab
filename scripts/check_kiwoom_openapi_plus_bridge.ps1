[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Probe = Join-Path $RepositoryRoot "bridge\kiwoom_openapi_plus\probe.py"
$DefaultPython = Join-Path $RepositoryRoot ".venv-kiwoom-x86\Scripts\python.exe"

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

& $BridgePython $Probe --mode environment
exit $LASTEXITCODE
