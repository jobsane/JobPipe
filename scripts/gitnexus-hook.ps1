param(
    [string]$Trigger = "hook"
)

$ErrorActionPreference = "SilentlyContinue"

$repo = (git rev-parse --show-toplevel 2>$null).Trim()
if (-not $repo) {
    exit 0
}

$gitDir = (git -C $repo rev-parse --git-common-dir 2>$null).Trim()
if (-not [System.IO.Path]::IsPathRooted($gitDir)) {
    $gitDir = Join-Path $repo $gitDir
}

$lockFile = Join-Path $gitDir "gitnexus-sync.lock"
$logFile = Join-Path $gitDir "gitnexus-hook.log"
$syncScript = Join-Path $repo "scripts\gitnexus-sync.ps1"

if (-not (Test-Path -LiteralPath $syncScript)) {
    exit 0
}

if (Test-Path -LiteralPath $lockFile) {
    $lock = Get-Item -LiteralPath $lockFile
    if ($lock.LastWriteTime -gt (Get-Date).AddMinutes(-10)) {
        exit 0
    }
    Remove-Item -LiteralPath $lockFile -Force
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$syncScript`"",
    "-RepoPath", "`"$repo`"",
    "-Trigger", "`"$Trigger`"",
    "-LogFile", "`"$logFile`"",
    "-LockFile", "`"$lockFile`""
)

Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WindowStyle Hidden | Out-Null
exit 0
