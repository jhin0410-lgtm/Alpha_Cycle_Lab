[CmdletBinding()]
param(
    [switch]$NoReport,
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyCollection()]
    [string[]]$PipelineArguments = @()
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$SetupScript = Join-Path $ScriptDirectory "setup_local_credentials.ps1"
$DefaultOutputRoot = Join-Path $RepositoryRoot "data/private/live-research"
$RequiredVariables = @(
    "TOSSINVEST_CLIENT_ID",
    "TOSSINVEST_CLIENT_SECRET",
    "OPENDART_API_KEY",
    "BOK_ECOS_API_KEY"
)

function Get-PipelineOptionValue {
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

function New-ResumeArguments {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )

    $result = [System.Collections.Generic.List[string]]::new()
    foreach ($option in @(
        "--evaluation-date",
        "--output",
        "--history-years",
        "--timeout-seconds",
        "--max-retries"
    )) {
        $value = Get-PipelineOptionValue -Arguments $Arguments -OptionName $option
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $result.Add($option)
            $result.Add($value)
        }
    }
    return [string[]]$result.ToArray()
}

function Resolve-OutputRoot {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )

    $configured = Get-PipelineOptionValue -Arguments $Arguments -OptionName "--output"
    if ([string]::IsNullOrWhiteSpace($configured)) {
        return [System.IO.Path]::GetFullPath($DefaultOutputRoot)
    }
    if ([System.IO.Path]::IsPathRooted($configured)) {
        return [System.IO.Path]::GetFullPath($configured)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $configured))
}

function Get-StatusWriteTicks {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not [System.IO.File]::Exists($Path)) {
        return [long]-1
    }
    return (Get-Item -LiteralPath $Path).LastWriteTimeUtc.Ticks
}

function Test-CurrentStatusFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][long]$PreviousTicks
    )

    if (-not [System.IO.File]::Exists($Path)) {
        return $false
    }
    return (Get-StatusWriteTicks -Path $Path) -ne $PreviousTicks
}

Set-Location $RepositoryRoot
$OutputRoot = Resolve-OutputRoot -Arguments $PipelineArguments
$StatusPath = Join-Path $OutputRoot "latest_run.json"
$ResumeArguments = New-ResumeArguments -Arguments $PipelineArguments

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

$statusTicksBefore = Get-StatusWriteTicks -Path $StatusPath
& $ProjectPython -m alpha_cycle.live_pipeline_provenance_cli @PipelineArguments
$pipelineExitCode = $LASTEXITCODE
$statusIsCurrent = Test-CurrentStatusFile `
    -Path $StatusPath `
    -PreviousTicks $statusTicksBefore

if ($statusIsCurrent) {
    $status = Get-Content $StatusPath -Raw -Encoding utf8 | ConvertFrom-Json
    if (
        $status.status -eq "blocked" -and
        $status.reason -eq "tossinvest_ip_allowlist"
    ) {
        Write-Host "TossInvest blocked the current public IP: $($status.public_ip)"
        Write-Host "Attempting fail-closed resume from a fresh linked market/research snapshot."
        $resumeTicksBefore = Get-StatusWriteTicks -Path $StatusPath
        & $ProjectPython -m alpha_cycle.resume_pipeline_provenance_cli @ResumeArguments
        $pipelineExitCode = $LASTEXITCODE
        if (
            Test-CurrentStatusFile `
                -Path $StatusPath `
                -PreviousTicks $resumeTicksBefore
        ) {
            $status = Get-Content $StatusPath -Raw -Encoding utf8 | ConvertFrom-Json
        }
        else {
            [Console]::Error.WriteLine(
                "Resume did not create a current status file: $StatusPath"
            )
            if ($pipelineExitCode -eq 0) {
                $pipelineExitCode = 2
            }
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
        Write-Host "Market provenance: $($status.market_provenance_status)"
        Write-Host "Reference price cross-provider certified: $($status.reference_price_cross_provider_certified)"
        Write-Host "Decision evidence envelope: $($status.decision_evidence_envelope_path)"
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
    [Console]::Error.WriteLine(
        "Pipeline did not create a current status file: $StatusPath"
    )
    if ($pipelineExitCode -eq 0) {
        $pipelineExitCode = 2
    }
}

exit $pipelineExitCode
