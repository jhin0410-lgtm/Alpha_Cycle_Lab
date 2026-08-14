[CmdletBinding()]
param(
    [string]$ObservedDate = "",
    [double]$BoardTimeoutSeconds = 20.0,
    [double]$PdfTimeoutSeconds = 30.0
)

$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $ScriptDirectory
$SourcePointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-attachment-discovery/latest_skhynix_ir_attachment_discovery.json"
$ComponentPointer = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-component-contract-diagnostic/latest_skhynix_ir_component_contract_diagnostic.json"
$BoardOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-board-api-capture"
$BoardPointer = Join-Path $BoardOutput "latest_skhynix_ir_board_api_capture.json"
$AttachmentOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-attachment"
$AttachmentPointer = Join-Path $AttachmentOutput "latest_skhynix_ir_q2_attachment.json"
$ReadinessOutput = Join-Path $RepositoryRoot "data/private/research/skhynix-official-ir-q2-parser-readiness"

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
        "Alpha Cycle Python dependencies are not ready for SK hynix Q2 source capture. " +
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

Write-Host "[1/3] Resolving the official SK hynix IR transport and capturing /board/list."
Write-Host "No request is sent if the Axios API base is not uniquely source-derived."
Write-Host "Python: $ProjectPython"
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_board_api_capture_cli `
    --observed-date $ObservedDate `
    --source-pointer $SourcePointer `
    --component-pointer $ComponentPointer `
    --output $BoardOutput `
    --timeout $BoardTimeoutSeconds
if ($LASTEXITCODE -ne 0) {
    Write-Error "SK hynix board API stage did not resolve/capture safely; later stages were not attempted."
    exit $LASTEXITCODE
}

Write-Host "[2/3] Capturing the returned 2Q26 Earnings Release PDF from cdnUrl + fileUrl2."
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_q2_attachment_capture_cli `
    --observed-date $ObservedDate `
    --board-pointer $BoardPointer `
    --output $AttachmentOutput `
    --timeout $PdfTimeoutSeconds
if ($LASTEXITCODE -ne 0) {
    Write-Error "SK hynix official PDF stage failed; parser-readiness stage was not attempted."
    exit $LASTEXITCODE
}

Write-Host "[3/3] Extracting source-backed parser-contract review context."
Write-Host "Numeric semantics and registry activation remain disabled."
& $ProjectPython -m alpha_cycle.sk_hynix_official_ir_q2_parser_readiness_cli `
    --observed-date $ObservedDate `
    --attachment-pointer $AttachmentPointer `
    --output $ReadinessOutput
exit $LASTEXITCODE
