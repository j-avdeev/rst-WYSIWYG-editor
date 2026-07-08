# Starts the backend (FastAPI/uvicorn) and frontend (Vite) dev servers.
# Usage: powershell -File scripts\dev.ps1 [-Root <sphinx-source-dir>]
param(
    [string]$Root = "C:\work\pradis-docs-git\docs\pradis-sphinx-doc"
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$env:RSTKIT_ROOT = $Root

Write-Host "RSTKIT_ROOT = $Root"

$backend = Start-Process -FilePath "uv" `
    -ArgumentList "run", "uvicorn", "app.main:app", "--reload", "--port", "8010" `
    -WorkingDirectory (Join-Path $repoRoot "backend") `
    -PassThru -NoNewWindow

$frontendDir = Join-Path $repoRoot "frontend"
if (Test-Path (Join-Path $frontendDir "package.json")) {
    $frontend = Start-Process -FilePath "pnpm" `
        -ArgumentList "dev" `
        -WorkingDirectory $frontendDir `
        -PassThru -NoNewWindow
} else {
    Write-Host "frontend/ not scaffolded yet — backend only (http://localhost:8010)"
    $frontend = $null
}

Write-Host "Backend:  http://localhost:8010/api/health"
if ($frontend) { Write-Host "Frontend: http://localhost:5173" }
Write-Host "Ctrl+C to stop."

try {
    Wait-Process -Id $backend.Id
} finally {
    if ($frontend -and -not $frontend.HasExited) { Stop-Process -Id $frontend.Id -Force }
}
