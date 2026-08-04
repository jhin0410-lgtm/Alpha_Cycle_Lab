[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$InstallPython
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Resolver = Join-Path $ScriptDirectory "resolve_project_python.ps1"
$VirtualEnvironmentRoot = Join-Path $RepositoryRoot ".venv"
$VirtualEnvironmentPython = Join-Path $VirtualEnvironmentRoot "Scripts\python.exe"

function Test-X64ProjectPython {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (-not [System.IO.File]::Exists($PythonPath)) {
        return $false
    }
    try {
        $probe = & $PythonPath -c @"
import struct
import sys
print(f"{struct.calcsize('P') * 8}|{sys.version_info.major}|{sys.version_info.minor}|{sys.executable}")
"@ 2>$null
    }
    catch {
        return $false
    }
    if ($LASTEXITCODE -ne 0 -or $null -eq $probe) {
        return $false
    }
    $parts = @($probe)[-1].ToString().Trim().Split("|", 4)
    if ($parts.Count -ne 4) {
        return $false
    }
    $bitness = 0
    $major = 0
    $minor = 0
    if (
        -not [int]::TryParse($parts[0], [ref]$bitness) -or
        -not [int]::TryParse($parts[1], [ref]$major) -or
        -not [int]::TryParse($parts[2], [ref]$minor)
    ) {
        return $false
    }
    if ($bitness -ne 64) {
        return $false
    }
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 12)) {
        return $false
    }
    $resolved = $parts[3].Trim()
    return (
        -not [string]::IsNullOrWhiteSpace($resolved) -and
        $resolved -notlike "*.venv-kiwoom-x86*"
    )
}

function Resolve-X64ProjectPython {
    try {
        $resolved = & $Resolver 2>$null
    }
    catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or $null -eq $resolved) {
        return $null
    }
    $path = @($resolved)[-1].ToString().Trim()
    if (Test-X64ProjectPython -PythonPath $path) {
        return [System.IO.Path]::GetFullPath($path)
    }
    return $null
}

function Wait-X64ProjectPython {
    param(
        [ValidateRange(1, 60)]
        [int]$Attempts = 20,
        [ValidateRange(1, 10)]
        [int]$DelaySeconds = 1
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $resolved = Resolve-X64ProjectPython
        if (-not [string]::IsNullOrWhiteSpace($resolved)) {
            return $resolved
        }
        if ($attempt -lt $Attempts) {
            Start-Sleep -Seconds $DelaySeconds
        }
    }
    return $null
}

function Install-X64Python {
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        throw "winget is unavailable; install official Python 3.12 x64 manually."
    }

    Write-Host "Installing official Python 3.12 x64 for the main Alpha Cycle Lab environment..."
    & $winget.Source install `
        --id Python.Python.3.12 `
        --exact `
        --architecture x64 `
        --scope user `
        --force `
        --accept-package-agreements `
        --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "The official Python 3.12 x64 installation command failed."
    }
}

Set-Location $RepositoryRoot
$BasePython = Resolve-X64ProjectPython
if (-not $BasePython -and $InstallPython) {
    Install-X64Python
    Write-Host "Waiting for the new x64 Python registration to become visible..."
    $BasePython = Wait-X64ProjectPython
}
if (-not $BasePython) {
    Write-Host "A separate 64-bit Python 3.12+ runtime is required for Alpha Cycle Lab."
    Write-Host "The Kiwoom OpenAPI+ x86 bridge Python cannot be used for analysis."
    Write-Host "Run this command to install and configure it automatically:"
    Write-Host ".\scripts\setup_project_python.cmd -InstallPython"
    exit 2
}

Write-Host "Using main x64 Python: $BasePython"
if ($Force -and [System.IO.Directory]::Exists($VirtualEnvironmentRoot)) {
    Remove-Item -Recurse -Force $VirtualEnvironmentRoot
}
if (-not [System.IO.File]::Exists($VirtualEnvironmentPython)) {
    Write-Host "Creating the main project virtual environment..."
    & $BasePython -m venv $VirtualEnvironmentRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the main project virtual environment."
    }
}
if (-not (Test-X64ProjectPython -PythonPath $VirtualEnvironmentPython)) {
    throw "The main project virtual environment is not using 64-bit Python 3.12+."
}

Write-Host "Updating pip in the main project environment..."
& $VirtualEnvironmentPython -m pip install `
    --disable-pip-version-check `
    --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to update pip in the main project environment."
}

Write-Host "Installing Alpha Cycle Lab and development dependencies..."
& $VirtualEnvironmentPython -m pip install `
    --disable-pip-version-check `
    --editable ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Alpha Cycle Lab dependencies."
}

$verification = & $VirtualEnvironmentPython -c @"
import struct
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import alpha_cycle
import numpy
import pandas
import yaml

assert struct.calcsize('P') * 8 == 64
assert datetime(2026, 1, 1, tzinfo=ZoneInfo('Asia/Seoul')).utcoffset() is not None
print('PROJECT PYTHON: PASS')
print(f"Python bitness: {struct.calcsize('P') * 8}")
print(f"NumPy: {numpy.__version__}")
print(f"pandas: {pandas.__version__}")
print(f"PyYAML: {yaml.__version__}")
print(f"Python executable: {sys.executable}")
"@
if ($LASTEXITCODE -ne 0) {
    throw "The main project environment verification failed."
}
$verification | ForEach-Object { Write-Host $_ }

[Environment]::SetEnvironmentVariable(
    "ALPHA_CYCLE_PYTHON",
    $VirtualEnvironmentPython,
    "User"
)
[Environment]::SetEnvironmentVariable(
    "ALPHA_CYCLE_PYTHON",
    $VirtualEnvironmentPython,
    "Process"
)

Write-Host "Alpha Cycle Lab main project environment is configured."
Write-Host "Main project Python: $VirtualEnvironmentPython"
Write-Host "Kiwoom bridge Python remains isolated in .venv-kiwoom-x86."
Write-Host "Account and order APIs remain disabled."
