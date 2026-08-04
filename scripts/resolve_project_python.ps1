[CmdletBinding()]
param(
    [switch]$Diagnostic
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$ProbeScript = Join-Path $ScriptDirectory "project_python_probe.py"
$MinimumMajor = 3
$MinimumMinor = 12
$DiagnosticDirectory = Join-Path $RepositoryRoot "data\private\diagnostics"
$DiagnosticPath = Join-Path $DiagnosticDirectory "project_python_resolution.json"

function New-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [string[]]$PrefixArguments = @(),
        [string]$Source = "unspecified"
    )

    return [pscustomobject]@{
        Executable = $Executable
        PrefixArguments = [string[]]$PrefixArguments
        Source = $Source
    }
}

function Add-Candidate {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Candidates,
        [string]$Executable,
        [string[]]$PrefixArguments = @(),
        [string]$Source = "unspecified"
    )

    if ([string]::IsNullOrWhiteSpace($Executable)) {
        return
    }
    $Candidates.Add(
        (New-PythonCandidate `
            -Executable $Executable `
            -PrefixArguments $PrefixArguments `
            -Source $Source)
    )
}

function Add-RecursiveCandidates {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Candidates,
        [string]$Root,
        [string]$Source
    )

    if ([string]::IsNullOrWhiteSpace($Root) -or -not [System.IO.Directory]::Exists($Root)) {
        return
    }

    try {
        Get-ChildItem `
            -LiteralPath $Root `
            -Filter "python.exe" `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -notmatch '\\Lib\\venv\\scripts\\' -and
                $_.FullName -notmatch '\\.venv-kiwoom-x86\\'
            } |
            Sort-Object FullName -Unique |
            ForEach-Object {
                Add-Candidate `
                    -Candidates $Candidates `
                    -Executable $_.FullName `
                    -Source $Source
            }
    }
    catch {
        return
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
                        Add-Candidate `
                            -Candidates $Candidates `
                            -Executable $executable `
                            -Source "registry:$hive/$view/$versionName"
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
    $pathLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pathLauncher) {
        $launcherPaths.Add($pathLauncher.Source)
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
        foreach ($selector in @(
            "-V:3.13",
            "-3.13-64",
            "-V:3.12",
            "-3.12-64",
            "-3-64",
            "-3"
        )) {
            Add-Candidate `
                -Candidates $Candidates `
                -Executable $launcher `
                -PrefixArguments @($selector) `
                -Source "launcher:$selector"
        }
        try {
            $installed = & $launcher -0p 2>&1
            foreach ($line in @($installed)) {
                $match = [regex]::Match(
                    $line.ToString(),
                    '["'']?([A-Za-z]:\\.*?python(?:w)?\.exe)["'']?\s*$',
                    [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                )
                if ($match.Success) {
                    Add-Candidate `
                        -Candidates $Candidates `
                        -Executable $match.Groups[1].Value `
                        -Source "launcher_inventory"
                }
            }
        }
        catch {
            continue
        }
    }
}

function Invoke-PythonProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [string[]]$PrefixArguments = @(),
        [string]$Source = "unspecified"
    )

    $label = (@($Executable) + @($PrefixArguments)) -join " "
    if (-not [System.IO.File]::Exists($ProbeScript)) {
        throw "Project Python probe is missing: $ProbeScript"
    }

    try {
        $arguments = @($PrefixArguments) + @($ProbeScript)
        $raw = & $Executable @arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    catch {
        return [pscustomobject]@{
            Candidate = $label
            Source = $Source
            Status = "launch_failed"
            ExitCode = $null
            Bitness = $null
            Version = $null
            ResolvedPath = $null
            Detail = $_.Exception.Message
        }
    }

    $lines = @($raw | ForEach-Object { $_.ToString().Trim() })
    $jsonLine = @($lines | Where-Object { $_ -like "{*" } | Select-Object -Last 1)
    if ($exitCode -ne 0 -or $jsonLine.Count -eq 0) {
        return [pscustomobject]@{
            Candidate = $label
            Source = $Source
            Status = "launch_failed"
            ExitCode = $exitCode
            Bitness = $null
            Version = $null
            ResolvedPath = $null
            Detail = (($lines | Select-Object -Last 5) -join " | ")
        }
    }

    try {
        $payload = $jsonLine[-1] | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{
            Candidate = $label
            Source = $Source
            Status = "invalid_probe"
            ExitCode = $exitCode
            Bitness = $null
            Version = $null
            ResolvedPath = $null
            Detail = $jsonLine[-1]
        }
    }

    $bitness = [int]$payload.bitness
    $major = [int]$payload.major
    $minor = [int]$payload.minor
    $resolved = [string]$payload.executable
    $version = "$major.$minor"

    if ($bitness -ne 64) {
        $status = "rejected_32_bit"
        $detail = "expected 64-bit Python"
    }
    elseif ($major -lt $MinimumMajor -or ($major -eq $MinimumMajor -and $minor -lt $MinimumMinor)) {
        $status = "version_too_old"
        $detail = "minimum version is 3.12"
    }
    elseif ($resolved -like "*.venv-kiwoom-x86*") {
        $status = "rejected_kiwoom_bridge"
        $detail = "Kiwoom x86 bridge is isolated"
    }
    elseif ([string]::IsNullOrWhiteSpace($resolved) -or -not [System.IO.File]::Exists($resolved)) {
        $status = "resolved_path_missing"
        $detail = "sys.executable does not exist"
    }
    else {
        $status = "accepted"
        $detail = "compatible project Python"
        $resolved = [System.IO.Path]::GetFullPath($resolved)
    }

    return [pscustomobject]@{
        Candidate = $label
        Source = $Source
        Status = $status
        ExitCode = $exitCode
        Bitness = $bitness
        Version = $version
        ResolvedPath = $resolved
        Detail = $detail
    }
}

function Write-DiagnosticReport {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [System.Collections.Generic.List[object]]$Results,
        [string]$AcceptedPath
    )

    New-Item -ItemType Directory -Force -Path $DiagnosticDirectory | Out-Null
    $pathPython = Get-Command "python.exe" -ErrorAction SilentlyContinue
    $pathLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    $payload = [ordered]@{
        schema_version = "1.1"
        generated_at = [DateTimeOffset]::Now.ToString("o")
        repository_root = $RepositoryRoot
        probe_script = $ProbeScript
        local_app_data = $env:LOCALAPPDATA
        program_files = $env:ProgramFiles
        program_w6432 = $env:ProgramW6432
        path_python = if ($null -eq $pathPython) { "" } else { $pathPython.Source }
        path_launcher = if ($null -eq $pathLauncher) { "" } else { $pathLauncher.Source }
        accepted_path = $AcceptedPath
        candidates = @($Results)
    }
    $payload |
        ConvertTo-Json -Depth 7 |
        Set-Content -LiteralPath $DiagnosticPath -Encoding UTF8
}

$candidates = [System.Collections.Generic.List[object]]::new()

foreach ($scope in @("Process", "User")) {
    $configured = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", $scope)
    Add-Candidate `
        -Candidates $candidates `
        -Executable $configured `
        -Source "environment:$scope"
}

Add-Candidate `
    -Candidates $candidates `
    -Executable (Join-Path $RepositoryRoot ".venv\Scripts\python.exe") `
    -Source "project_venv"

foreach ($knownPython in @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312-32\python.exe"),
    "C:\Python314\python.exe",
    "C:\Python313\python.exe",
    "C:\Python312\python.exe"
)) {
    Add-Candidate `
        -Candidates $candidates `
        -Executable $knownPython `
        -Source "known_path"
}

Add-LauncherCandidates -Candidates $candidates
Add-RegistryCandidates -Candidates $candidates

foreach ($root in @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps")
)) {
    Add-RecursiveCandidates `
        -Candidates $candidates `
        -Root $root `
        -Source "recursive:$root"
}

foreach ($programRoot in @($env:ProgramFiles, $env:ProgramW6432)) {
    if ([string]::IsNullOrWhiteSpace($programRoot) -or -not [System.IO.Directory]::Exists($programRoot)) {
        continue
    }
    Get-ChildItem `
        -LiteralPath $programRoot `
        -Directory `
        -Filter "Python*" `
        -ErrorAction SilentlyContinue |
        ForEach-Object {
            Add-RecursiveCandidates `
                -Candidates $candidates `
                -Root $_.FullName `
                -Source "program_files:$($_.FullName)"
        }
}

$pathPython = Get-Command "python.exe" -ErrorAction SilentlyContinue
if ($null -ne $pathPython) {
    Add-Candidate `
        -Candidates $candidates `
        -Executable $pathPython.Source `
        -Source "path"
}

$seen = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
$results = [System.Collections.Generic.List[object]]::new()
$acceptedPath = $null
foreach ($candidate in $candidates) {
    $executable = [string]$candidate.Executable
    $prefixArguments = [string[]]$candidate.PrefixArguments
    $identity = "$executable|$($prefixArguments -join ' ')"
    if (-not $seen.Add($identity)) {
        continue
    }
    $result = Invoke-PythonProbe `
        -Executable $executable `
        -PrefixArguments $prefixArguments `
        -Source ([string]$candidate.Source)
    $results.Add($result)
    if ($result.Status -eq "accepted") {
        $acceptedPath = [string]$result.ResolvedPath
        break
    }
}

if ($Diagnostic -or [string]::IsNullOrWhiteSpace($acceptedPath)) {
    Write-DiagnosticReport -Results $results -AcceptedPath $acceptedPath
}

if (-not [string]::IsNullOrWhiteSpace($acceptedPath)) {
    Write-Output $acceptedPath
    exit 0
}

Write-Error @"
No compatible 64-bit Python 3.12+ interpreter was found for Alpha Cycle Lab.
The Kiwoom OpenAPI+ x86 bridge Python is intentionally excluded.
Diagnostic report: $DiagnosticPath
Run .\scripts\setup_project_python.cmd -InstallPython to install Python x64, create .venv, and install project dependencies.
"@
exit 2
