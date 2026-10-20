# ============================================================
#  sync_to_pi.ps1 — Sync Coffee Bean Sorting System to Raspberry Pi
#
#  Called by sync_to_pi.bat, or run directly:
#    powershell -ExecutionPolicy Bypass -File sync_to_pi.ps1
#
#  Requires: OpenSSH client (built into Windows 10/11)
#  SSH key auth recommended (no password prompts during sync)
# ============================================================

param(
    [string]$PiUser    = "coffeebean",
    [string]$PiHost    = "coffeebean.local",
    [string]$PiDir     = "/home/coffeebean/COFFEE_BEANS",
    [switch]$SkipBuild,        # skip npm build on Pi after sync
    [switch]$SkipRestart,      # skip systemctl restart after sync
    [switch]$SetupOnly         # only run setup_rpi.sh, no file sync
)

# ── Colours ──────────────────────────────────────────────────
function Write-Ok   ($msg) { Write-Host "  [OK] $msg"    -ForegroundColor Green  }
function Write-Info ($msg) { Write-Host "  [>>] $msg"    -ForegroundColor Cyan   }
function Write-Warn ($msg) { Write-Host "  [!!] $msg"    -ForegroundColor Yellow }
function Write-Fail ($msg) { Write-Host "  [XX] $msg"    -ForegroundColor Red    }
function Write-Step ($n,$t){ Write-Host "`n  ── Step $n`: $t" -ForegroundColor White }

$SSH = "ssh"
$SCP = "scp"
$SSHTarget = "$PiUser@$PiHost"
$ProjectRoot = $PSScriptRoot   # folder containing this script

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor DarkCyan
Write-Host "   Coffee Bean Sorting System — Sync to Raspberry Pi"          -ForegroundColor Cyan
Write-Host "   Target : $SSHTarget`:$PiDir"                                -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor DarkCyan
Write-Host ""

# ── Helper: run SSH command and capture result ───────────────
function Invoke-SSH {
    param([string]$Cmd, [switch]$ShowOutput)
    if ($ShowOutput) {
        & $SSH -o ConnectTimeout=10 $SSHTarget $Cmd
    } else {
        $out = & $SSH -o ConnectTimeout=10 $SSHTarget $Cmd 2>&1
        return $out
    }
    return $LASTEXITCODE
}

# ── Helper: copy a single file/dir to Pi ────────────────────
function Copy-ToPi {
    param([string]$LocalPath, [string]$RemotePath, [switch]$Recursive)
    $flags = if ($Recursive) { "-r" } else { "" }
    if ($Recursive) {
        & $SCP -r -o ConnectTimeout=10 "$LocalPath" "$SSHTarget`:$RemotePath" 2>&1 | Out-Null
    } else {
        & $SCP -o ConnectTimeout=10 "$LocalPath" "$SSHTarget`:$RemotePath" 2>&1 | Out-Null
    }
    return $LASTEXITCODE
}

# ════════════════════════════════════════════════════════════
# STEP 1 — Verify SSH connection
# ════════════════════════════════════════════════════════════
Write-Step 1 "Verifying SSH connection"
$test = & $SSH -o ConnectTimeout=8 $SSHTarget "echo OK" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Cannot reach $SSHTarget"
    Write-Warn "Tip: Set up key auth so no password is needed:"
    Write-Host "       ssh-keygen -t ed25519 -C coffeebean-sync" -ForegroundColor DarkGray
    Write-Host "       type `$env:USERPROFILE\.ssh\id_ed25519.pub | ssh $SSHTarget 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'" -ForegroundColor DarkGray
    exit 1
}
Write-Ok "SSH connection verified"

# ════════════════════════════════════════════════════════════
# STEP 2 — Create remote directory structure
# ════════════════════════════════════════════════════════════
Write-Step 2 "Creating remote directory structure"
Invoke-SSH "mkdir -p $PiDir/backend/api $PiDir/backend/core $PiDir/frontend/src $PiDir/scripts $PiDir/migrations $PiDir/data/training/grade1 $PiDir/data/training/grade2 $PiDir/data/training/grade3 $PiDir/data/training/grade4 $PiDir/logs"
Write-Ok "Remote directories ready"

# ════════════════════════════════════════════════════════════
# STEP 3 — Sync files (via SCP, with exclusions)
#   Excluded: venv/, node_modules/, frontend/dist/, data/coffee_sorter.db,
#             logs/, .git/, __pycache__/, *.pyc, .env (keep Pi's own .env)
# ════════════════════════════════════════════════════════════
Write-Step 3 "Syncing project files"

