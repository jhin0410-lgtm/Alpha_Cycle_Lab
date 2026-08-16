param(
    [string]$EvaluationDate = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($EvaluationDate)) {
    try {
        $korea = [System.TimeZoneInfo]::FindSystemTimeZoneById("Korea Standard Time")
        $EvaluationDate = [System.TimeZoneInfo]::ConvertTimeFromUtc(
            [DateTime]::UtcNow,
            $korea
        ).ToString("yyyy-MM-dd")
    }
    catch {
        $EvaluationDate = (Get-Date).ToString("yyyy-MM-dd")
    }
}

$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path $repoRoot ".venv313\Scripts\python.exe")
)
$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $python = $candidate
        break
    }
}
if ($null -eq $python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python environment not found. Create .venv or make python available on PATH."
    }
    $python = $pythonCommand.Source
}

if ([string]::IsNullOrWhiteSpace($env:OPENDART_API_KEY)) {
    throw "OPENDART_API_KEY is required for quarterly company and historical product captures."
}

$currentProductPointer = Join-Path $repoRoot `
    "data\private\research\skhynix-opendart-q2-product-revenue-certification\latest_certification.json"
$secSupportPointer = Join-Path $repoRoot `
    "data\private\research\sec-product-profitability-support\latest_sec_product_profitability_support.json"

Write-Host "============================================================"
Write-Host "SK hynix product-profitability calibration evidence"
Write-Host "Evaluation date: $EvaluationDate"
Write-Host "Python: $python"
Write-Host "============================================================"

$currentProductMatchesEvaluationDate = $false
if (Test-Path $currentProductPointer) {
    try {
        $currentPointerJson = Get-Content -Raw -Path $currentProductPointer | ConvertFrom-Json
        $currentProductMatchesEvaluationDate = (
            [string]$currentPointerJson.evaluation_date -eq $EvaluationDate
        )
    }
    catch {
        $currentProductMatchesEvaluationDate = $false
    }
}

if (-not $currentProductMatchesEvaluationDate) {
    Write-Host (
        "[1/6] Current 2Q26 direct product revenue is missing/stale for " +
        "$EvaluationDate; certifying it first."
    )
    & (Join-Path $PSScriptRoot "report_skhynix_opendart_q2_product_revenue_certification.ps1") `
        -EvaluationDate $EvaluationDate
    if ($LASTEXITCODE -ne 0) {
        throw "Current 2Q26 product-revenue certification failed."
    }
}
else {
    Write-Host "[1/6] Current 2Q26 direct product-revenue pointer matches evaluation date."
}

if (-not (Test-Path $secSupportPointer)) {
    if ([string]::IsNullOrWhiteSpace($env:SEC_EDGAR_USER_AGENT)) {
        throw (
            "SEC_EDGAR_USER_AGENT is required because SEC profitability support " +
            "has not been captured yet. Example: AlphaCycleLab your-email@example.com"
        )
    }
    Write-Host "[2/6] Capturing official SEC historical profitability support."
    & $python -m alpha_cycle.sec_product_profitability_support_cli `
        --document-id "skhynix_000660_2026_sec_424b4_product_profitability_support" `
        --observed-date $EvaluationDate
    if ($LASTEXITCODE -ne 0) {
        throw "SEC historical profitability support capture failed."
    }
}
else {
    Write-Host "[2/6] SEC historical profitability support pointer already exists."
}

Write-Host "[3/6] Replaying 13-quarter DRAM/NAND cycle-driver bands from archived SEC bytes."
& $python -m alpha_cycle.sec_product_cycle_driver_support_cli `
    --evaluation-date $EvaluationDate
if ($LASTEXITCODE -ne 0) {
    throw "SEC cycle-driver support capture/replay failed."
}

Write-Host "[4/6] Capturing 10 direct OpenDART company profitability quarters."
& $python -m alpha_cycle.sk_hynix_opendart_quarterly_company_profitability_cli `
    --evaluation-date $EvaluationDate
if ($LASTEXITCODE -ne 0) {
    throw "OpenDART quarterly company profitability capture failed."
}

Write-Host "[5/6] Capturing historical direct product-revenue periods."
Write-Host "      Parser-incompatible periods are preserved as failed diagnostics, not inferred."
& $python -m alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli `
    --evaluation-date $EvaluationDate
if ($LASTEXITCODE -ne 0) {
    throw "Historical product-revenue batch capture failed before producing a panel."
}

Write-Host "[6/6] Replaying all evidence and reporting fail-closed calibration readiness."
& $python -m alpha_cycle.sk_hynix_product_profitability_calibration_readiness_cli `
    --evaluation-date $EvaluationDate
if ($LASTEXITCODE -ne 0) {
    throw "Product-profitability calibration readiness replay failed."
}

Write-Host "============================================================"
Write-Host "[OK] Evidence capture/replay completed."
Write-Host "Numeric product-margin fitting remains disabled unless the readiness audit says otherwise."
Write-Host "============================================================"
