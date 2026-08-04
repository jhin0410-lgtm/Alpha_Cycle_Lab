[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$InstallPython
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$BridgeRoot = Join-Path $RepositoryRoot "bridge\kiwoom_openapi_plus"
$Requirements = Join-Path $BridgeRoot "requirements-win32.txt"
$Probe = Join-Path $BridgeRoot "probe.py"
$QtInitializer = Join-Path $ScriptDirectory "initialize_kiwoom_openapi_plus_qt.ps1"
$VenvRoot = Join-Path $RepositoryRoot ".venv-kiwoom-x86"
$VenvPython = Join-Path $VenvRoot "Scripts\python.exe"

function Test-X86Python {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (-not [System.IO.File]::Exists($PythonPath)) {
        return $false
    }
    $result = & $PythonPath -c "import struct; print(struct.calcsize('P') * 8)" 2>$null
    return $LASTEXITCODE -eq 0 -and ($result | Select-Object -Last 1) -eq "32"
}

function Find-X86Python {
    $configured = [Environment]::GetEnvironmentVariable(
        "KIWOOM_OPENAPI_PYTHON32",
        "User"
    )
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        if (Test-X86Python -PythonPath $configured) {
            return [System.IO.Path]::GetFullPath($configured)
        }
    }

    $processConfigured = [Environment]::GetEnvironmentVariable(
        "KIWOOM_OPENAPI_PYTHON32",
        "Process"
    )
    if (-not [string]::IsNullOrWhiteSpace($processConfigured)) {
        if (Test-X86Python -PythonPath $processConfigured) {
            return [System.IO.Path]::GetFullPath($processConfigured)
        }
    }

    $selectors = @("-3.12-32", "-3.11-32", "-3.10-32")
    foreach ($selector in $selectors) {
        try {
            $candidate = & py $selector -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $path = $candidate | Select-Object -Last 1
                if (Test-X86Python -PythonPath $path) {
                    return [System.IO.Path]::GetFullPath($path)
                }
            }
        }
        catch {
            continue
        }
    }
    return $null
}

function Install-X86Python {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "winget is unavailable; install official Python 3.12 x86 manually."
    }
    & winget install `
        --id Python.Python.3.12 `
        --exact `
        --architecture x86 `
        --scope user `
        --accept-package-agreements `
        --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "The official Python 3.12 x86 installation command failed."
    }
}

Set-Location $RepositoryRoot
$BasePython = Find-X86Python
if (-not $BasePython -and $InstallPython) {
    Install-X86Python
    $BasePython = Find-X86Python
}
if (-not $BasePython) {
    Write-Host "A separate 32-bit Python runtime is required for KHOpenAPI.ocx."
    Write-Host "Run this command to install and configure it automatically:"
    Write-Host ".\scripts\setup_kiwoom_openapi_plus_bridge.cmd -InstallPython"
    exit 2
}

if ($Force -and [System.IO.Directory]::Exists($VenvRoot)) {
    Remove-Item -Recurse -Force $VenvRoot
}
if (-not [System.IO.File]::Exists($VenvPython)) {
    & $BasePython -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the isolated x86 bridge environment."
    }
}
if (-not (Test-X86Python -PythonPath $VenvPython)) {
    throw "The bridge virtual environment is not using 32-bit Python."
}

& $VenvPython -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to update pip in the x86 bridge environment."
}
& $VenvPython -m pip install `
    --disable-pip-version-check `
    --requirement $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install the pinned x86 PyQt5 bridge dependencies."
}

. $QtInitializer -BridgePython $VenvPython
& $VenvPython $Probe --mode environment
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

[Environment]::SetEnvironmentVariable(
    "KIWOOM_OPENAPI_BRIDGE_PYTHON",
    $VenvPython,
    "User"
)
[Environment]::SetEnvironmentVariable(
    "KIWOOM_OPENAPI_BRIDGE_PYTHON",
    $VenvPython,
    "Process"
)

Write-Host "Kiwoom OpenAPI+ x86 bridge environment is configured."
Write-Host "Main Alpha Cycle Lab Python remains unchanged."
Write-Host "Account and order APIs remain disabled."
