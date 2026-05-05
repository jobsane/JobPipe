$ErrorActionPreference = "Stop"

$repo = (git rev-parse --show-toplevel).Trim()
if (-not $repo) {
    throw "Run this from inside the Jobpipe repository."
}

git -C $repo config core.hooksPath .githooks

Write-Host "Installed GitNexus hooks for this worktree."
Write-Host "Hooks run quietly after commit, checkout, and merge."
Write-Host "Log: .git/gitnexus-hook.log"

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo "scripts\gitnexus-sync.ps1") -RepoPath $repo -Trigger install