# Files/dirs to sync and their descriptions
$syncItems = @(
    # Backend Python source
    @{ local="$ProjectRoot\backend\main.py";                   remote="$PiDir/backend/main.py";                   desc="backend/main.py" },
    @{ local="$ProjectRoot\backend\requirements.txt";          remote="$PiDir/backend/requirements.txt";          desc="backend/requirements.txt" },
    @{ local="$ProjectRoot\backend\api\routes.py";             remote="$PiDir/backend/api/routes.py";             desc="backend/api/routes.py" },
    @{ local="$ProjectRoot\backend\api\websocket.py";          remote="$PiDir/backend/api/websocket.py";          desc="backend/api/websocket.py" },
    @{ local="$ProjectRoot\backend\api\__init__.py";           remote="$PiDir/backend/api/__init__.py";           desc="backend/api/__init__.py" },
    @{ local="$ProjectRoot\backend\core\camera.py";            remote="$PiDir/backend/core/camera.py";            desc="backend/core/camera.py" },
    @{ local="$ProjectRoot\backend\core\config.py";            remote="$PiDir/backend/core/config.py";            desc="backend/core/config.py" },
    @{ local="$ProjectRoot\backend\core\database.py";          remote="$PiDir/backend/core/database.py";          desc="backend/core/database.py" },
    @{ local="$ProjectRoot\backend\core\db_models.py";         remote="$PiDir/backend/core/db_models.py";         desc="backend/core/db_models.py" },
    @{ local="$ProjectRoot\backend\core\db_service.py";        remote="$PiDir/backend/core/db_service.py";        desc="backend/core/db_service.py" },
    @{ local="$ProjectRoot\backend\core\detector.py";          remote="$PiDir/backend/core/detector.py";          desc="backend/core/detector.py" },
    @{ local="$ProjectRoot\backend\core\models.py";            remote="$PiDir/backend/core/models.py";            desc="backend/core/models.py" },
    @{ local="$ProjectRoot\backend\core\sorting_controller.py";remote="$PiDir/backend/core/sorting_controller.py";desc="backend/core/sorting_controller.py" },
    @{ local="$ProjectRoot\backend\core\trainer.py";           remote="$PiDir/backend/core/trainer.py";           desc="backend/core/trainer.py" },
    @{ local="$ProjectRoot\backend\core\__init__.py";          remote="$PiDir/backend/core/__init__.py";          desc="backend/core/__init__.py" },
    @{ local="$ProjectRoot\backend\__init__.py";               remote="$PiDir/backend/__init__.py";               desc="backend/__init__.py"; optional=$true },

    # Root config files
    @{ local="$ProjectRoot\gunicorn.conf.py";                  remote="$PiDir/gunicorn.conf.py";                  desc="gunicorn.conf.py" },
    @{ local="$ProjectRoot\alembic.ini";                       remote="$PiDir/alembic.ini";                       desc="alembic.ini" },
    @{ local="$ProjectRoot\.env.example";                      remote="$PiDir/.env.example";                      desc=".env.example" },
    @{ local="$ProjectRoot\camera_test.html";                  remote="$PiDir/camera_test.html";                  desc="camera_test.html" },
    @{ local="$ProjectRoot\launcher.html";                     remote="$PiDir/launcher.html";                     desc="launcher.html" },
    @{ local="$ProjectRoot\start_system.sh";                   remote="$PiDir/start_system.sh";                   desc="start_system.sh" },

    # Scripts
    @{ local="$ProjectRoot\scripts\start.sh";                  remote="$PiDir/scripts/start.sh";                  desc="scripts/start.sh" },
    @{ local="$ProjectRoot\scripts\setup_rpi.sh";              remote="$PiDir/scripts/setup_rpi.sh";              desc="scripts/setup_rpi.sh" },
    @{ local="$ProjectRoot\scripts\coffee-sorter.service";     remote="$PiDir/scripts/coffee-sorter.service";     desc="scripts/coffee-sorter.service"; optional=$true }
)

# Directories to sync recursively
$syncDirs = @(
    @{ local="$ProjectRoot\frontend\src";            remote="$PiDir/frontend/src";      desc="frontend/src/" },
    @{ local="$ProjectRoot\frontend\public";         remote="$PiDir/frontend/";         desc="frontend/public/"; optional=$true },
    @{ local="$ProjectRoot\migrations";              remote="$PiDir/migrations";        desc="migrations/" }
)

