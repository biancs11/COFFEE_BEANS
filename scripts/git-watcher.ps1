# =============================================================================
#  Coffee Bean Sorting System — Git Auto-Refresh Watcher
#  Monitors BOTH:
#    1. GitHub remote (origin/main) — polls every 30 seconds via git fetch
#    2. Local file changes          — instant via .NET FileSystemWatcher
#
#  On change detected:
#    - Pulls latest code (if remote change)
#    - Reinstalls pip deps if requirements.txt changed
#    - Reinstalls npm deps if package.json changed
#    - Restarts only the affected server (backend / frontend / both)
#    - Browser auto-refreshes via Vite HMR (frontend) or full reload signal
#
#  Usage (called by START_AUTO.bat — do not run directly unless debugging):
#    powershell -ExecutionPolicy Bypass -File scripts\git-watcher.ps1
# =============================================================================

param(
    [string]$ProjectDir  = (Split-Path $PSScriptRoot -Parent),
    [string]$Branch      = "main",
    [int]   $PollSeconds = 30
)

Set-Location $ProjectDir

# ── Colour helpers ────────────────────────────────────────────────────────────
function Log-Info  ([string]$msg) { Write-Host "[WATCHER] $msg" -ForegroundColor Cyan    }
function Log-Ok    ([string]$msg) { Write-Host "[WATCHER] $msg" -ForegroundColor Green   }
function Log-Warn  ([string]$msg) { Write-Host "[WATCHER] $msg" -ForegroundColor Yellow  }
function Log-Change([string]$msg) { Write-Host "[CHANGE ] $msg" -ForegroundColor Magenta }
function Log-Error ([string]$msg) { Write-Host "[ERROR  ] $msg" -ForegroundColor Red     }

# ── Get current git commit hash ───────────────────────────────────────────────
function Get-LocalHash {
    return (git -C $ProjectDir rev-parse HEAD 2>$null).Trim()
}

function Get-RemoteHash {
    # fetch quietly, then read remote branch tip
    git -C $ProjectDir fetch origin $Branch --quiet 2>$null | Out-Null
    return (git -C $ProjectDir rev-parse "origin/$Branch" 2>$null).Trim()
}

# ── Restart helpers ───────────────────────────────────────────────────────────
function Stop-Backend {
    Get-Process | Where-Object { $_.MainWindowTitle -like "*CBS-Backend*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    # Also kill any python uvicorn on port 8000
    $pids = (netstat -ano | Select-String ":8000 ") -replace '.*\s+(\d+)$','$1' |
              Select-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$') { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue }
    }
    Start-Sleep -Seconds 1
}

