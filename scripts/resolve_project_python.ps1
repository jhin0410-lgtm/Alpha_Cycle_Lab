[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$MinimumMajor = 3
$MinimumMinor = 12

function New-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [string[]]$PrefixArguments = @()
    )

    return [pscustomobject]@{
        Executable = $Executable
        PrefixArguments = $PrefixArguments
    }
}

function Test-ProjectPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [string[]]$PrefixArguments = @()
    )

    try {
        $probe = & $Executable @PrefixArguments -c @"
import struct
import sys
print(f"{struct.calcsize('P') * 8}|{sys.version_info.major}|{sys.version_info.minor}|{sys.executable}")
"@ 2>$null
    }
    catch {
        return $null
    }
    if ($LASTEXITCODE -ne 0 -or $null -eq $probe) {
        return $null
    }

    $line = @($probe)[-1].ToString().Trim()
    $parts = $line.Split("|", 4)
    if ($parts.Count -ne 4) {
        return $null
    }

    $bitness = 0
    $major = 0
    $minor = 0
    if (
        -not [int]::TryParse($parts[0], [ref]$bitness) -or
        -not [int]::TryParse($parts[1], [ref]$major) -or
        -not [int]::TryParse($parts[2], [ref]$minor)
    ) {
        return $null
    }
    if ($bitness -ne 64) {
        return $null
    }
    if ($major -lt $MinimumMajor -or ($major -eq $MinimumMajor -and $minor -lt $MinimumMinor)) {
        return $null
    }

    $resolved = $parts[3].Trim()
    if ([string]::IsNullOrWhiteSpace($resolved) -or -not [System.IO.File]::Exists($resolved)) {
        return $null
    }
    if ($resolved -like "*.venv-kiwoom-x86*") {
        return $null
    }
    return [System.IO.Path]::GetFullPath($resolved)
}

$candidates = [System.Collections.Generic.List[object]]::new()

foreach ($scope in @("Process", "User")) {
    $configured = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", $scope)
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        $candidates.Add(
            (New-PythonCandidate -Executable $configured)
        )
    }
}

$projectVirtualEnvironment = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if ([System.IO.File]::Exists($projectVirtualEnvironment)) {
    $candidates.Add(
        (New-PythonCandidate -Executable $projectVirtualEnvironment)
    )
}

$launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
if ($null -ne $launcher) {
    $candidates.Add(
        (New-PythonCandidate -Executable $launcher.Source -PrefixArguments @("-3.12-64"))
    )
    $candidates.Add(
        (New-PythonCandidate -Executable $launcher.Source -PrefixArguments @("-3-64"))
    )
}

$localPythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
if ([System.IO.Directory]::Exists($localPythonRoot)) {
    Get-ChildItem $localPythonRoot -Directory -Filter "Python3*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "python.exe"
            if ([System.IO.File]::Exists($candidate)) {
                $candidates.Add(
                    (New-PythonCandidate -Executable $candidate)
                )
            }
        }
}

$pathPython = Get-Command "python.exe" -ErrorAction SilentlyContinue
if ($null -ne $pathPython) {
    $candidates.Add(
        (New-PythonCandidate -Executable $pathPython.Source)
    )
}

$seen = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($candidate in $candidates) {
    $executable = [string]$candidate.Executable
    $prefixArguments = [string[]]$candidate.PrefixArguments
    $identity = "$executable|$($prefixArguments -join ' ')"
    if (-not $seen.Add($identity)) {
        continue
    }
    $resolved = Test-ProjectPython -Executable $executable -PrefixArguments $prefixArguments
    if (-not [string]::IsNullOrWhiteSpace($resolved)) {
        Write-Output $resolved
        exit 0
    }
}

Write-Error @"
No compatible 64-bit Python 3.12+ interpreter was found for Alpha Cycle Lab.
The Kiwoom OpenAPI+ x86 bridge Python is intentionally excluded.
Run .\scripts\setup_project_python.cmd -InstallPython to install Python x64, create .venv, and install project dependencies.
"@
exit 2
