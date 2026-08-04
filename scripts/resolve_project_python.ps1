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

function Add-DirectoryCandidates {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Candidates,
        [string]$Root
    )

    if ([string]::IsNullOrWhiteSpace($Root) -or -not [System.IO.Directory]::Exists($Root)) {
        return
    }

    $direct = Join-Path $Root "python.exe"
    if ([System.IO.File]::Exists($direct)) {
        $Candidates.Add((New-PythonCandidate -Executable $direct))
    }

    Get-ChildItem $Root -Directory -Filter "Python3*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object {
            $candidate = Join-Path $_.FullName "python.exe"
            if ([System.IO.File]::Exists($candidate)) {
                $Candidates.Add((New-PythonCandidate -Executable $candidate))
            }
        }
}

function Add-RegistryCandidates {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Candidates
    )

    $hives = @(
        [Microsoft.Win32.RegistryHive]::CurrentUser,
        [Microsoft.Win32.RegistryHive]::LocalMachine
    )
    $views = @(
        [Microsoft.Win32.RegistryView]::Registry64,
        [Microsoft.Win32.RegistryView]::Registry32
    )

    foreach ($hive in $hives) {
        foreach ($view in $views) {
            $baseKey = $null
            $pythonCore = $null
            try {
                $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey($hive, $view)
                $pythonCore = $baseKey.OpenSubKey("Software\Python\PythonCore")
                if ($null -eq $pythonCore) {
                    continue
                }
                foreach ($versionName in $pythonCore.GetSubKeyNames()) {
                    $installPath = $pythonCore.OpenSubKey("$versionName\InstallPath")
                    if ($null -eq $installPath) {
                        continue
                    }
                    try {
                        $executable = [string]$installPath.GetValue("ExecutablePath", "")
                        if ([string]::IsNullOrWhiteSpace($executable)) {
                            $installRoot = [string]$installPath.GetValue("", "")
                            if (-not [string]::IsNullOrWhiteSpace($installRoot)) {
                                $executable = Join-Path $installRoot "python.exe"
                            }
                        }
                        if (-not [string]::IsNullOrWhiteSpace($executable)) {
                            $Candidates.Add((New-PythonCandidate -Executable $executable))
                        }
                    }
                    finally {
                        $installPath.Dispose()
                    }
                }
            }
            catch {
                continue
            }
            finally {
                if ($null -ne $pythonCore) {
                    $pythonCore.Dispose()
                }
                if ($null -ne $baseKey) {
                    $baseKey.Dispose()
                }
            }
        }
    }
}

function Add-LauncherCandidates {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Candidates
    )

    $launcherPaths = [System.Collections.Generic.List[string]]::new()
    $command = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        $launcherPaths.Add($command.Source)
    }
    foreach ($knownPath in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Launcher\py.exe"),
        (Join-Path $env:WINDIR "py.exe"),
        (Join-Path $env:ProgramFiles "Python Launcher\py.exe")
    )) {
        if ([System.IO.File]::Exists($knownPath)) {
            $launcherPaths.Add($knownPath)
        }
    }

    $seenLaunchers = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($launcher in $launcherPaths) {
        if (-not $seenLaunchers.Add($launcher)) {
            continue
        }
        foreach ($selector in @("-3.12-64", "-V:3.12", "-3-64")) {
            $Candidates.Add(
                (New-PythonCandidate -Executable $launcher -PrefixArguments @($selector))
            )
        }
        try {
            $installed = & $launcher -0p 2>$null
            if ($LASTEXITCODE -eq 0) {
                foreach ($line in @($installed)) {
                    $match = [regex]::Match(
                        $line.ToString(),
                        "([A-Za-z]:\\.*?python(?:w)?\.exe)\s*$",
                        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                    )
                    if ($match.Success) {
                        $Candidates.Add(
                            (New-PythonCandidate -Executable $match.Groups[1].Value)
                        )
                    }
                }
            }
        }
        catch {
            continue
        }
    }
}

$candidates = [System.Collections.Generic.List[object]]::new()

foreach ($scope in @("Process", "User")) {
    $configured = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", $scope)
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        $candidates.Add((New-PythonCandidate -Executable $configured))
    }
}

$projectVirtualEnvironment = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
if ([System.IO.File]::Exists($projectVirtualEnvironment)) {
    $candidates.Add((New-PythonCandidate -Executable $projectVirtualEnvironment))
}

Add-LauncherCandidates -Candidates $candidates
Add-RegistryCandidates -Candidates $candidates

foreach ($root in @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python"),
    $env:ProgramFiles,
    $env:ProgramW6432,
    "C:\Python312",
    "C:\Python313"
)) {
    Add-DirectoryCandidates -Candidates $candidates -Root $root
}

$pathPython = Get-Command "python.exe" -ErrorAction SilentlyContinue
if ($null -ne $pathPython) {
    $candidates.Add((New-PythonCandidate -Executable $pathPython.Source))
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