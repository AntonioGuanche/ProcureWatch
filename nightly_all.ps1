# =============================================================================
# ProcureWatch - Nightly All-in-One v6
# v6: removed PDF download steps (7+9). Downloads now on-demand via UI.
#     Kept: import, backfill, enrichment, doc cataloging, watchlists.
# v5: fixed TED links.pdf extraction, smart batch download, Q&A fallback
# Usage: powershell -ExecutionPolicy Bypass -File .\nightly_all.ps1
# =============================================================================

$BASE    = "https://web-production-4d5c0.up.railway.app/api/admin"
$headers = @{ "X-Admin-Key" = "Amu'Semois_R&R.2026" }
$startTime = Get-Date

function Call-Api {
    param([string]$Method, [string]$Url, [int]$Timeout = 900, [int]$Retries = 2)
    for ($attempt = 1; $attempt -le ($Retries + 1); $attempt++) {
        try {
            $r = Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -TimeoutSec $Timeout
            return $r
        } catch {
            $msg = $_.Exception.Message
            $isRetryable = $msg -match "fermee|closed|timeout|expired|connexion"
            if ($isRetryable -and $attempt -le $Retries) {
                Write-Host "  RETRY $attempt/$Retries (waiting 10s): $msg" -ForegroundColor Yellow
                Start-Sleep -Seconds 10
            } else {
                Write-Host "  ERROR: $msg" -ForegroundColor Red
                return $null
            }
        }
    }
    return $null
}

function Show-Elapsed {
    $mins = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 1)
    Write-Host "  [elapsed: ${mins}min]" -ForegroundColor DarkGray
}

# =====================================================================
# STEP 1 - Daily import (BOSA + TED, split to avoid timeout)
# =====================================================================
Write-Host "`n========== STEP 1/8 - Daily Import (BOSA + TED, 3 jours) ==========" -ForegroundColor Cyan

$urlBosa = "$BASE/bulk-import?sources=BOSA" + "&page_size=250&max_pages=30" + "&run_backfill=false&run_matcher=false"
$r = Call-Api "POST" $urlBosa 900
if ($r -and $r.sources.bosa) {
    $b = $r.sources.bosa
    Write-Host "  BOSA: api=$($b.api_total_count) created=$($b.total_created) updated=$($b.total_updated)" -ForegroundColor Green
}
Show-Elapsed

$urlTed = "$BASE/bulk-import?sources=TED" + "&ted_days_back=3&page_size=250&max_pages=30" + "&run_backfill=false&run_matcher=false"
$r = Call-Api "POST" $urlTed 900
if ($r -and $r.sources.ted) {
    $t = $r.sources.ted
    Write-Host "  TED:  api=$($t.api_total_count) created=$($t.total_created) updated=$($t.total_updated)" -ForegroundColor Green
}
Show-Elapsed

# =====================================================================
# STEP 2 - Backfill enrichment (raw_data -> structured fields)
# =====================================================================
Write-Host "`n========== STEP 2/8 - Backfill (raw_data -> champs) ==========" -ForegroundColor Cyan

$bfTotal = 0
for ($bfPass = 1; $bfPass -le 3; $bfPass++) {
    $url2 = "$BASE/backfill?limit=3000" + "&refresh_vectors=false"
    $r = Call-Api "POST" $url2 900
    if (-not $r) { break }
    $enriched = if ($r.enriched) { $r.enriched } else { 0 }
    $bfTotal += $enriched
    Write-Host "  Pass $bfPass : enriched=$enriched processed=$($r.processed)" -ForegroundColor Green
    if ($enriched -eq 0) { break }
}
if ($bfTotal -gt 0) {
    $url2v = "$BASE/backfill?limit=1" + "&refresh_vectors=true"
    Call-Api "POST" $url2v 900 | Out-Null
    Write-Host "  Search vectors refreshed" -ForegroundColor Green
}
Write-Host "  Backfill total: $bfTotal" -ForegroundColor Cyan
Show-Elapsed

# =====================================================================
# STEP 3 - TED CAN enrich (loop 500/batch with retry)
# =====================================================================
Write-Host "`n========== STEP 3/8 - TED CAN Enrich (boucle auto) ==========" -ForegroundColor Cyan

$urlTedDry = "$BASE/ted-can-enrich?limit=500" + "&dry_run=true"
$dry = Call-Api "POST" $urlTedDry
if ($dry) {
    Write-Host "  Eligible: $($dry.total_candidates) notices with country-code-only winners" -ForegroundColor Yellow
}

