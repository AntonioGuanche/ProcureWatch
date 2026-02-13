# =============================================================================
# ProcureWatch - Nightly All-in-One v4
# v4: added TED doc download (Step 8) + Q&A endpoint backend
# v3: added BOSA document crawl (Step 7) - PDF download + text extraction
# v2: higher timeouts, retry on connection errors, skip BOSA XML loop
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
Write-Host "`n========== STEP 1/9 - Daily Import (BOSA + TED, 3 jours) ==========" -ForegroundColor Cyan

$urlBosa = "$BASE/bulk-import?sources=BOSA" + "&page_size=250&max_pages=20" + "&run_backfill=false&run_matcher=false"
$r = Call-Api "POST" $urlBosa 900
if ($r -and $r.sources.bosa) {
    $b = $r.sources.bosa
    Write-Host "  BOSA: api=$($b.api_total_count) created=$($b.total_created) updated=$($b.total_updated)" -ForegroundColor Green
}
Show-Elapsed

$urlTed = "$BASE/bulk-import?sources=TED" + "&ted_days_back=3&page_size=250&max_pages=20" + "&run_backfill=false&run_matcher=false"
$r = Call-Api "POST" $urlTed 900
if ($r -and $r.sources.ted) {
    $t = $r.sources.ted
    Write-Host "  TED:  api=$($t.api_total_count) created=$($t.total_created) updated=$($t.total_updated)" -ForegroundColor Green
}
Show-Elapsed

# =====================================================================
# STEP 2 - Backfill enrichment (smaller batches)
# =====================================================================
Write-Host "`n========== STEP 2/9 - Backfill (raw_data -> champs) ==========" -ForegroundColor Cyan

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
Write-Host "`n========== STEP 3/9 - TED CAN Enrich (boucle auto) ==========" -ForegroundColor Cyan

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
# STEP 4 - BOSA enrich awards (XML) - ONE pass only
# v1 showed only 7/5000 have XML - looping re-scans same skipped rows
# =====================================================================
Write-Host "`n========== STEP 4/9 - BOSA Enrich Awards (XML - 1 pass) ==========" -ForegroundColor Cyan

$urlBosaXml = "$BASE/bosa-enrich-awards?limit=50000" + "&batch_size=1000&dry_run=false"
$r = Call-Api "POST" $urlBosaXml 900
if ($r) {
    Write-Host "  Enriched: $($r.enriched) | Skipped: $($r.skipped) | Errors: $($r.errors)" -ForegroundColor Green
}
Show-Elapsed

# =====================================================================
# STEP 5 - BOSA enrich awards via API (main worker, with retry)
# This is the heavy step: ~39K CANs, ~500/pass, ~4min/pass
# =====================================================================
Write-Host "`n========== STEP 5/9 - BOSA Enrich via API (boucle auto) ==========" -ForegroundColor Cyan

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
Write-Host "`n========== STEP 6/9 - Merge and Cleanup Orphan CANs ==========" -ForegroundColor Cyan

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
# STEP 7 - BOSA Document Crawl (PDF download + text extraction)
# ~1 sec/notice, 1000/pass, loop until done or 3 consecutive failures
# Endpoint max is 1000/call — we loop to process up to 5000/night
# =====================================================================
Write-Host "`n========== STEP 7/9 - BOSA Document Crawl (PDFs) ==========" -ForegroundColor Cyan

$urlCrawlDry = "$BASE/crawl-portal-documents?limit=1000&dry_run=true"
$dry = Call-Api "POST" $urlCrawlDry
if ($dry) {
    Write-Host "  Eligible: $($dry.total_eligible) BOSA notices without PDFs" -ForegroundColor Yellow
}

$crawlTotal = 0
$crawlPdfs = 0
$crawlText = 0
$crawlErrors = 0
$crawlFails = 0
$crawlPass = 0
$maxCrawlPasses = 5   # 5 x 1000 = 5000 notices max per night

