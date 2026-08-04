[CmdletBinding()]
param(
    [switch]$NoReport,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PipelineArguments = @()
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
    "BOK_ECOS_API_KEY"
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

$bokEcosKey = [Environment]::GetEnvironmentVariable("BOK_ECOS_API_KEY", "Process")
if ([string]::IsNullOrWhiteSpace($bokEcosKey)) {
    $legacyProcessKey = [Environment]::GetEnvironmentVariable("ECOS_API_KEY", "Process")
    $legacyUserKey = [Environment]::GetEnvironmentVariable("ECOS_API_KEY", "User")
    $legacyKey = if (-not [string]::IsNullOrWhiteSpace($legacyProcessKey)) {
        $legacyProcessKey
    }
    else {
        $legacyUserKey
    }
    if (-not [string]::IsNullOrWhiteSpace($legacyKey)) {
        [Environment]::SetEnvironmentVariable("BOK_ECOS_API_KEY", $legacyKey, "User")
        [Environment]::SetEnvironmentVariable("BOK_ECOS_API_KEY", $legacyKey, "Process")
        $bokEcosKey = $legacyKey
    }
}
if (-not [string]::IsNullOrWhiteSpace($bokEcosKey)) {
    [Environment]::SetEnvironmentVariable("ECOS_API_KEY", $bokEcosKey, "Process")
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

$bokEcosKey = [Environment]::GetEnvironmentVariable("BOK_ECOS_API_KEY", "Process")
if (-not [string]::IsNullOrWhiteSpace($bokEcosKey)) {
    [Environment]::SetEnvironmentVariable("ECOS_API_KEY", $bokEcosKey, "Process")
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
    [Console]::Error.WriteLine(
        "Credential setup did not configure: $($remaining -join ', ')"
    )
    exit 2
}

$ProjectPython = [Environment]::GetEnvironmentVariable(
    "ALPHA_CYCLE_PYTHON",
    "Process"
)
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $ProjectPython = "python"
}

& $ProjectPython -m alpha_cycle.live_pipeline_cli @PipelineArguments
$pipelineExitCode = $LASTEXITCODE

if (Test-Path $StatusPath) {
    $status = Get-Content $StatusPath -Raw -Encoding utf8 | ConvertFrom-Json
    if (
        $status.status -eq "blocked" -and
        $status.reason -eq "tossinvest_ip_allowlist"
    ) {
        Write-Host "TossInvest blocked the current public IP: $($status.public_ip)"
        Write-Host "Attempting fail-closed resume from a fresh linked market/research snapshot."
        & $ProjectPython -m alpha_cycle.resume_pipeline_cli
        $pipelineExitCode = $LASTEXITCODE
        if (Test-Path $StatusPath) {
            $status = Get-Content $StatusPath -Raw -Encoding utf8 | ConvertFrom-Json
        }
    }

    if ($status.status -eq "completed" -and $status.report_path) {
        Write-Host "Live research pipeline completed."
        if ($status.execution_mode -eq "resumed_linked_snapshots") {
            Write-Host "Execution mode: resumed linked snapshots"
            Write-Host "Source evaluation date: $($status.evaluation_date)"
            Write-Host "Market snapshot age: $($status.market_snapshot_age_minutes) minutes"
            if ($status.cross_date_resume) {
                Write-Host "Requested date: $($status.requested_evaluation_date)"
                Write-Host "Market capture date: $($status.market_capture_date)"
            }
        }
        Write-Host "Report: $($status.report_path)"
        if (-not $NoReport) {
            Get-Content $status.report_path -Encoding utf8
        }
    }
    else {
        Write-Host "No completed report is available for this run."
        $status | ConvertTo-Json -Depth 8
    }
}
else {
    [Console]::Error.WriteLine("Pipeline status file was not created: $StatusPath")
    if ($pipelineExitCode -eq 0) {
        $pipelineExitCode = 2
    }
}

exit $pipelineExitCode
