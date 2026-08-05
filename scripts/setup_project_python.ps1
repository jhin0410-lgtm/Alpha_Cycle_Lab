[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$InstallPython
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$Resolver = Join-Path $ScriptDirectory "resolve_project_python.ps1"
$ProbeScript = Join-Path $ScriptDirectory "project_python_probe.py"
$VirtualEnvironmentRoot = Join-Path $RepositoryRoot ".venv"
$VirtualEnvironmentPython = Join-Path $VirtualEnvironmentRoot "Scripts\python.exe"
$DiagnosticPath = Join-Path $RepositoryRoot "data\private\diagnostics\project_python_resolution.json"

function Resolve-ProbedX64ProjectPython {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    if (
        -not [System.IO.File]::Exists($PythonPath) -or
        -not [System.IO.File]::Exists($ProbeScript)
    ) {
        return $null
    }
    try {
        $raw = & $PythonPath $ProbeScript 2>&1
        $exitCode = $LASTEXITCODE
    }
    catch {
        return $null
    }
    if ($exitCode -ne 0 -or $null -eq $raw) {
        return $null
    }
    $jsonLine = @(
        $raw |
            ForEach-Object { $_.ToString().Trim() } |
            Where-Object { $_ -like "{*" } |
            Select-Object -Last 1
    )
    if ($jsonLine.Count -eq 0) {
        return $null
    }
    try {
        $payload = $jsonLine[-1] | ConvertFrom-Json
        $bitness = [int]$payload.bitness
        $major = [int]$payload.major
        $minor = [int]$payload.minor
        $resolved = [System.IO.Path]::GetFullPath([string]$payload.executable)
    }
    catch {
        return $null
    }
    if (
        $bitness -ne 64 -or
        ($major -lt 3 -or ($major -eq 3 -and $minor -lt 12)) -or
        -not [System.IO.File]::Exists($resolved) -or
        $resolved -like "*.venv-kiwoom-x86*"
    ) {
        return $null
    }
    return $resolved
}

function Test-X64ProjectPython {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    return -not [string]::IsNullOrWhiteSpace(
        (Resolve-ProbedX64ProjectPython -PythonPath $PythonPath)
    )
}

function Test-PathInsideDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$CandidatePath,
        [Parameter(Mandatory = $true)][string]$DirectoryPath
    )

    try {
        $candidate = [System.IO.Path]::GetFullPath($CandidatePath)
        $directory = [System.IO.Path]::GetFullPath($DirectoryPath).TrimEnd(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
    }
    catch {
        return $false
    }
    $boundary = $directory + [System.IO.Path]::DirectorySeparatorChar
    return $candidate.StartsWith(
        $boundary,
        [System.StringComparison]::OrdinalIgnoreCase
    )
}

function Resolve-ConfiguredExternalPython {
    $candidates = [System.Collections.Generic.List[string]]::new()
    foreach ($scope in @("Process", "User")) {
        $configured = [Environment]::GetEnvironmentVariable(
            "ALPHA_CYCLE_PYTHON",
            $scope
        )
        if (-not [string]::IsNullOrWhiteSpace($configured)) {
            $candidates.Add($configured)
        }
    }
    $pathPython = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pathPython) {
        $candidates.Add($pathPython.Source)
    }

    $seen = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($candidate in $candidates) {
        try {
            $candidatePath = [System.IO.Path]::GetFullPath($candidate.Trim('"'))
        }
        catch {
            continue
        }
        if (-not $seen.Add($candidatePath)) {
            continue
        }
        $resolved = Resolve-ProbedX64ProjectPython -PythonPath $candidatePath
        if ([string]::IsNullOrWhiteSpace($resolved)) {
            continue
        }
        if (
            -not (Test-PathInsideDirectory `
                -CandidatePath $resolved `
                -DirectoryPath $VirtualEnvironmentRoot)
        ) {
            return $resolved
        }
    }
    return $null
}

function Resolve-X64ProjectPython {
    param([switch]$ExcludeProjectVenv)

    $resolverArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $Resolver
    )
    if ($ExcludeProjectVenv) {
        $resolverArguments += "-ExcludeProjectVenv"
    }
    try {
        $resolved = & powershell.exe @resolverArguments 2>$null
        $exitCode = $LASTEXITCODE
    }
    catch {
        return $null
    }
    if ($exitCode -ne 0 -or $null -eq $resolved) {
        return $null
    }
    $path = @($resolved)[-1].ToString().Trim()
    return Resolve-ProbedX64ProjectPython -PythonPath $path
}

function Resolve-SetupBasePython {
    param([switch]$ForcedRebuild)

    if ($ForcedRebuild) {
        $configuredExternal = Resolve-ConfiguredExternalPython
        if (-not [string]::IsNullOrWhiteSpace($configuredExternal)) {
            return $configuredExternal
        }
    }
    return Resolve-X64ProjectPython -ExcludeProjectVenv:$ForcedRebuild
}

function Wait-X64ProjectPython {
    param(
        [ValidateRange(1, 60)][int]$Attempts = 20,
        [ValidateRange(1, 10)][int]$DelaySeconds = 1,
        [switch]$ExcludeProjectVenv
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $resolved = Resolve-SetupBasePython -ForcedRebuild:$ExcludeProjectVenv
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
# During a forced rebuild, resolve the interpreter's probed sys.executable and
# reject it only when that real executable is inside the exact project .venv.
# Invalid configured paths are skipped so PATH and the general resolver remain usable.
$BasePython = Resolve-SetupBasePython -ForcedRebuild:$Force
if (-not $BasePython -and $InstallPython) {
    Install-X64Python
    Write-Host "Waiting for the new x64 Python registration to become visible..."
    $BasePython = Wait-X64ProjectPython -ExcludeProjectVenv:$Force
}
if (-not $BasePython) {
    $diagnosticArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $Resolver,
        "-Diagnostic"
    )
    if ($Force) {
        $diagnosticArguments += "-ExcludeProjectVenv"
    }
    & powershell.exe @diagnosticArguments 2>$null | Out-Null
    Write-Host "A separate 64-bit Python 3.12+ runtime is required for Alpha Cycle Lab."
    Write-Host "The Kiwoom OpenAPI+ x86 bridge Python cannot be used for analysis."
    Write-Host "Diagnostic report: $DiagnosticPath"
    Write-Host "Run this command only when x64 Python is genuinely absent:"
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
    throw "The main project virtual environment is not using 64-bit Python 3.12+. Run setup with -Force."
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

$verification = & $VirtualEnvironmentPython $ProbeScript --verify-project 2>&1
if ($LASTEXITCODE -ne 0) {
    $verification | ForEach-Object { Write-Host $_ }
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