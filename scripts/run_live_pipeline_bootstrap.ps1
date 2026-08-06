[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [AllowEmptyCollection()]
    [string[]]$PipelineArguments = @()
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Resolver = Join-Path $ScriptDirectory "resolve_project_python.ps1"
$Pipeline = Join-Path $ScriptDirectory "run_live_pipeline.ps1"
$KiwoomFailover = Join-Path $ScriptDirectory "run_kiwoom_primary_failover.ps1"
$SourceRoot = Join-Path $RepositoryRoot "src"
$DefaultOutputRoot = Join-Path $RepositoryRoot "data/private/live-research"

function Get-OptionValue {
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

function Resolve-OutputRoot {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Arguments
    )

    $configured = Get-OptionValue -Arguments $Arguments -OptionName "--output"
    if ([string]::IsNullOrWhiteSpace($configured)) {
        return [System.IO.Path]::GetFullPath($DefaultOutputRoot)
    }
    if ([System.IO.Path]::IsPathRooted($configured)) {
        return [System.IO.Path]::GetFullPath($configured)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $configured))
}

$ProjectPython = & $Resolver
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ProjectPython)) {
    exit 2
}
$ProjectPython = @($ProjectPython)[-1].ToString().Trim()
$ProjectPythonDirectory = Split-Path -Parent $ProjectPython

$env:PATH = "$ProjectPythonDirectory;$($env:PATH)"
$env:ALPHA_CYCLE_PYTHON = $ProjectPython
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $SourceRoot
}
else {
    $env:PYTHONPATH = "$SourceRoot;$($env:PYTHONPATH)"
}

Set-Location $RepositoryRoot
& $Pipeline @PipelineArguments
$pipelineExitCode = $LASTEXITCODE
if ($pipelineExitCode -eq 0) {
    exit 0
}

$OutputRoot = Resolve-OutputRoot -Arguments $PipelineArguments
$StatusPath = Join-Path $OutputRoot "latest_run.json"
if (-not [System.IO.File]::Exists($StatusPath)) {
    exit $pipelineExitCode
}

try {
    $status = Get-Content -LiteralPath $StatusPath -Raw -Encoding utf8 | ConvertFrom-Json
}
catch {
    exit $pipelineExitCode
}

if ($status.reason -ne "resume_unavailable") {
    exit $pipelineExitCode
}
if (-not [System.IO.File]::Exists($KiwoomFailover)) {
    exit $pipelineExitCode
}

& $KiwoomFailover -ProjectPython $ProjectPython @PipelineArguments
exit $LASTEXITCODE
