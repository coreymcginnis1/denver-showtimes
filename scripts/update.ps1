# Refresh Denver showtimes and publish.
#
# Run this on your own machine (your home IP scrapes all three theaters, including AMC,
# which blocks GitHub's datacenter IPs). Showtimes turn over Wed/Thu, so once a week is plenty.
# It scrapes -> commits public/data.json (only if it changed) -> pushes. The GitHub Action
# then just deploys what you pushed.
#
#   Run manually:   powershell -ExecutionPolicy Bypass -File scripts\update.ps1
#   Or schedule weekly (see README "Updating showtimes").

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

& .\.venv\Scripts\python.exe -m movie_scraper
if ($LASTEXITCODE -ne 0) { Write-Error "Scrape failed."; exit 1 }

git add public/data.json
if (git status --porcelain public/data.json) {
    git commit -m "Update showtimes $(Get-Date -Format 'yyyy-MM-dd')"
    git push
    Write-Host "`nShowtimes updated and pushed - the site will redeploy shortly."
} else {
    Write-Host "`nNo change in showtimes; nothing to push."
}
