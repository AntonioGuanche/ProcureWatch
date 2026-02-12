#!/usr/bin/env pwsh
# rescore-matches.ps1 — Recalculate relevance scores for all watchlist matches
# Usage:
#   ./scripts/rescore-matches.ps1                    # dry run
#   ./scripts/rescore-matches.ps1 -Execute            # execute
#   ./scripts/rescore-matches.ps1 -WatchlistId "xxx"  # single watchlist

param(
    [switch]$Execute,
    [string]$WatchlistId = ""
)

$BASE = "https://web-production-4d5c0.up.railway.app"
$KEY  = "Amu'Semois_R&R.2026"
$headers = @{ "X-Admin-Key" = $KEY }

# ── Step 1: Dry run to see current state ──
Write-Host "`n=== Rescore All Matches ===" -ForegroundColor Cyan

$dryRun = if ($Execute) { "false" } else { "true" }
$url = "$BASE/api/admin/rescore-all-matches?dry_run=$dryRun"
if ($WatchlistId) {
    $url += "&watchlist_id=$WatchlistId"
}

Write-Host "URL: $url"
Write-Host "Mode: $(if ($Execute) { 'EXECUTE' } else { 'DRY RUN' })" -ForegroundColor $(if ($Execute) { "Red" } else { "Yellow" })

try {
    $r = Invoke-RestMethod -Uri $url -Method POST -Headers $headers -TimeoutSec 300
    $r | ConvertTo-Json -Depth 3
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $body = $_.Exception.Response.Content.ReadAsStringAsync().Result
        Write-Host $body -ForegroundColor Red
    }
}
