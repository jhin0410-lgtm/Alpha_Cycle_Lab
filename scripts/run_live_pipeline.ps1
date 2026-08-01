[CmdletBinding()]
param(
    [switch]$NoReport
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$SetupScript = Join-Path $ScriptDirectory "setup_local_credentials.ps1"
$StatusPath = Join-Path $RepositoryRoot "data/private/live-research/latest_run.json"
$RequiredVariables = @(
    "TOSSINVEST_CLIENT_ID",
    "TOSSINVEST_CLIENT_SECRET",
    "OPENDART_API_KEY",
    "ECOS_API_KEY"
)

Set-Location $RepositoryRoot

foreach ($name in $RequiredVariables) {
    $processValue = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($processValue)) {
        $userValue = [Environment]::GetEnvironmentVariable($name, "User")
        if (-not [string]::IsNullOrWhiteSpace($userValue)) {
            [Environment]::SetEnvironmentVariable($name, $userValue, "Process")
        }
    }
}

$missing = @(
    foreach ($name in $RequiredVariables) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrWhiteSpace($value)) {
            $name
        }
    }
)

if ($missing.Count -gt 0) {
    Write-Host "Missing local API credentials: $($missing -join ', ')"
    Write-Host "Starting secure one-time credential setup. Values will not be printed or committed."
    & $SetupScript
}

$remaining = @(
    foreach ($name in $RequiredVariables) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrWhiteSpace($value)) {
            $name
        }
    }
)
if ($remaining.Count -gt 0) {
    Write-Error "Credential setup did not configure: $($remaining -join ', ')"
    exit 2
}

& python -m alpha_cycle.live_pipeline_cli @args
$pipelineExitCode = $LASTEXITCODE

if (Test-Path $StatusPath) {
    $status = Get-Content $StatusPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($status.status -eq "completed" -and $status.report_path) {
        Write-Host "Live research pipeline completed."
        Write-Host "Report: $($status.report_path)"
        if (-not $NoReport) {
            Get-Content $status.report_path -Encoding utf8
        }
    }
    else {
        $status | ConvertTo-Json -Depth 8
    }
}
else {
    Write-Error "Pipeline status file was not created: $StatusPath"
    if ($pipelineExitCode -eq 0) {
        $pipelineExitCode = 2
    }
}

exit $pipelineExitCode
