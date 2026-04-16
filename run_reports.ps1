param(
    [string]$OutRuns = ".\out_runs",
    [string]$Reports = ".\reports",
    [string]$Decisions = "",
    [int]$Limit = 0,
    [switch]$IncludeExpired,
    [switch]$IncludeDescription,
    [int]$DescMaxChars = 4000
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

$argsList = @(
    "-m", "jobpipe.cli.sync_evaluations",
    "--out", $OutRuns,
    "--reports", $Reports,
    "--detailed-report"
)

if (-not $IncludeExpired) {
    $argsList += "--only-non-expired"
}

if ($Decisions) {
    $argsList += @("--decisions", $Decisions)
}

if ($Limit -gt 0) {
    $argsList += @("--limit", "$Limit")
}

if ($IncludeDescription) {
    $argsList += @("--include-description", "--desc-max-chars", "$DescMaxChars")
}

Write-Host ""
Write-Host "=== JobPipe Reports ===" -ForegroundColor Cyan
Write-Host "Out runs:  $OutRuns"
Write-Host "Reports:   $Reports"
if ($Decisions) {
    Write-Host "Decisions: $Decisions"
}
if (-not $IncludeExpired) {
    Write-Host "Filter:    only non-expired jobs"
}
if ($Limit -gt 0) {
    Write-Host "Limit:     $Limit"
}
if ($IncludeDescription) {
    Write-Host "Include:   truncated description snippets"
}
Write-Host ""

& $py @argsList

if ($LASTEXITCODE -ne 0) {
    Write-Error "sync_evaluations detailed report failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. Check .\reports for the generated files." -ForegroundColor Green