# Sync individual frontend config files
$frontendFiles = @(
    @{ local="$ProjectRoot\frontend\package.json";       remote="$PiDir/frontend/package.json";       desc="frontend/package.json" },
    @{ local="$ProjectRoot\frontend\package-lock.json";  remote="$PiDir/frontend/package-lock.json";  desc="frontend/package-lock.json"; optional=$true },
    @{ local="$ProjectRoot\frontend\vite.config.js";     remote="$PiDir/frontend/vite.config.js";     desc="frontend/vite.config.js" },
    @{ local="$ProjectRoot\frontend\index.html";         remote="$PiDir/frontend/index.html";         desc="frontend/index.html" },
    @{ local="$ProjectRoot\frontend\.env.production";    remote="$PiDir/frontend/.env.production";    desc="frontend/.env.production" },
    @{ local="$ProjectRoot\frontend\.env.development";   remote="$PiDir/frontend/.env.development";   desc="frontend/.env.development" }
)

$totalFiles = $syncItems.Count + $frontendFiles.Count
$current = 0
$errors = 0

# Sync individual files
foreach ($item in ($syncItems + $frontendFiles)) {
    $current++
    $pct = [int](($current / $totalFiles) * 100)
    Write-Progress -Activity "Syncing files to Pi" -Status "$($item.desc)" -PercentComplete $pct

    if (-not (Test-Path $item.local)) {
        if ($item.optional) { continue }
        Write-Warn "Missing: $($item.desc) — skipping"
        continue
    }

    $result = Copy-ToPi -LocalPath $item.local -RemotePath $item.remote
    if ($result -ne 0) {
        Write-Fail "Failed to copy: $($item.desc)"
        $errors++
    }
}

Write-Progress -Activity "Syncing files to Pi" -Completed

# Sync directories recursively
foreach ($dir in $syncDirs) {
    if (-not (Test-Path $dir.local)) {
        if ($dir.optional) { continue }
        Write-Warn "Missing dir: $($dir.desc) — skipping"
        continue
    }
    Write-Info "Syncing dir: $($dir.desc)"
    $result = Copy-ToPi -LocalPath $dir.local -RemotePath $dir.remote -Recursive
    if ($result -ne 0) {
        Write-Fail "Failed to copy dir: $($dir.desc)"
        $errors++
    }
}

if ($errors -gt 0) {
    Write-Warn "$errors file(s) failed to copy — check SSH connection"
} else {
    Write-Ok "All files synced successfully"
}

# ════════════════════════════════════════════════════════════
# STEP 4 — Fix line endings on all shell scripts (CRLF → LF)
# ════════════════════════════════════════════════════════════
Write-Step 4 "Fixing line endings on shell scripts (CRLF -> LF)"
Invoke-SSH "find $PiDir -name '*.sh' -exec sed -i 's/\r//' {} \; && chmod +x $PiDir/start_system.sh $PiDir/scripts/start.sh $PiDir/scripts/setup_rpi.sh 2>/dev/null; echo done"
Write-Ok "Line endings fixed, scripts are executable"

# ════════════════════════════════════════════════════════════
# STEP 5 — Check if .env exists on Pi (never overwrite it)
# ════════════════════════════════════════════════════════════
Write-Step 5 "Checking .env on Pi"
$envExists = Invoke-SSH "test -f $PiDir/.env && echo yes || echo no"
if ($envExists -match "no") {
    Write-Warn ".env not found on Pi — creating from .env.example"
    Invoke-SSH "cp $PiDir/.env.example $PiDir/.env && PI_IP=\$(hostname -I | awk '{print \$1}') && sed -i \"s|CORS_ORIGINS=.*|CORS_ORIGINS=http://localhost:8000,http://\${PI_IP}:8000|\" $PiDir/.env"
    Write-Ok ".env created on Pi (edit it if needed: nano $PiDir/.env)"
} else {
    Write-Ok ".env already exists on Pi — not overwritten"
}

# ════════════════════════════════════════════════════════════
# STEP 6 — Install / update Python dependencies
# ════════════════════════════════════════════════════════════
Write-Step 6 "Checking Python virtual environment on Pi"
$venvExists = Invoke-SSH "test -f $PiDir/venv/bin/activate && echo yes || echo no"
if ($venvExists -match "no") {
    Write-Warn "venv not found — run setup_rpi.sh first for full setup:"
    Write-Host "    ssh $SSHTarget 'cd $PiDir && bash scripts/setup_rpi.sh'" -ForegroundColor DarkGray
    Write-Warn "Attempting quick pip install into system Python..."
    Invoke-SSH "cd $PiDir && pip3 install -q -r backend/requirements.txt" -ShowOutput
} else {
    Write-Info "Updating Python dependencies..."
    Invoke-SSH "bash -c 'cd $PiDir && . venv/bin/activate && pip install -q -r backend/requirements.txt'" -ShowOutput
    Write-Ok "Python dependencies up to date"
}

