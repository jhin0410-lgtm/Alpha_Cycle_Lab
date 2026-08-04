[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BridgePython
)

$ErrorActionPreference = "Stop"

if (-not [System.IO.File]::Exists($BridgePython)) {
    throw "Kiwoom bridge Python executable does not exist."
}

$ScriptsDirectory = Split-Path -Parent $BridgePython
$VenvRoot = Split-Path -Parent $ScriptsDirectory
$SitePackages = Join-Path $VenvRoot "Lib\site-packages"
$PyQtRoot = Join-Path $SitePackages "PyQt5"
$QtCandidates = @(
    (Join-Path $PyQtRoot "Qt5"),
    (Join-Path $PyQtRoot "Qt")
)

$QtRoot = $null
$PlatformPluginDirectory = $null
foreach ($candidate in $QtCandidates) {
    $platforms = Join-Path $candidate "plugins\platforms"
    $qwindows = Join-Path $platforms "qwindows.dll"
    if ([System.IO.File]::Exists($qwindows)) {
        $QtRoot = $candidate
        $PlatformPluginDirectory = $platforms
        break
    }
}

if ([string]::IsNullOrWhiteSpace($QtRoot)) {
    throw (
        "PyQt5 qwindows.dll was not found in the x86 bridge environment. " +
        "Re-run setup with -Force after confirming the pinned PyQt5 packages installed."
    )
}

$PluginDirectory = Join-Path $QtRoot "plugins"
$QtBinDirectory = Join-Path $QtRoot "bin"

$env:QT_QPA_PLATFORM_PLUGIN_PATH = $PlatformPluginDirectory
$env:QT_PLUGIN_PATH = $PluginDirectory
if ([System.IO.Directory]::Exists($QtBinDirectory)) {
    $pathEntries = @($env:PATH -split ";")
    if ($pathEntries -notcontains $QtBinDirectory) {
        $env:PATH = "$QtBinDirectory;$env:PATH"
    }
}

if (-not [System.IO.File]::Exists(
    (Join-Path $env:QT_QPA_PLATFORM_PLUGIN_PATH "qwindows.dll")
)) {
    throw "Qt Windows platform plugin path initialization failed."
}
