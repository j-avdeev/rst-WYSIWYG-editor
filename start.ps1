# rst WYSIWYG editor - launcher for end users (no Node required).
# Usage: powershell -File start.ps1 -Root "C:\path\to\sphinx\source" [-Port 8010]
# The Sphinx source dir is the folder that contains conf.py.
param(
    [string]$Root = "",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
    Write-Host "Usage: powershell -File start.ps1 -Root `"C:\path\to\sphinx\source`" [-Port 8010]"
    Write-Host "  -Root must point at your Sphinx source directory (the one containing conf.py)."
    exit 1
}
if (-not (Test-Path (Join-Path $Root "conf.py"))) {
    Write-Host "WARNING: no conf.py found in '$Root'."
    Write-Host "The editor will still open, but 'Build & view' needs a Sphinx source dir."
}

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Host "The 'uv' tool is required (it manages Python automatically)."
    Write-Host "Install it once with:  winget install astral-sh.uv"
    Write-Host "...then re-run this script."
    exit 1
}

# frontend location: release layout (frontend-dist next to this script)
# or source checkout layout (frontend\dist)
$dist = Join-Path $PSScriptRoot "frontend-dist"
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    $dist = Join-Path $PSScriptRoot "frontend\dist"
}
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    Write-Host "Frontend build not found. In a source checkout run:"
    Write-Host "  cd frontend; pnpm install; pnpm build"
    exit 1
}

$env:RSTKIT_ROOT = $Root
$env:RSTKIT_FRONTEND_DIST = $dist

Write-Host "Docs root : $Root"
Write-Host "Frontend  : $dist"
Write-Host "Starting the editor on http://localhost:$Port  (first run downloads Python packages - please wait)"

$backendDir = Join-Path $PSScriptRoot "backend"
$server = Start-Process -FilePath "uv" `
    -ArgumentList "run", "uvicorn", "app.main:app", "--port", "$Port" `
    -WorkingDirectory $backendDir `
    -PassThru -NoNewWindow

# open the browser once the server responds
$opened = $false
for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 1
    if ($server.HasExited) { break }
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:$Port/api/health" -UseBasicParsing -TimeoutSec 2
        Start-Process "http://localhost:$Port"
        $opened = $true
        break
    } catch { }
}
if (-not $opened -and -not $server.HasExited) {
    Write-Host "Server is taking long to start; open http://localhost:$Port manually when ready."
}
if ($server.HasExited) {
    Write-Host "Server failed to start (exit code $($server.ExitCode))."
    exit 1
}

Write-Host "Editor is running. Press Ctrl+C in this window to stop it."
Wait-Process -Id $server.Id
