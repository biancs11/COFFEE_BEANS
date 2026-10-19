# =============================================================================
#  Coffee Bean Sorting System - Desktop Shortcut Installer
#  Creates ONE shortcut on the Windows Desktop:
#
#    "CoffeeSort Auto-Refresh"
#    Double-click => starts backend + frontend + git watcher,
#                    opens browser, auto-refreshes on any change.
#
#  Run once:  Right-click -> "Run with PowerShell"
# =============================================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Paths --------------------------------------------------------------------
$ProjectDir  = Split-Path $PSScriptRoot -Parent
$LauncherBat = Join-Path $PSScriptRoot "START_AUTO.bat"
$DesktopDir  = [Environment]::GetFolderPath("Desktop")
$Shell32     = "$env:SystemRoot\System32\shell32.dll"
$CmdExe      = "$env:SystemRoot\System32\cmd.exe"
$WshShell    = New-Object -ComObject WScript.Shell

# -- Verify launcher exists ---------------------------------------------------
if (-not (Test-Path $LauncherBat)) {
    Write-Host "[ERROR] Cannot find START_AUTO.bat at:" -ForegroundColor Red
    Write-Host "        $LauncherBat"                   -ForegroundColor Red
    Write-Host "        Make sure you run this from inside the shortcuts\ folder." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

# -- Create shortcut ----------------------------------------------------------
$lnkPath = Join-Path $DesktopDir "CoffeeSort Auto-Refresh.lnk"
$lnk = $WshShell.CreateShortcut($lnkPath)
$lnk.TargetPath       = $CmdExe
$lnk.Arguments        = "/c `"$LauncherBat`""
$lnk.WorkingDirectory = $ProjectDir
$lnk.Description      = "Start Coffee Bean Sorting System with auto-refresh (GitHub + local watch)"
$lnk.IconLocation     = "$Shell32,175"
$lnk.WindowStyle      = 1
$lnk.Save()

# -- Done ---------------------------------------------------------------------
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "   Coffee Bean Sorting System - Desktop Shortcut Installer"    -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  [OK] Shortcut created on your Desktop:" -ForegroundColor Green
Write-Host "       $lnkPath"                          -ForegroundColor White
Write-Host ""
Write-Host "  What happens when you double-click it:" -ForegroundColor Yellow
Write-Host "    1. Pulls latest code from GitHub (origin/main)"
Write-Host "    2. Sets up venv + node_modules if not present"
Write-Host "    3. Starts FastAPI backend  (port 8000, uvicorn --reload)"
Write-Host "    4. Starts Vite dev server  (port 5173, Vite HMR)"
Write-Host "    5. Opens browser at http://localhost:5173"
Write-Host "    6. Watches for changes:"
Write-Host "         Local  : .py / .env  => backend restarts instantly"
Write-Host "                  .jsx/.js/.css => hot-reload via Vite HMR"
Write-Host "         GitHub : new commit pushed to main => pull + smart restart"
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""
