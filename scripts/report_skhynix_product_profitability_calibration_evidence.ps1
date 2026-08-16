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
$cycleDriverPointer = Join-Path $repoRoot `
    "data\private\research\sec-product-cycle-driver-support\latest_sec_product_cycle_driver_support.json"
$companyProfitabilityPointer = Join-Path $repoRoot `
    "data\private\research\skhynix-opendart-quarterly-company-profitability\latest_quarterly_company_profitability.json"
$historicalProductPointer = Join-Path $repoRoot `
    "data\private\research\skhynix-opendart-historical-product-revenue-panel\latest_historical_product_revenue_panel.json"

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
        "[1/7] Current 2Q26 direct product revenue is missing/stale for " +
        "$EvaluationDate; certifying it first."
    )
    & (Join-Path $PSScriptRoot "report_skhynix_opendart_q2_product_revenue_certification.ps1") `
        -EvaluationDate $EvaluationDate
    if ($LASTEXITCODE -ne 0) {
        throw "Current 2Q26 product-revenue certification failed."
    }
}
else {
    Write-Host "[1/7] Current 2Q26 direct product-revenue pointer matches evaluation date."
}

if (-not (Test-Path $secSupportPointer)) {
    if ([string]::IsNullOrWhiteSpace($env:SEC_EDGAR_USER_AGENT)) {
        throw (
            "SEC_EDGAR_USER_AGENT is required because SEC profitability support " +
            "has not been captured yet. Example: AlphaCycleLab your-email@example.com"
        )
    }
    Write-Host "[2/7] Capturing official SEC historical profitability support."
    & $python -m alpha_cycle.sec_product_profitability_support_cli `
        --document-id "skhynix_000660_2026_sec_424b4_product_profitability_support" `
        --observed-date $EvaluationDate
    if ($LASTEXITCODE -ne 0) {
        throw "SEC historical profitability support capture failed."
    }
}
else {
    Write-Host "[2/7] SEC historical profitability support pointer already exists."
}

$secSupportJson = $null
try {
    $secSupportJson = Get-Content -Raw -Path $secSupportPointer | ConvertFrom-Json
}
catch {
    throw "SEC historical profitability support pointer is unreadable after step 2."
}

$cycleDriverReusable = $false
if (Test-Path $cycleDriverPointer) {
    try {
        $cycleDriverJson = Get-Content -Raw -Path $cycleDriverPointer | ConvertFrom-Json
        $cycleDriverReusable = (
            [string]$cycleDriverJson.status -eq "sec_product_cycle_driver_support_captured" -and
            [string]$cycleDriverJson.observed_date -eq $EvaluationDate -and
            [int]$cycleDriverJson.observation_count -eq 13 -and
            [string]$cycleDriverJson.source_profitability_support_evidence_id -eq `
                [string]$secSupportJson.evidence_id
        )
    }
    catch {
        $cycleDriverReusable = $false
    }
}
if ($cycleDriverReusable) {
    Write-Host "[3/7] Reusing 13-quarter SEC cycle-driver support for the current source evidence."
}
else {
    Write-Host "[3/7] Replaying 13-quarter DRAM/NAND cycle-driver bands from archived SEC bytes."
    & $python -m alpha_cycle.sec_product_cycle_driver_support_cli `
        --evaluation-date $EvaluationDate
    if ($LASTEXITCODE -ne 0) {
        throw "SEC cycle-driver support capture/replay failed."
    }
}

$companyProfitabilityReusable = $false
if (Test-Path $companyProfitabilityPointer) {
    try {
        $companyProfitabilityJson = `
            Get-Content -Raw -Path $companyProfitabilityPointer | ConvertFrom-Json
        $companyProfitabilityReusable = (
            [string]$companyProfitabilityJson.status -eq `
                "skhynix_opendart_quarterly_company_profitability_captured" -and
            [string]$companyProfitabilityJson.evaluation_date -eq $EvaluationDate -and
            [int]$companyProfitabilityJson.observation_count -eq 10
        )
    }
    catch {
        $companyProfitabilityReusable = $false
    }
}
if ($companyProfitabilityReusable) {
    Write-Host "[4/7] Reusing 10-quarter OpenDART company-profitability panel."
}
else {
    Write-Host "[4/7] Capturing 10 direct OpenDART company profitability quarters."
    & $python -m alpha_cycle.sk_hynix_opendart_quarterly_company_profitability_cli `
        --evaluation-date $EvaluationDate
    if ($LASTEXITCODE -ne 0) {
        throw "OpenDART quarterly company profitability capture failed."
    }
}

Write-Host "[5/7] Recapturing historical direct product-revenue periods with exact text bytes."
Write-Host "      Parser-incompatible periods are preserved as failed diagnostics, not inferred."
& $python -m alpha_cycle.sk_hynix_opendart_historical_product_revenue_panel_cli `
    --evaluation-date $EvaluationDate
if ($LASTEXITCODE -ne 0) {
    throw "Historical product-revenue batch capture failed before producing a panel."
}

if (-not (Test-Path $historicalProductPointer)) {
    throw "Historical product-revenue pointer is missing after step 5."
}
try {
    $historicalProductJson = Get-Content -Raw -Path $historicalProductPointer | ConvertFrom-Json
}
catch {
    throw "Historical product-revenue pointer is unreadable after step 5."
}
$historicalFailedPeriodCount = [int]$historicalProductJson.failed_period_count
if ($historicalFailedPeriodCount -gt 0) {
    Write-Host (
        "[5a/7] " + $historicalFailedPeriodCount +
        " historical periods remain parser-incompatible; replaying preserved failures offline."
    )
    Write-Host "       These signatures are diagnostics only and never promote source facts."
    & $python -m alpha_cycle.sk_hynix_opendart_historical_product_revenue_diagnostics_cli `
        --evaluation-date $EvaluationDate
    if ($LASTEXITCODE -ne 0) {
        Write-Warning (
            "Historical product-revenue offline diagnostics failed; " +
            "calibration readiness will remain fail-closed."
        )
    }
}
else {
    Write-Host "[5a/7] Historical direct product-revenue source coverage is complete."
}

Write-Host "[6/7] Replaying all evidence and reporting fail-closed calibration readiness."
& $python -m alpha_cycle.sk_hynix_product_profitability_calibration_readiness_cli `
    --evaluation-date $EvaluationDate
if ($LASTEXITCODE -ne 0) {
    throw "Product-profitability calibration readiness replay failed."
}

Write-Host "[7/7] Probing structural design rank with direction-only issuer semantics."
Write-Host "      This does not estimate product margins or open the fit gate."
& $python -m alpha_cycle.sk_hynix_product_profitability_structural_rank_probe_cli `
    --evaluation-date $EvaluationDate
if ($LASTEXITCODE -ne 0) {
    throw "Product-profitability structural rank probe failed before producing a report."
}

Write-Host "============================================================"
Write-Host "[OK] Evidence capture/replay and structural rank probe completed."
Write-Host "Numeric product-margin fitting remains disabled; rank readiness is not model readiness."
Write-Host "============================================================"