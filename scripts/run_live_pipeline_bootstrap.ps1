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
$Pipeline = Join-Path $ScriptDirectory "run_live_pipeline_orchestrator.ps1"
$MacroLiquidityRefresh = Join-Path $ScriptDirectory "refresh_macro_liquidity.ps1"
$OfficialIrRefresh = Join-Path $ScriptDirectory "refresh_official_semiconductor_ir.ps1"
$ProvisionalEarningsRefresh = Join-Path $ScriptDirectory "refresh_opendart_provisional_earnings.ps1"
$SourceRoot = Join-Path $RepositoryRoot "src"

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
& $MacroLiquidityRefresh @PipelineArguments
& $OfficialIrRefresh @PipelineArguments
& $ProvisionalEarningsRefresh @PipelineArguments
& $Pipeline @PipelineArguments
exit $LASTEXITCODE
