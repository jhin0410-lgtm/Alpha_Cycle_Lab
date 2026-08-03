[CmdletBinding()]
param(
    [switch]$Mock,
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$SetupScript = Join-Path $ScriptDirectory "setup_kiwoom_rest.ps1"
$PathVariables = @(
    "KIWOOM_REST_APP_KEY_FILE",
    "KIWOOM_REST_APP_SECRET_FILE"
)

Set-Location $RepositoryRoot

foreach ($name in $PathVariables) {
    $processValue = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($processValue)) {
        $userValue = [Environment]::GetEnvironmentVariable($name, "User")
        if (-not [string]::IsNullOrWhiteSpace($userValue)) {
            [Environment]::SetEnvironmentVariable($name, $userValue, "Process")
        }
    }
}

$missing = @(
    foreach ($name in $PathVariables) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrWhiteSpace($value) -or -not [System.IO.File]::Exists($value)) {
            $name
        }
    }
)

if ($missing.Count -gt 0) {
    Write-Host "Kiwoom REST local text-file paths require one-time setup."
    & $SetupScript
}

$arguments = @()
if ($Mock) {
    $arguments += "--mock"
}
if ($Offline) {
    $arguments += "--offline"
}

& python -m alpha_cycle.kiwoom_readiness_cli @arguments
exit $LASTEXITCODE
