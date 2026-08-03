[CmdletBinding()]
param(
    [string]$InstallRoot
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
Set-Location $RepositoryRoot

$arguments = @()
if (-not [string]::IsNullOrWhiteSpace($InstallRoot)) {
    $arguments += "--install-root"
    $arguments += $InstallRoot
}

& python -m alpha_cycle.kiwoom_openapi_plus_readiness_cli @arguments
exit $LASTEXITCODE
