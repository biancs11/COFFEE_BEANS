# ── Quick Git Push Script ────────────────────────────────────────────────────
# Stages all changes, prompts for a commit message, then pushes to GitHub.
# Usage: right-click → "Run with PowerShell"  OR  just double-click it.
# ─────────────────────────────────────────────────────────────────────────────

$GIT = "C:\Users\User\AppData\Local\GitHubDesktop\app-3.6.5\resources\app\git\cmd\git.exe"
$REPO = $PSScriptRoot   # same folder as this script

# ── Colour helpers ───────────────────────────────────────────────────────────
function Info  { param($m) Write-Host "  $m"       -ForegroundColor Cyan    }
function OK    { param($m) Write-Host "  $m"       -ForegroundColor Green   }
function Warn  { param($m) Write-Host "  $m"       -ForegroundColor Yellow  }
function Err   { param($m) Write-Host "  $m"       -ForegroundColor Red     }

Clear-Host
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor DarkYellow
Write-Host "  ║   Coffee Bean Sorter — Quick Git Push    ║" -ForegroundColor DarkYellow
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor DarkYellow
Write-Host ""

# ── Verify git exists ────────────────────────────────────────────────────────
if (-not (Test-Path $GIT)) {
    Err "Git not found at:"
    Err "  $GIT"
    Err ""
    Err "Install Git for Windows from https://git-scm.com/download/win"
    Err "or update the `$GIT path at the top of this script."
    Read-Host "`n  Press Enter to exit"
    exit 1
}

Set-Location $REPO

# ── Show current status ──────────────────────────────────────────────────────
Info "Changed files:"
& $GIT status --short
Write-Host ""

# ── Check if there is anything to commit ─────────────────────────────────────
$changes = & $GIT status --porcelain
if (-not $changes) {
    OK "Nothing to commit — everything is up to date."
    Read-Host "`n  Press Enter to exit"
    exit 0
}

# ── Prompt for commit message ────────────────────────────────────────────────
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$default   = "update: $timestamp"

Write-Host "  Commit message (leave blank to use default):" -ForegroundColor White
Write-Host "  Default: $default" -ForegroundColor DarkGray
$msg = Read-Host "  >"

if ([string]::IsNullOrWhiteSpace($msg)) { $msg = $default }

Write-Host ""

# ── Stage all changes ─────────────────────────────────────────────────────────
Info "Staging all changes..."
& $GIT add .
if ($LASTEXITCODE -ne 0) { Err "git add failed."; Read-Host "Press Enter to exit"; exit 1 }
OK "Staged."

# ── Commit ────────────────────────────────────────────────────────────────────
Info "Committing: `"$msg`""
& $GIT commit -m $msg
if ($LASTEXITCODE -ne 0) { Err "git commit failed."; Read-Host "Press Enter to exit"; exit 1 }
OK "Committed."

# ── Push ─────────────────────────────────────────────────────────────────────
Info "Pushing to GitHub..."
& $GIT push
if ($LASTEXITCODE -ne 0) {
    Warn "Push failed — trying to set upstream branch..."
    $branch = & $GIT rev-parse --abbrev-ref HEAD
    & $GIT push --set-upstream origin $branch
    if ($LASTEXITCODE -ne 0) { Err "Push failed. Check your remote / network."; Read-Host "Press Enter to exit"; exit 1 }
}

Write-Host ""
OK "Done! Changes are live on GitHub."
Write-Host ""
Read-Host "  Press Enter to close"
