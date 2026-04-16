# JobPipe - one-shot runner
# Usage: .\go.ps1
# Options:
#   .\go.ps1 -DryRun             2 jobs only, no browser (test mode)
#   .\go.ps1 -NoOpen             full run, skip auto-opening browser
#   .\go.ps1 -WithSuggestions    scan Gmail for suggestions + fetch queued FINN jobs
#                                + scrape FINN search by keyword (all daytime only, 09-19 Oslo)

param(
    [switch]$DryRun,
    [switch]$NoOpen,
    [switch]$WithSuggestions
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot          # ensure CWD = project root (editable install needs this)
$py = "$PSScriptRoot\.venv\Scripts\python.exe"

function Import-DotEnv {
    param(
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($raw in Get-Content -LiteralPath $Path) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }

        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        if (-not $key -or [Environment]::GetEnvironmentVariable($key, "Process")) {
            continue
        }

        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

Import-DotEnv (Join-Path $PSScriptRoot ".env")

if (-not (Test-Path $py)) {
    Write-Error "Venv not found at $py - run: python -m venv .venv && .venv\Scripts\pip install -e ."
    exit 1
}

$env:OPENAI_AGENTS_DISABLE_TRACING = "1"
$maxJobs = if ($DryRun) { 2 } else { 100 }
$profilePath = if ($env:JOBPIPE_PROFILE_PATH) {
    $env:JOBPIPE_PROFILE_PATH
} elseif ($env:JOBPIPE_DATA_DIR) {
    Join-Path $env:JOBPIPE_DATA_DIR "profile_pack.md"
} else {
    ".\profile_pack.md"
}

Write-Host ""
Write-Host "=== JobPipe ===" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "Mode: DRY RUN (max 2 jobs)"
} else {
    Write-Host "Mode: FULL RUN (max 100 jobs)"
}
if ($WithSuggestions) {
    Write-Host "Suggestions: ON (FINN/LinkedIn email scan + fetch)"
}
Write-Host ""

# --- Optional: Suggestion intake (FINN/LinkedIn email scan + FINN search scrape) ---
# Only when -WithSuggestions is passed. All three steps have built-in 09:00-19:00 Oslo
# time guards — they exit cleanly if run outside that window.
if ($WithSuggestions) {
    Write-Host "[0a/4] scan_gmail --scan-suggestions (FINN/LinkedIn emails)..." -ForegroundColor Yellow
    & $py -m jobpipe.cli.scan_gmail `
        --scan-suggestions `
        --days 30
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "scan_gmail --scan-suggestions failed (exit $LASTEXITCODE). Continuing."
    }

    Write-Host ""
    Write-Host "[0b/4] pull_suggested (FINN jobs from email queue, daytime only)..." -ForegroundColor Yellow
    & $py -m jobpipe.cli.pull_suggested `
        --max 20
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "pull_suggested failed (exit $LASTEXITCODE). Continuing."
    }

    Write-Host ""
    Write-Host "[0c/4] pull_finn_search (direct FINN keyword search, daytime only)..." -ForegroundColor Yellow
    & $py -m jobpipe.cli.pull_finn_search `
        --config .\configs\pipeline.v1.yaml `
        --max 40
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "pull_finn_search failed (exit $LASTEXITCODE). Continuing."
    }
    Write-Host ""
}

# 1. Pull + process
Write-Host "[1/3] drain_queue..." -ForegroundColor Yellow
& $py -m jobpipe.cli.drain_queue `
    --profile $profilePath `
    --config .\configs\pipeline.v1.yaml `
    --out .\out_runs `
    --state .\jobs_state.json `
    --batch-size $maxJobs `
    --overwrite

if ($LASTEXITCODE -ne 0) {
    Write-Error "drain_queue failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# 2. Sync ledger
Write-Host ""
Write-Host "[2/3] sync_ledger..." -ForegroundColor Yellow
& $py -m jobpipe.cli.sync_ledger `
    --out .\out_runs `
    --sqlite .\reports\ledger.sqlite `
    --csv .\reports\ledger_latest.csv

if ($LASTEXITCODE -ne 0) {
    Write-Error "sync_ledger failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# 3. Rebuild dashboard
Write-Host ""
Write-Host "[3/3] export_dashboard..." -ForegroundColor Yellow
& $py -m jobpipe.cli.export_dashboard

if ($LASTEXITCODE -ne 0) {
    Write-Error "export_dashboard failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green

if (-not $NoOpen -and -not $DryRun) {
    Write-Host "Opening dashboard..." -ForegroundColor Cyan
    Start-Process ".\reports\dashboard.html"
}