do {
    $crawlPass++
    Write-Host "`n  Pass $crawlPass/$maxCrawlPasses..." -ForegroundColor Yellow
    $urlCrawl = "$BASE/crawl-portal-documents?limit=1000&source=BOSA_EPROC&download=true&dry_run=false"
    $r = Call-Api "POST" $urlCrawl 900 2
    if (-not $r) {
        $crawlFails++
        if ($crawlFails -ge 3) { Write-Host "  3 consecutive failures, stopping crawl" -ForegroundColor Red; break }
        Write-Host "  Will retry after 15s pause..." -ForegroundColor Yellow
        Start-Sleep -Seconds 15
        continue
    }
    $crawlFails = 0

    $processed = if ($r.notices_processed) { $r.notices_processed } else { 0 }
    $pdfs = if ($r.pdfs_downloaded) { $r.pdfs_downloaded } else { 0 }
    $withText = if ($r.pdfs_with_text) { $r.pdfs_with_text } else { 0 }
    $errs = if ($r.errors) { $r.errors } else { 0 }
    $crawlTotal += $processed
    $crawlPdfs += $pdfs
    $crawlText += $withText
    $crawlErrors += $errs

    Write-Host "  Processed: $processed | PDFs: $pdfs | With text: $withText | Errors: $errs | Running total: $crawlTotal" -ForegroundColor Green
    Show-Elapsed

    # Stop if no more eligible notices
    if ($processed -eq 0) { Write-Host "  No more notices to crawl, done." -ForegroundColor Green; break }
    # Stop if pass yielded nothing useful (all skipped or all errors)
    if ($pdfs -eq 0 -and $errs -eq 0) { Write-Host "  No PDFs found this pass, done." -ForegroundColor Green; break }
    Start-Sleep -Seconds 5
} while ($crawlPass -lt $maxCrawlPasses)

Write-Host "  Document crawl total: $crawlTotal notices, $crawlPdfs PDFs, $crawlText with text" -ForegroundColor Cyan
Show-Elapsed

# =====================================================================
# STEP 8 - TED Document Download + Text Extraction
# Picks up TED documents already in notice_documents (URLs from import)
# and downloads/extracts text from PDFs
# =====================================================================
Write-Host "`n========== STEP 8/9 - TED Document Download (PDFs) ==========" -ForegroundColor Cyan

$urlTedDocDry = "$BASE/batch-download-documents?source=TED_EU&limit=500&dry_run=true"
$dry = Call-Api "POST" $urlTedDocDry
if ($dry) {
    Write-Host "  Eligible: $($dry.total_eligible) TED PDF documents without text" -ForegroundColor Yellow
}

$tedDocTotal = 0
$tedDocDownloaded = 0
$tedDocExtracted = 0
$tedDocFails = 0
$tedDocPass = 0
$maxTedDocPasses = 3   # 3 x 500 = 1500 docs max per night

do {
    $tedDocPass++
    Write-Host "`n  Pass $tedDocPass/$maxTedDocPasses..." -ForegroundColor Yellow
    $urlTedDoc = "$BASE/batch-download-documents?source=TED_EU&limit=500&dry_run=false"
    $r = Call-Api "POST" $urlTedDoc 900 2
    if (-not $r) {
        $tedDocFails++
        if ($tedDocFails -ge 3) { Write-Host "  3 consecutive failures, stopping TED docs" -ForegroundColor Red; break }
        Write-Host "  Will retry after 15s pause..." -ForegroundColor Yellow
        Start-Sleep -Seconds 15
        continue
    }
    $tedDocFails = 0

    $attempted = if ($r.attempted) { $r.attempted } else { 0 }
    $downloaded = if ($r.downloaded) { $r.downloaded } else { 0 }
    $extracted = if ($r.extracted) { $r.extracted } else { 0 }
    $tedDocTotal += $attempted
    $tedDocDownloaded += $downloaded
    $tedDocExtracted += $extracted

    Write-Host "  Attempted: $attempted | Downloaded: $downloaded | Extracted: $extracted | Running total: $tedDocTotal" -ForegroundColor Green
    Show-Elapsed

    if ($attempted -eq 0) { Write-Host "  No more TED docs to process, done." -ForegroundColor Green; break }
    Start-Sleep -Seconds 3
} while ($tedDocPass -lt $maxTedDocPasses)

Write-Host "  TED docs total: $tedDocTotal attempted, $tedDocDownloaded downloaded, $tedDocExtracted with text" -ForegroundColor Cyan
Show-Elapsed

# =====================================================================
# STEP 9 - Watchlist matcher + Rescore
# =====================================================================
Write-Host "`n========== STEP 9/9 - Watchlist Matcher + Rescore ==========" -ForegroundColor Cyan

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
Write-Host "  Backfill:     $bfTotal enriched" -ForegroundColor White
Write-Host "  TED enrich:   $tedTotal notices updated" -ForegroundColor White
Write-Host "  BOSA API:     $bosaApiTotal notices enriched" -ForegroundColor White
Write-Host "  CANs merged:  $mergeTotal" -ForegroundColor White
Write-Host "  BOSA docs:    $crawlPdfs PDFs ($crawlText with text) from $crawlTotal notices" -ForegroundColor White
Write-Host "  TED docs:     $tedDocDownloaded downloaded ($tedDocExtracted with text)" -ForegroundColor White
Write-Host "  Watchlists:   matched + rescored" -ForegroundColor White