function Stop-Frontend {
    Get-Process | Where-Object { $_.MainWindowTitle -like "*CBS-Frontend*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    # Kill any node on port 5173
    $pids = (netstat -ano | Select-String ":5173 ") -replace '.*\s+(\d+)$','$1' |
              Select-Object -Unique
    foreach ($p in $pids) {
        if ($p -match '^\d+$') { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue }
    }
    Start-Sleep -Seconds 1
}

function Start-Backend {
    Log-Info "Starting backend on port 8000..."
    $env:PYTHONPATH = $ProjectDir
    $env:APP_ENV    = "development"
    Start-Process cmd.exe -ArgumentList @(
        "/k",
        "title CBS-Backend-DEV && cd /d `"$ProjectDir`" && call venv\Scripts\activate.bat && set PYTHONPATH=$ProjectDir && set APP_ENV=development && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info"
    ) -WindowStyle Minimized
    Log-Ok "Backend started."
}

function Start-Frontend {
    Log-Info "Starting frontend on port 5173..."
    Start-Process cmd.exe -ArgumentList @(
        "/k",
        "title CBS-Frontend-DEV && cd /d `"$ProjectDir\frontend`" && npm run dev"
    ) -WindowStyle Minimized
    Log-Ok "Frontend started."
}

function Install-PipDeps {
    Log-Info "requirements.txt changed — reinstalling pip deps..."
    & "$ProjectDir\venv\Scripts\pip.exe" install -r "$ProjectDir\backend\requirements.txt" --quiet
    Log-Ok "Pip deps updated."
}

function Install-NpmDeps {
    Log-Info "package.json changed — reinstalling npm deps..."
    & npm install --prefix "$ProjectDir\frontend" --silent
    Log-Ok "Npm deps updated."
}

# ── Pull latest from GitHub ───────────────────────────────────────────────────
function Pull-Latest {
    Log-Change "Pulling latest from origin/$Branch..."
    $result = git -C $ProjectDir pull origin $Branch 2>&1
    Log-Info $result
}

# ── Determine which parts changed since a given hash ─────────────────────────
function Get-ChangedAreas ([string]$oldHash) {
    $files = git -C $ProjectDir diff --name-only $oldHash HEAD 2>$null
    $areas = @{ Backend  = $false; Frontend = $false
                PipDeps  = $false; NpmDeps  = $false }
    foreach ($f in $files) {
        if ($f -match '^backend/')                { $areas.Backend  = $true }
        if ($f -match '^frontend/src/')           { $areas.Frontend = $true }
        if ($f -match '^frontend/public/')        { $areas.Frontend = $true }
        if ($f -match 'requirements\.txt')        { $areas.PipDeps  = $true; $areas.Backend  = $true }
        if ($f -match 'package\.json')            { $areas.NpmDeps  = $true; $areas.Frontend = $true }
        if ($f -match '^(\.env|alembic\.ini|migrations/)') { $areas.Backend = $true }
    }
    return $areas
}

# =============================================================================
#  LOCAL FILE WATCHER  — instant reaction to saves in the project tree
# =============================================================================
Log-Info "Setting up local file system watchers..."

# Backend watcher — .py files and .env
$BackendWatcher            = New-Object System.IO.FileSystemWatcher
$BackendWatcher.Path       = "$ProjectDir\backend"
$BackendWatcher.Filter     = "*.py"
$BackendWatcher.IncludeSubdirectories = $true
$BackendWatcher.EnableRaisingEvents   = $true

# Frontend watcher — src folder
$FrontendWatcher            = New-Object System.IO.FileSystemWatcher
$FrontendWatcher.Path       = "$ProjectDir\frontend\src"
$FrontendWatcher.Filter     = "*.*"
$FrontendWatcher.IncludeSubdirectories = $true
$FrontendWatcher.EnableRaisingEvents   = $true

# Requirements watcher
$ReqWatcher            = New-Object System.IO.FileSystemWatcher
$ReqWatcher.Path       = "$ProjectDir\backend"
$ReqWatcher.Filter     = "requirements.txt"
$ReqWatcher.EnableRaisingEvents = $true

# Package.json watcher
$PkgWatcher            = New-Object System.IO.FileSystemWatcher
$PkgWatcher.Path       = "$ProjectDir\frontend"
$PkgWatcher.Filter     = "package.json"
$PkgWatcher.EnableRaisingEvents = $true

# .env watcher (root)
$EnvWatcher            = New-Object System.IO.FileSystemWatcher
$EnvWatcher.Path       = $ProjectDir
$EnvWatcher.Filter     = ".env"
$EnvWatcher.EnableRaisingEvents = $true

# Debounce flags — prevent double-fires within 5 seconds
$script:LastBackendRestart  = [datetime]::MinValue
$script:LastFrontendRestart = [datetime]::MinValue
$script:DebounceSeconds     = 5

$OnBackendChange = {
    param($source, $e)
    $now = [datetime]::Now
    if (($now - $script:LastBackendRestart).TotalSeconds -lt $script:DebounceSeconds) { return }
    $script:LastBackendRestart = $now
    Log-Change "Local backend file changed: $($e.Name)"
    # Uvicorn --reload handles .py restarts automatically; we only need
    # to act if requirements.txt or .env changed (handled by their own watchers)
}

$OnReqChange = {
    param($source, $e)
    $now = [datetime]::Now
    if (($now - $script:LastBackendRestart).TotalSeconds -lt $script:DebounceSeconds) { return }
    $script:LastBackendRestart = $now
    Log-Change "requirements.txt changed locally — updating deps and restarting backend..."
    Install-PipDeps
    Stop-Backend
    Start-Sleep -Seconds 1
    Start-Backend
}

$OnEnvChange = {
    param($source, $e)
    $now = [datetime]::Now
    if (($now - $script:LastBackendRestart).TotalSeconds -lt $script:DebounceSeconds) { return }
    $script:LastBackendRestart = $now
    Log-Change ".env changed locally — restarting backend to reload config..."
    Stop-Backend
    Start-Sleep -Seconds 1
    Start-Backend
}

$OnPkgChange = {
    param($source, $e)
    $now = [datetime]::Now
    if (($now - $script:LastFrontendRestart).TotalSeconds -lt $script:DebounceSeconds) { return }
    $script:LastFrontendRestart = $now
    Log-Change "package.json changed locally — updating npm deps and restarting frontend..."
    Install-NpmDeps
    Stop-Frontend
    Start-Sleep -Seconds 1
    Start-Frontend
}

# Register event handlers
Register-ObjectEvent $BackendWatcher  "Changed" -Action $OnBackendChange | Out-Null
Register-ObjectEvent $BackendWatcher  "Created" -Action $OnBackendChange | Out-Null
Register-ObjectEvent $ReqWatcher      "Changed" -Action $OnReqChange     | Out-Null
Register-ObjectEvent $EnvWatcher      "Changed" -Action $OnEnvChange     | Out-Null
Register-ObjectEvent $PkgWatcher      "Changed" -Action $OnPkgChange     | Out-Null
# Note: frontend/src .jsx/.js/.css changes are handled by Vite HMR automatically
#       so the FrontendWatcher is registered but only reacts to package.json/config

Log-Ok "File watchers active."

# =============================================================================
#  REMOTE POLL LOOP — checks GitHub origin/main every $PollSeconds
# =============================================================================
$localHash = Get-LocalHash
Log-Info "Current commit : $($localHash.Substring(0,8))"
Log-Info "Polling GitHub origin/$Branch every ${PollSeconds}s for new commits..."
Log-Ok  "Watcher is running. Press Ctrl+C to stop."
Write-Host ""

while ($true) {
    Start-Sleep -Seconds $PollSeconds

    $remoteHash = Get-RemoteHash

    if ($remoteHash -ne $localHash) {
        Log-Change "New commit on origin/$Branch detected!"
        Log-Change "  Local  : $($localHash.Substring(0,8))"
        Log-Change "  Remote : $($remoteHash.Substring(0,8))"

        $oldHash = $localHash

        Pull-Latest

        $localHash = Get-LocalHash
        $areas     = Get-ChangedAreas -oldHash $oldHash

        # Install deps first if needed
        if ($areas.PipDeps)  { Install-PipDeps  }
        if ($areas.NpmDeps)  { Install-NpmDeps  }

        # Restart affected servers
        if ($areas.Backend) {
            Log-Change "Backend files changed — restarting backend..."
            Stop-Backend
            Start-Sleep -Seconds 2
            Start-Backend
        }

        if ($areas.Frontend) {
            Log-Change "Frontend files changed — restarting frontend dev server..."
            Stop-Frontend
            Start-Sleep -Seconds 2
            Start-Frontend
        }

        Log-Ok "Update applied. Commit: $($localHash.Substring(0,8))"
        Write-Host ""
    } else {
        # Silent tick — no output unless you want verbose mode
        # Log-Info "No remote changes. ($(Get-Date -Format 'HH:mm:ss'))"
    }
}
