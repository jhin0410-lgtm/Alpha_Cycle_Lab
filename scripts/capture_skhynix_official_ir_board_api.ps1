[CmdletBinding()]
param(
    [string]$ObservedDate = "",
    [string]$SourcePointer = "",
    [string]$ComponentPointer = "",
    [string]$Output = "",
    [double]$TimeoutSeconds = 20.0
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$DefaultSourcePointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-attachment-discovery/latest_skhynix_ir_attachment_discovery.json"
$DefaultComponentPointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-component-contract-diagnostic/latest_skhynix_ir_component_contract_diagnostic.json"
$DefaultOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-board-api-capture"

Set-Location $RepositoryRoot
$ProjectPython = [Environment]::GetEnvironmentVariable("ALPHA_CYCLE_PYTHON", "Process")
if ([string]::IsNullOrWhiteSpace($ProjectPython)) {
    $VenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $ProjectPython = (Resolve-Path $VenvPython).Path
    }
    else {
        $ProjectPython = "python"
    }
}

& $ProjectPython -c "import alpha_cycle, pypdf" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw (
        "Alpha Cycle Python dependencies are not ready for SK hynix board API capture. " +
        "Resolved Python: $ProjectPython`n" +
        "Create/install the project environment with:`n" +
        "  py -3.12 -m venv .venv`n" +
        "  .\.venv\Scripts\python.exe -m pip install --upgrade pip`n" +
        "  .\.venv\Scripts\python.exe -m pip install -e .`n" +
        "Then rerun this script. You may also set ALPHA_CYCLE_PYTHON to an explicit interpreter."
    )
}
if ([string]::IsNullOrWhiteSpace($ObservedDate)) {
    $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
    $ObservedDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
        [DateTime]::UtcNow,
        $korea
    ).ToString("yyyy-MM-dd")
}
if ([string]::IsNullOrWhiteSpace($SourcePointer)) {
    $SourcePointer = $DefaultSourcePointer
}
if ([string]::IsNullOrWhiteSpace($ComponentPointer)) {
    $ComponentPointer = $DefaultComponentPointer
}
if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = $DefaultOutput
}

Write-Host "Resolving the SK hynix IR Axios transport from archived official bytes."
Write-Host "The /board/list request is sent only if the API base is uniquely source-derived."
Write-Host "Verified UI contract: bcode=105, page=1, pageSize=200, lang=ENG."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_board_api_capture_cli `
    --observed-date $ObservedDate `
    --source-pointer $SourcePointer `
    --component-pointer $ComponentPointer `
    --output $Output `
    --timeout $TimeoutSeconds
exit $LASTEXITCODE
