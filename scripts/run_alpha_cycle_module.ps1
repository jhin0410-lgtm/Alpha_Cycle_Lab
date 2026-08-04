[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9_.]+$")]
    [string]$Module,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ModuleArguments = @()
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Resolver = Join-Path $ScriptDirectory "resolve_project_python.ps1"
$SourceRoot = Join-Path $RepositoryRoot "src"

$ProjectPython = & $Resolver
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ProjectPython)) {
    exit 2
}
$ProjectPython = @($ProjectPython)[-1].ToString().Trim()

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $SourceRoot
}
else {
    $env:PYTHONPATH = "$SourceRoot;$($env:PYTHONPATH)"
}
$env:ALPHA_CYCLE_PYTHON = $ProjectPython

Set-Location $RepositoryRoot
& $ProjectPython -m $Module @ModuleArguments
exit $LASTEXITCODE
