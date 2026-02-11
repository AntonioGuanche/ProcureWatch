# ============================================================
# ProcureWatch – TED Result (CAN) import for BELGIUM ONLY
# Faster variant: year-by-year (Belgium volume is manageable)
# ============================================================
# Usage: .\import_ted_can_belgium.ps1
# ============================================================

$headers = @{"X-Admin-Key"="Amu'Semois_R&R.2026"}
$base = "https://web-production-4d5c0.up.railway.app/api/admin/bulk-import"

$startYear = 2020
$endYear   = 2026

Write-Host "=== TED CAN Import (Belgium only) ===" -ForegroundColor Yellow
Write-Host "Years: $startYear -> $endYear" -ForegroundColor Yellow
Write-Host ""

$totalCreated = 0
$totalUpdated = 0
$startTime = Get-Date

for ($y = $startYear; $y -le $endYear; $y++) {
    $pdFrom = "${y}0101"
    $pdTo   = if ($y -eq $endYear) { "${y}0228" } else { "${y}1231" }

    # Belgium CANs: form-type = result (TED v3 eForms)
    $expertQuery = "form-type = result AND buyer-country = BEL AND PD >= $pdFrom AND PD <= $pdTo"

    Write-Host "`n=== TED CAN Belgium $y ===" -ForegroundColor Cyan

    try {
        $uri = "$base`?sources=TED&term_ted=$([uri]::EscapeDataString($expertQuery))&ted_days_back=3650&page_size=250&max_pages=100&run_backfill=false&run_matcher=false"

        $r = Invoke-RestMethod -Method POST `
          -Uri $uri `
          -Headers $headers -TimeoutSec 600

        $s = $r.sources.ted
        $totalCreated += $s.total_created
        $totalUpdated += $s.total_updated
        Write-Host "  total_api=$($s.api_total_count) created=$($s.total_created) updated=$($s.total_updated) pages=$($s.pages_fetched) time=$($s.elapsed_seconds)s" -ForegroundColor Green

    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
    }

    Start-Sleep -Seconds 2
}

$elapsed = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 1)
Write-Host "`n========================================" -ForegroundColor Yellow
Write-Host "BELGIUM CAN IMPORT COMPLETE in $elapsed min | Created: $totalCreated | Updated: $totalUpdated" -ForegroundColor Yellow

# ── Final backfill ──
Write-Host "`nRunning backfill..." -ForegroundColor Yellow
try {
    $bf = Invoke-RestMethod -Method POST `
      -Uri "$base`?sources=TED&page_size=1&max_pages=0&run_backfill=true&run_matcher=true" `
      -Headers $headers -TimeoutSec 600
    Write-Host "Backfill done: enriched=$($bf.backfill.enriched)" -ForegroundColor Green
} catch {
    Write-Host "Backfill error: $_" -ForegroundColor Red
}