$tedPass = 0
$tedTotal = 0
$tedFails = 0
$urlTedExec = "$BASE/ted-can-enrich?limit=500" + "&batch_size=10&api_delay_ms=500&dry_run=false"
do {
    $tedPass++
    Write-Host "`n  Pass $tedPass..." -ForegroundColor Yellow
    $r = Call-Api "POST" $urlTedExec 900 2
    if (-not $r) {
        $tedFails++
        if ($tedFails -ge 3) { Write-Host "  3 failures, stopping TED CAN" -ForegroundColor Red; break }
        Write-Host "  Will retry after pause..." -ForegroundColor Yellow
        Start-Sleep -Seconds 15
        continue
    }
    $tedFails = 0

    $enriched = if ($r.enriched) { $r.enriched } else { 0 }
    $candidates = if ($r.total_candidates) { $r.total_candidates } else { 0 }
    $tedTotal += $enriched
    Write-Host "  Candidates: $candidates | Enriched: $enriched | Still country-only: $($r.still_country_only) | Total so far: $tedTotal" -ForegroundColor Green
    Show-Elapsed

    if ($enriched -eq 0 -and $candidates -eq 0) { Write-Host "  Done." -ForegroundColor Green; break }
    if ($candidates -lt 500) { Write-Host "  Last batch, done." -ForegroundColor Green; break }
    Start-Sleep -Seconds 3
} while ($true)

Write-Host "  TED CAN enrich total: $tedTotal" -ForegroundColor Cyan

# =====================================================================
# STEP 4 - BOSA enrich Awards (XML) - ONE pass only
# =====================================================================
Write-Host "`n========== STEP 4/8 - BOSA Enrich Awards (XML - 1 pass) ==========" -ForegroundColor Cyan

$urlBosaXml = "$BASE/bosa-enrich-awards?limit=50000" + "&batch_size=1000&dry_run=false"
$r = Call-Api "POST" $urlBosaXml 900
if ($r) {
    Write-Host "  Enriched: $($r.enriched) | Skipped: $($r.skipped) | Errors: $($r.errors)" -ForegroundColor Green
}
Show-Elapsed

# =====================================================================
# STEP 5 - BOSA enrich awards via API (main worker, with retry)
# =====================================================================
Write-Host "`n========== STEP 5/8 - BOSA Enrich via API (boucle auto) ==========" -ForegroundColor Cyan

$urlBosaApiDry = "$BASE/bosa-enrich-awards-via-api?limit=1" + "&dry_run=true"
$dry = Call-Api "POST" $urlBosaApiDry
if ($dry) {
    Write-Host "  Eligible: $($dry.total_eligible) flat BOSA CANs" -ForegroundColor Yellow
    if ($dry.estimated_time_minutes) {
        Write-Host "  Estimated time for 500: ~$($dry.estimated_time_minutes) min" -ForegroundColor Yellow
    }
}

$bosaApiTotal = 0
$bosaApiFails = 0
$bosaApiPass = 0
$urlBosaApiExec = "$BASE/bosa-enrich-awards-via-api?limit=500" + "&batch_size=50&api_delay_ms=300&dry_run=false"
do {
    $bosaApiPass++
    Write-Host "`n  Pass $bosaApiPass..." -ForegroundColor Yellow
    $r = Call-Api "POST" $urlBosaApiExec 900 2
    if (-not $r) {
        $bosaApiFails++
        if ($bosaApiFails -ge 3) { Write-Host "  3 consecutive failures, stopping BOSA API" -ForegroundColor Red; break }
        Write-Host "  Will retry after 15s pause..." -ForegroundColor Yellow
        Start-Sleep -Seconds 15
        continue
    }
    $bosaApiFails = 0

    $enriched = if ($r.enriched) { $r.enriched } else { 0 }
    $apiErr = if ($r.api_errors) { $r.api_errors } else { 0 }
    $bosaApiTotal += $enriched
    Write-Host "  Enriched: $enriched | API errors: $apiErr | Total: $bosaApiTotal" -ForegroundColor Green
    Show-Elapsed

    if ($enriched -eq 0) { Write-Host "  No more, done." -ForegroundColor Green; break }
    Start-Sleep -Seconds 5
} while ($bosaApiPass -lt 100)

# =====================================================================
# STEP 6 - Merge + cleanup orphan CANs
# =====================================================================
Write-Host "`n========== STEP 6/8 - Merge and Cleanup Orphan CANs ==========" -ForegroundColor Cyan

$mergeTotal = 0
$mergePass = 0
$urlMerge = "$BASE/merge-cans?limit=5000" + "&dry_run=false"
do {
    $mergePass++
    $r = Call-Api "POST" $urlMerge
    if (-not $r) { break }

    $merged = if ($r.merged) { $r.merged } else { 0 }
    $mergeTotal += $merged
    Write-Host "  Merge pass $mergePass : merged=$merged scanned=$($r.total_scanned)" -ForegroundColor Green

    if ($merged -eq 0 -or $r.total_scanned -lt 5000) { break }
    Start-Sleep -Seconds 1
} while ($mergePass -lt 10)
Write-Host "  Total merged: $mergeTotal" -ForegroundColor Cyan

