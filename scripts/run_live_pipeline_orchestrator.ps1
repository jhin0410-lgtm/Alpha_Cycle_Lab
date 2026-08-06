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

function Resolve-RepositoryPath {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ([System.IO.Path]::IsPathRooted($Value)) {
        return [System.IO.Path]::GetFullPath($Value)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $Value))
}

function Read-JsonFile {
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

function Test-FalseBooleanProperty {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Name
    )
    $property = $Value.PSObject.Properties[$Name]
    return $null -ne $property -and $property.Value -eq $false
}

function Test-PathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root)
    $separator = [System.IO.Path]::DirectorySeparatorChar
    $trimCharacters = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $rootPrefix = $resolvedRoot.TrimEnd($trimCharacters) + $separator
    return (
        $resolvedPath.Equals(
            $resolvedRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        $resolvedPath.StartsWith(
            $rootPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    )
}

function Test-NewKiwoomExport {
    param(
        [AllowNull()][object]$Before,
        [AllowNull()][object]$After,
        [Parameter(Mandatory = $true)][DateTimeOffset]$StartedAtUtc,
        [Parameter(Mandatory = $true)][string]$ExpectedOutputRoot
    )
    if ($null -eq $After) {
        return $false
    }
    if (
        [string]$After.status -ne "completed" -or
        [string]$After.provider -ne "kiwoom_openapi_plus"
    ) {
        return $false
    }

    $snapshotId = [string]$After.snapshot_id
    if ($snapshotId -notmatch "^[0-9a-f]{64}$") {
        return $false
    }
    if ($null -ne $Before -and [string]$Before.snapshot_id -eq $snapshotId) {
        return $false
    }

    $capturedAtUtc = [DateTimeOffset]::MinValue
    if (
        -not [DateTimeOffset]::TryParse(
            [string]$After.captured_at_utc,
            [ref]$capturedAtUtc
        )
    ) {
        return $false
    }
    if (
        $capturedAtUtc -lt $StartedAtUtc.AddMinutes(-1) -or
        $capturedAtUtc -gt [DateTimeOffset]::UtcNow.AddMinutes(1)
    ) {
        return $false
    }

    $symbols = @(
        $After.symbols |
            ForEach-Object { [string]$_ } |
            Sort-Object
    )
    if (($symbols -join ",") -ne "000660,005930,005935") {
        return $false
    }
    if (
        -not (Test-FalseBooleanProperty -Value $After -Name "account_api_enabled") -or
        -not (Test-FalseBooleanProperty -Value $After -Name "order_api_enabled")
    ) {
        return $false
    }

    try {
        $exportDirectory = Resolve-RepositoryPath -Value ([string]$After.export_directory)
        $manifestPath = Resolve-RepositoryPath -Value ([string]$After.manifest_path)
    }
    catch {
        return $false
    }
    if (
        -not (Test-PathWithinRoot -Path $exportDirectory -Root $ExpectedOutputRoot) -or
        -not (Test-PathWithinRoot -Path $manifestPath -Root $exportDirectory) -or
        -not [System.IO.Directory]::Exists($exportDirectory) -or
        -not [System.IO.File]::Exists($manifestPath)
    ) {
        return $false
    }

    $manifest = Read-JsonFile -Path $manifestPath
    if (
        $null -eq $manifest -or
        [string]$manifest.status -ne "completed" -or
        [string]$manifest.provider -ne "kiwoom_openapi_plus" -or
        [string]$manifest.snapshot_id -ne $snapshotId -or
        -not (Test-FalseBooleanProperty -Value $manifest -Name "account_api_enabled") -or
        -not (Test-FalseBooleanProperty -Value $manifest -Name "order_api_enabled")
    ) {
        return $false
    }

    $quotePath = Join-Path $exportDirectory ([string]$manifest.quotes_file)
    $dailyBarsPath = Join-Path $exportDirectory ([string]$manifest.daily_bars_file)
    if (
        -not (Test-PathWithinRoot -Path $quotePath -Root $exportDirectory) -or
        -not (Test-PathWithinRoot -Path $dailyBarsPath -Root $exportDirectory) -or
        -not [System.IO.File]::Exists($quotePath) -or
        -not [System.IO.File]::Exists($dailyBarsPath)
    ) {
        return $false
    }
    return $true
}

Set-Location $RepositoryRoot
$OutputRoot = Resolve-OutputRoot -Arguments $PipelineArguments
$StatusPath = Join-Path $OutputRoot "latest_run.json"
$KiwoomOutputRoot = Join-Path $OutputRoot "kiwoom-openapi-plus-market"
$KiwoomPointerPath = Join-Path $KiwoomOutputRoot "latest_market_export.json"
$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $ProjectPython = "python"
}

& $LivePipeline -NoReport @PipelineArguments
$exitCode = $LASTEXITCODE
$status = Read-JsonFile -Path $StatusPath
$shouldFallback = $false
if ($null -ne $status) {
    $shouldFallback = (
        $status.reason -eq "tossinvest_ip_allowlist" -or
        $status.reason -eq "resume_unavailable"
    )
}

if ($exitCode -ne 0 -and $shouldFallback) {
    Write-Host "TossInvest is unavailable from this IP. Collecting fresh Kiwoom read-only market evidence."
    $pointerBefore = Read-JsonFile -Path $KiwoomPointerPath
    $exportStartedAtUtc = [DateTimeOffset]::UtcNow
    & $KiwoomExporter `
        -DailyCount 120 `
        -TimeoutSeconds 600 `
        -OutputRoot $KiwoomOutputRoot
    $kiwoomExitCode = $LASTEXITCODE
    if ($null -eq $kiwoomExitCode) {
        $kiwoomExitCode = 1
    }
    $pointerAfter = Read-JsonFile -Path $KiwoomPointerPath
    $freshKiwoomExport = Test-NewKiwoomExport `
        -Before $pointerBefore `
        -After $pointerAfter `
        -StartedAtUtc $exportStartedAtUtc `
        -ExpectedOutputRoot $KiwoomOutputRoot

    if (-not $freshKiwoomExport) {
        [Console]::Error.WriteLine(
            "Kiwoom read-only market export did not publish a new valid evidence bundle; no single-provider decision was published."
        )
        if ($kiwoomExitCode -ne 0) {
            exit $kiwoomExitCode
        }
        exit 3
    }
    if ($kiwoomExitCode -ne 0) {
        [Console]::Error.WriteLine(
            "Kiwoom exporter returned exit code $kiwoomExitCode after publishing a new valid evidence bundle. Continuing through downstream provenance validation."
        )
    }

    Write-Host "Running the research pipeline in explicit Kiwoom-primary-only mode."
    & $ProjectPython -m alpha_cycle.kiwoom_primary_pipeline_cli @PipelineArguments
    $exitCode = $LASTEXITCODE
    $status = Read-JsonFile -Path $StatusPath
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
