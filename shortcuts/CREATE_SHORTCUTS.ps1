# ============================================================
#  Coffee Bean Sorting System — Create Windows Shortcut Icons
#  Run this once to place shortcuts on your Desktop.
#  Right-click → "Run with PowerShell"
# ============================================================

$ProjectDir = Split-Path $PSScriptRoot -Parent
$ShortcutDir = $PSScriptRoot
$DesktopDir  = [Environment]::GetFolderPath("Desktop")
$WshShell    = New-Object -ComObject WScript.Shell

function New-Shortcut {
    param(
        [string]$Name,
        [string]$Target,
        [string]$Arguments = "",
        [string]$WorkDir,
        [string]$Description,
        [string]$IconPath,
        [int]   $IconIndex = 0,
        [string]$Destination = $DesktopDir
    )

    $lnk = $WshShell.CreateShortcut("$Destination\$Name.lnk")
    $lnk.TargetPath       = $Target
    $lnk.Arguments        = $Arguments
    $lnk.WorkingDirectory = $WorkDir
    $lnk.Description      = $Description
    $lnk.IconLocation     = "$IconPath,$IconIndex"
    $lnk.WindowStyle      = 1
    $lnk.Save()
    Write-Host "Created: $Destination\$Name.lnk"
}

$shell32 = "$env:SystemRoot\System32\shell32.dll"
$cmd     = "$env:SystemRoot\System32\cmd.exe"

# ── 1. START SYSTEM ──────────────────────────────────────────
New-Shortcut `
    -Name        "☕ Start Coffee Sorter" `
    -Target      $cmd `
    -Arguments   "/c `"$ShortcutDir\START_SYSTEM.bat`"" `
    -WorkDir     $ProjectDir `
    -Description "Start the Coffee Bean Sorting System backend and open dashboard" `
    -IconPath    $shell32 `
    -IconIndex   175

# ── 2. STOP SYSTEM ───────────────────────────────────────────
New-Shortcut `
    -Name        "⏹ Stop Coffee Sorter" `
    -Target      $cmd `
    -Arguments   "/c `"$ShortcutDir\STOP_SYSTEM.bat`"" `
    -WorkDir     $ProjectDir `
    -Description "Stop all Coffee Bean Sorting System processes" `
    -IconPath    $shell32 `
    -IconIndex   131

# ── 3. OPEN DASHBOARD ────────────────────────────────────────
New-Shortcut `
    -Name        "🌐 Coffee Sorter Dashboard" `
    -Target      "http://localhost:8000" `
    -Arguments   "" `
    -WorkDir     $ProjectDir `
    -Description "Open Coffee Bean Sorting System dashboard in browser" `
    -IconPath    $shell32 `
    -IconIndex   14

# ── 4. DEV MODE ──────────────────────────────────────────────
New-Shortcut `
    -Name        "🛠 Coffee Sorter DEV" `
    -Target      $cmd `
    -Arguments   "/c `"$ShortcutDir\START_DEV.bat`"" `
    -WorkDir     $ProjectDir `
    -Description "Start Coffee Bean Sorting System in development mode (hot reload)" `
    -IconPath    $shell32 `
    -IconIndex   71

# ── 5. VIEW LOGS ─────────────────────────────────────────────
New-Shortcut `
    -Name        "📋 Coffee Sorter Logs" `
    -Target      $cmd `
    -Arguments   "/c `"$ShortcutDir\VIEW_LOGS.bat`"" `
    -WorkDir     $ProjectDir `
    -Description "View live Coffee Bean Sorting System logs" `
    -IconPath    $shell32 `
    -IconIndex   44

Write-Host ""
Write-Host "======================================================"
Write-Host "  5 shortcuts created on your Desktop!"
Write-Host "  Look for them on your Windows Desktop."
Write-Host "======================================================"
Write-Host ""
Read-Host -Prompt "Press Enter to close"