# ════════════════════════════════════════════════════════════
# STEP 7 — Build React frontend on Pi (skip with -SkipBuild)
# ════════════════════════════════════════════════════════════
Write-Step 7 "Building React frontend on Pi"
if ($SkipBuild) {
    Write-Warn "Skipped (--SkipBuild flag set)"
} else {
    Write-Info "Running npm ci && npm run build on Pi (this takes ~2-3 min on RPi 4)..."
    Invoke-SSH "cd $PiDir/frontend && npm ci --silent && npm run build" -ShowOutput
    $buildCheck = Invoke-SSH "test -f $PiDir/frontend/dist/index.html && echo ok || echo fail"
    if ($buildCheck -match "ok") {
        Write-Ok "Frontend built successfully"
    } else {
        Write-Fail "Frontend build failed — check output above"
    }
}

# ════════════════════════════════════════════════════════════
# STEP 8 — Run DB migrations
# ════════════════════════════════════════════════════════════
Write-Step 8 "Running database migrations"
$alembicCmd = "bash -c 'cd $PiDir && if [ -f venv/bin/activate ]; then . venv/bin/activate; fi && alembic upgrade head 2>&1'"
Invoke-SSH $alembicCmd -ShowOutput
Write-Ok "Migrations applied"

# ════════════════════════════════════════════════════════════
# STEP 9 — Restart the service (skip with -SkipRestart)
# ════════════════════════════════════════════════════════════
Write-Step 9 "Restarting coffee-sorter service on Pi"
if ($SkipRestart) {
    Write-Warn "Skipped (--SkipRestart flag set)"
    Write-Info "To restart manually: ssh $SSHTarget 'sudo systemctl restart coffee-sorter'"
} else {
    $serviceStatus = Invoke-SSH "systemctl is-enabled coffee-sorter 2>/dev/null || echo not-installed"
    if ($serviceStatus -match "enabled|disabled") {
        Invoke-SSH "sudo systemctl restart coffee-sorter" -ShowOutput
        Start-Sleep -Seconds 3
        $running = Invoke-SSH "systemctl is-active coffee-sorter"
        if ($running -match "active") {
            Write-Ok "Service restarted and running"
        } else {
            Write-Warn "Service may not be running. Check: ssh $SSHTarget 'sudo journalctl -u coffee-sorter -n 30'"
        }
    } else {
        Write-Warn "Systemd service not installed — starting server only (no browser) via SSH"
        Write-Info "To install service: ssh $SSHTarget 'cd $PiDir && bash scripts/setup_rpi.sh'"
        # Kill existing process and start server in background (no browser — SSH has no display)
        Invoke-SSH "bash -c 'pkill -f uvicorn 2>/dev/null; pkill -f gunicorn 2>/dev/null; sleep 1; cd $PiDir; if [ -f venv/bin/activate ]; then . venv/bin/activate; fi; nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > logs/server.log 2>&1 &'"
        Write-Ok "Server started in background — open http://$piIP`:8000/launcher on the Pi screen"
    }
}

# ════════════════════════════════════════════════════════════
# STEP 10 — Health check
# ════════════════════════════════════════════════════════════
Write-Step 10 "Health check"
Start-Sleep -Seconds 3
$health = Invoke-SSH "curl -s --max-time 5 http://localhost:8000/health 2>/dev/null || echo 'not_ready'"
if ($health -match '"status":"ok"' -or $health -match '"status": "ok"') {
    Write-Ok "System is healthy and responding"
} else {
    Write-Warn "Health check inconclusive — server may still be starting"
    Write-Info "Check status: ssh $SSHTarget 'curl http://localhost:8000/health'"
}

# ── Get Pi IP for browser link ───────────────────────────────
$piIP = Invoke-SSH "hostname -I | awk '{print `$1}'"
$piIP = $piIP.Trim()

# ════════════════════════════════════════════════════════════
# DONE
# ════════════════════════════════════════════════════════════
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor DarkGreen
Write-Host "   Sync complete!" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor DarkGreen
Write-Host ""
Write-Host "   Dashboard  : http://$piIP`:8000" -ForegroundColor Cyan
Write-Host "   Launcher   : http://$piIP`:8000/launcher" -ForegroundColor Cyan
Write-Host "   Health     : http://$piIP`:8000/health" -ForegroundColor Cyan
Write-Host "   Logs       : ssh $SSHTarget 'tail -f $PiDir/logs/server.log'" -ForegroundColor DarkGray
Write-Host ""
Write-Host "   Service commands on Pi:" -ForegroundColor DarkGray
Write-Host "     sudo systemctl status  coffee-sorter" -ForegroundColor DarkGray
Write-Host "     sudo systemctl restart coffee-sorter" -ForegroundColor DarkGray
Write-Host "     sudo journalctl -u coffee-sorter -f" -ForegroundColor DarkGray
Write-Host ""
