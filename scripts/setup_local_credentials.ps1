[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"

$RequiredVariables = @(
    "TOSSINVEST_CLIENT_ID",
    "TOSSINVEST_CLIENT_SECRET",
    "OPENDART_API_KEY",
    "ECOS_API_KEY"
)

function Get-EffectiveCredentialValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    $userValue = [Environment]::GetEnvironmentVariable($Name, "User")

    if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        if ([string]::IsNullOrWhiteSpace($userValue)) {
            [Environment]::SetEnvironmentVariable($Name, $processValue, "User")
        }
        return $processValue
    }

    if (-not [string]::IsNullOrWhiteSpace($userValue)) {
        [Environment]::SetEnvironmentVariable($Name, $userValue, "Process")
        return $userValue
    }

    return $null
}

function Test-CredentialValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name cannot be blank."
    }
    if ($Value -match "[\r\n]") {
        throw "$Name cannot contain a newline."
    }
    if ($Value.ToLowerInvariant().Contains("replace_with")) {
        throw "$Name cannot use a placeholder value."
    }
}

if ($StatusOnly) {
    $missing = @()
    foreach ($name in $RequiredVariables) {
        if (Get-EffectiveCredentialValue -Name $name) {
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

foreach ($name in $RequiredVariables) {
    $existing = Get-EffectiveCredentialValue -Name $name
    if ($existing -and -not $Force) {
        Write-Host "$name already configured"
        continue
    }

    $secureValue = Read-Host "Enter $name" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        $plainValue = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        Test-CredentialValue -Name $name -Value $plainValue
        [Environment]::SetEnvironmentVariable($name, $plainValue, "User")
        [Environment]::SetEnvironmentVariable($name, $plainValue, "Process")
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
        $plainValue = $null
        $secureValue = $null
    }
    Write-Host "$name configured"
}

Write-Host "All Alpha Cycle Lab API credentials are configured for this Windows user and current PowerShell process."
