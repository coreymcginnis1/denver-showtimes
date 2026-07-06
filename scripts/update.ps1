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

# The scrape prints a "new titles since last run" digest — eyeball it for any that need a
# cleanup rule in config.toml before it publishes.
& .\.venv\Scripts\python.exe -m movie_scraper
if ($LASTEXITCODE -ne 0) { Write-Error "Scrape failed."; exit 1 }

git add public/data.json known_titles.txt
if (git status --porcelain public/data.json known_titles.txt) {
    git commit -m "Update showtimes $(Get-Date -Format 'yyyy-MM-dd')"
    # git push uses whichever GitHub account gh has active; force the personal one.
    gh auth switch --user coreymcginnis1 2>$null
    git push
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nShowtimes updated and pushed - the site will redeploy shortly."
    } else {
        Write-Error "Push failed - run 'gh auth status'; the active account needs write access to coreymcginnis1/denver-showtimes."
    }
} else {
    Write-Host "`nNo change in showtimes; nothing to push."
}
