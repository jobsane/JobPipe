param(
    [string]$RepoPath = ".",
    [string]$Trigger = "manual",
    [string]$LogFile,
    [string]$LockFile,
    [switch]$Force,
    [switch]$Embeddings
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message)
    if ($LogFile) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -LiteralPath $LogFile -Value "[$timestamp] $Message"
    }
    else {
        Write-Host $Message
    }
}

try {
    if ($LockFile) {
        New-Item -ItemType File -Path $LockFile -Force | Out-Null
    }

    $repo = (git -C $RepoPath rev-parse --show-toplevel).Trim()
    $composeFile = Join-Path $repo "docker-compose.gitnexus.yml"
    $analyzeScript = Join-Path $repo "scripts\gitnexus-analyze.ps1"

    Write-Log "GitNexus sync started ($Trigger): $repo"

    docker volume create gitnexus-data | Out-Null

    if (Test-Path -LiteralPath $composeFile) {
        docker compose -f $composeFile up -d | Out-Null
        Write-Log "GitNexus Docker services ensured."
    }

    $analyzeArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $analyzeScript, "-RepoPath", $repo)
    if ($Force) {
        $analyzeArgs += "-Force"
    }
    if ($Embeddings) {
        $analyzeArgs += "-Embeddings"
    }

    & powershell.exe @analyzeArgs 2>&1 | ForEach-Object { Write-Log $_.ToString() }
    if ($LASTEXITCODE -ne 0) {
        throw "GitNexus analyze failed with exit code $LASTEXITCODE."
    }

    Write-Log "GitNexus sync finished."
}
catch {
    Write-Log "GitNexus sync failed: $($_.Exception.Message)"
}
finally {
    if ($LockFile -and (Test-Path -LiteralPath $LockFile)) {
        Remove-Item -LiteralPath $LockFile -Force
    }
}