Write-Host "`n  Cleanup orphan CANs..." -ForegroundColor Yellow
$urlCleanDry = "$BASE/cleanup-orphan-cans?limit=50000" + "&dry_run=true"
$dry = Call-Api "POST" $urlCleanDry
if ($dry -and $dry.deleted -and $dry.deleted -gt 0) {
    Write-Host "  Dry run: would delete $($dry.deleted) orphan CANs" -ForegroundColor Yellow
    $urlClean = "$BASE/cleanup-orphan-cans?limit=50000" + "&dry_run=false"
    $r = Call-Api "POST" $urlClean
    if ($r) { Write-Host "  Deleted: $($r.deleted)" -ForegroundColor Green }
} else {
    Write-Host "  No orphan CANs to clean up." -ForegroundColor Green
}
Show-Elapsed

# =====================================================================
# STEP 7 - TED Document Backfill (catalog URLs from raw_data)
# Creates notice_documents records from TED raw_data links.pdf URLs.
# NO download — just cataloging so docs appear in the UI.
# =====================================================================
Write-Host "`n========== STEP 7/8 - TED Document Backfill (catalogage) ==========" -ForegroundColor Cyan

$backfillCreated = 0
$backfillProcessed = 0
$backfillDry = Call-Api "POST" "$BASE/backfill-ted-documents?dry_run=true"
if ($backfillDry) {
    $tedBfTotal = $backfillDry.ted_notices_total
    $tedPdfs = $backfillDry.ted_pdf_documents
    Write-Host "  TED notices: $tedBfTotal | Already have PDF docs: $tedPdfs" -ForegroundColor Yellow

    $needsBackfill = $tedBfTotal - [math]::Floor($tedPdfs / 1)
    if ($needsBackfill -gt 100) {
        Write-Host "  Running backfill..." -ForegroundColor Yellow
        $backfillPass = 0
        $maxBackfillPasses = 50

        do {
            $backfillPass++
            Write-Host "  Pass $backfillPass/$maxBackfillPasses..." -ForegroundColor Yellow
            $r = Call-Api "POST" "$BASE/backfill-ted-documents?limit=2000&dry_run=false" 120 2
            if (-not $r) {
                Write-Host "  Backfill call failed, stopping" -ForegroundColor Red
                break
            }
            $processed = if ($r.processed) { $r.processed } else { 0 }
            $created = if ($r.documents_created) { $r.documents_created } else { 0 }
            $backfillProcessed += $processed
            $backfillCreated += $created
            Write-Host "  +$processed notices, +$created docs (total: $backfillProcessed / $backfillCreated)" -ForegroundColor Green

            if ($processed -lt 2000) {
                Write-Host "  Backfill complete! No more notices to process." -ForegroundColor Green
                break
            }
            Start-Sleep -Seconds 2
        } while ($backfillPass -lt $maxBackfillPasses)

        Write-Host "  Backfill done: $backfillProcessed notices, $backfillCreated new document records" -ForegroundColor Cyan
    } else {
        Write-Host "  Backfill already caught up, skipping." -ForegroundColor Green
    }
}
Show-Elapsed

# =====================================================================
# STEP 8 - Watchlist matcher + Rescore
# =====================================================================
Write-Host "`n========== STEP 8/8 - Watchlist Matcher + Rescore ==========" -ForegroundColor Cyan

$r = Call-Api "POST" "$BASE/match-watchlists" 900 2
if ($r) {
    Write-Host "  Matcher: watchlists=$($r.watchlists_processed) new_matches=$($r.total_new_matches) emails=$($r.emails_sent)" -ForegroundColor Green
}

$urlRescore = "$BASE/rescore-all-matches?dry_run=false"
$r = Call-Api "POST" $urlRescore 900 2
if ($r) {
    Write-Host "  Rescore: updated=$($r.updated)/$($r.total_matches) errors=$($r.errors)" -ForegroundColor Green
}
Show-Elapsed

# =====================================================================
# DONE
# =====================================================================
$elapsed = [math]::Round(((Get-Date) - $startTime).TotalMinutes, 1)
Write-Host "`n========== NIGHTLY ALL-IN-ONE COMPLETE - ${elapsed} min ==========" -ForegroundColor Green
Write-Host "  Backfill:        $bfTotal enriched" -ForegroundColor White
Write-Host "  TED enrich:      $tedTotal notices updated" -ForegroundColor White
Write-Host "  BOSA API:        $bosaApiTotal notices enriched" -ForegroundColor White
Write-Host "  CANs merged:     $mergeTotal" -ForegroundColor White
Write-Host "  TED doc catalog: $backfillCreated new records" -ForegroundColor White
Write-Host "  Watchlists:      matched + rescored" -ForegroundColor White
Write-Host "  PDF downloads:   on-demand via UI (not nightly)" -ForegroundColor DarkGray
