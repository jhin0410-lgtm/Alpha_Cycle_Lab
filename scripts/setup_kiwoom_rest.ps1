[CmdletBinding()]
param(
    [string]$AppKeyFile,
    [string]$AppSecretFile,
    [switch]$Force,
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"
$PathVariables = @(
    "KIWOOM_REST_APP_KEY_FILE",
    "KIWOOM_REST_APP_SECRET_FILE"
)

function Get-EffectivePath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    $userValue = [Environment]::GetEnvironmentVariable($Name, "User")
    $value = if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        $processValue
    }
    else {
        $userValue
    }
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        [Environment]::SetEnvironmentVariable($Name, $value, "Process")
        return $value
    }
    return $null
}

function Test-SecretTextFile {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        throw "$Name path cannot be blank."
    }
    $resolved = [System.IO.Path]::GetFullPath($PathValue)
    if (-not [System.IO.File]::Exists($resolved)) {
        throw "$Name file does not exist."
    }
    $unsupported = @(".exe", ".msi", ".dll", ".ocx", ".zip", ".7z", ".rar")
    if ($unsupported -contains [System.IO.Path]::GetExtension($resolved).ToLowerInvariant()) {
        throw "$Name must be a Kiwoom REST text credential, not an Open API+ installer."
    }
    return $resolved
}

if ($StatusOnly) {
    $missing = @()
    foreach ($name in $PathVariables) {
        $value = Get-EffectivePath -Name $name
        if ($value -and [System.IO.File]::Exists($value)) {
            Write-Host "$name configured"
        }
        else {
            Write-Host "$name missing"
            $missing += $name
        }
    }
    if ($missing.Count -gt 0) {
        exit 2
    }
    exit 0
}

$existingKey = Get-EffectivePath -Name "KIWOOM_REST_APP_KEY_FILE"
$existingSecret = Get-EffectivePath -Name "KIWOOM_REST_APP_SECRET_FILE"

if (-not $Force -and $existingKey -and $existingSecret) {
    if ([System.IO.File]::Exists($existingKey) -and [System.IO.File]::Exists($existingSecret)) {
        Write-Host "Kiwoom REST credential file paths are already configured."
        exit 0
    }
}

if ([string]::IsNullOrWhiteSpace($AppKeyFile)) {
    $AppKeyFile = Read-Host "Enter the full path to the Kiwoom REST App Key text file"
}
if ([string]::IsNullOrWhiteSpace($AppSecretFile)) {
    $AppSecretFile = Read-Host "Enter the full path to the Kiwoom REST App Secret text file"
}

$resolvedKey = Test-SecretTextFile -Name "Kiwoom REST App Key" -PathValue $AppKeyFile
$resolvedSecret = Test-SecretTextFile -Name "Kiwoom REST App Secret" -PathValue $AppSecretFile

[Environment]::SetEnvironmentVariable(
    "KIWOOM_REST_APP_KEY_FILE",
    $resolvedKey,
    "User"
)
[Environment]::SetEnvironmentVariable(
    "KIWOOM_REST_APP_SECRET_FILE",
    $resolvedSecret,
    "User"
)
[Environment]::SetEnvironmentVariable(
    "KIWOOM_REST_APP_KEY_FILE",
    $resolvedKey,
    "Process"
)
[Environment]::SetEnvironmentVariable(
    "KIWOOM_REST_APP_SECRET_FILE",
    $resolvedSecret,
    "Process"
)

Write-Host "Kiwoom REST credential file paths are configured for this Windows user."
Write-Host "Credential contents and file names were not printed or copied into the repository."
