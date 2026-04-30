param(
    [string]$RepoPath = ".",
    [switch]$Force,
    [switch]$Embeddings
)

$repo = (git -C $RepoPath rev-parse --show-toplevel).Trim()
if (-not $repo) {
    throw "Run this from inside a git repository, or pass -RepoPath."
}

$userRoot = [System.IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd("\", "/")
$repoFull = [System.IO.Path]::GetFullPath($repo).TrimEnd("\", "/")

if (-not $repoFull.StartsWith($userRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Repo must be under $userRoot so Docker can expose it as /workspace/<relative-path>."
}

$relative = $repoFull.Substring($userRoot.Length).TrimStart("\", "/")
$containerRepo = "/workspace/" + ($relative -replace "\\", "/")

$gitnexusArgs = @("analyze", $containerRepo, "--skip-agents-md")
if ($Force) {
    $gitnexusArgs += "--force"
}
if ($Embeddings) {
    $gitnexusArgs += "--embeddings"
}

docker run --rm `
    -e "GIT_CONFIG_COUNT=1" `
    -e "GIT_CONFIG_KEY_0=safe.directory" `
    -e "GIT_CONFIG_VALUE_0=*" `
    -v "gitnexus-data:/data/gitnexus" `
    -v "gitnexus-data:/home/node/.gitnexus" `
    -v "${userRoot}:/workspace" `
    ghcr.io/abhigyanpatwari/gitnexus:latest `
    node gitnexus/dist/cli/index.js @gitnexusArgs

docker run --rm `
    -e "GIT_CONFIG_COUNT=1" `
    -e "GIT_CONFIG_KEY_0=safe.directory" `
    -e "GIT_CONFIG_VALUE_0=*" `
    -v "gitnexus-data:/data/gitnexus" `
    -v "gitnexus-data:/home/node/.gitnexus" `
    -v "${userRoot}:/workspace:ro" `
    ghcr.io/abhigyanpatwari/gitnexus:latest `
    node gitnexus/dist/cli/index.js index $containerRepo
