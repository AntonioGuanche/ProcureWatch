# ============================================================
# ProcureWatch – TED Result Notices (CAN) massive import
# Month-by-month using TED expert query: form-type = result
#
# TED v3 (eForms) form types:
#   planning     = Prior Information Notice (PIN)
#   competition  = Contract Notice (CN)
#   result       = Contract Award Notice (CAN) ← THIS
#   dir-awa-pre  = Direct Award Pre-notification
#   cont-modif   = Contract Modification
# ============================================================
# Usage: .\import_ted_can.ps1
# ============================================================

$headers = @{"X-Admin-Key"="Amu'Semois_R&R.2026"}
$base = "https://web-production-4d5c0.up.railway.app/api/admin/bulk-import"

# ── Date range: 2020-01 to 2026-02 ──
$startYear  = 2020
$endYear    = 2026
$endMonth   = 2

$months = @()
for ($y = $startYear; $y -le $endYear; $y++) {
    $maxM = if ($y -eq $endYear) { $endMonth } else { 12 }
    for ($m = 1; $m -le $maxM; $m++) {
        $from = "{0:D4}{1:D2}01" -f $y, $m
        $lastDay = [DateTime]::DaysInMonth($y, $m)
        $to   = "{0:D4}{1:D2}{2:D2}" -f $y, $m, $lastDay
        $months += ,@($from, $to)
    }
}

Write-Host "=== TED Result (CAN) Import ===" -ForegroundColor Yellow
Write-Host "Months to import: $($months.Count) ($startYear-01 -> $endYear-$('{0:D2}' -f $endMonth))" -ForegroundColor Yellow
Write-Host ""

$totalCreated = 0
$totalUpdated = 0
$startTime = Get-Date

foreach ($period in $months) {
    $pdFrom = $period[0]
    $pdTo   = $period[1]

    # TED v3 expert query: result = CAN (Contract Award Notice)
    $expertQuery = "form-type = result AND PD >= $pdFrom AND PD <= $pdTo"

    $label = "$($pdFrom.Substring(0,4))-$($pdFrom.Substring(4,2))"
    Write-Host "`n=== TED CAN $label ===" -ForegroundColor Cyan

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
Write-Host "CAN IMPORT COMPLETE in $elapsed min | Created: $totalCreated | Updated: $totalUpdated" -ForegroundColor Yellow

# ── Final backfill + matcher ──
Write-Host "`nRunning backfill + matcher..." -ForegroundColor Yellow
try {
    $bf = Invoke-RestMethod -Method POST `
      -Uri "$base`?sources=TED&page_size=1&max_pages=0&run_backfill=true&run_matcher=true" `
      -Headers $headers -TimeoutSec 600
    Write-Host "Backfill done: enriched=$($bf.backfill.enriched)" -ForegroundColor Green
} catch {
    Write-Host "Backfill error: $_" -ForegroundColor Red
}

Write-Host "`n=== ALL DONE ===" -ForegroundColor Yellow
