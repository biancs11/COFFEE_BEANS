#!/bin/bash
# ============================================================
#  pull_and_restart.sh
#  Offline-first update + restart script for the Pi.
#
#  Modes:
#    Default (offline): restart server only — no git pull, no npm.
#    --sync  : also syncs files from Windows via sync_to_pi.ps1
#    --online: git pull from GitHub + pip install + npm rebuild
#
#  Usage on Pi terminal:
#    bash ~/COFFEE_BEANS/scripts/pull_and_restart.sh
#
#  Usage from Windows PC via SSH (offline sync):
#    ssh coffeebean@192.168.1.84 "bash ~/COFFEE_BEANS/scripts/pull_and_restart.sh"
#
#  Usage from Windows PC via SSH (online update):
#    ssh coffeebean@192.168.1.84 "bash ~/COFFEE_BEANS/scripts/pull_and_restart.sh --online"
# ============================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

# ── Parse flags ──────────────────────────────────────────────
MODE="offline"
for arg in "$@"; do
    case "$arg" in
        --online) MODE="online" ;;
        --sync)   MODE="sync"   ;;
    esac
done

echo ""
echo " ============================================"
echo "   Coffee Bean Sorting System - Update"
echo "   Mode: $MODE"
echo " ============================================"
echo ""

# ── Activate venv ────────────────────────────────────────────
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    . "$PROJECT_DIR/venv/bin/activate"
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# ── ONLINE MODE: git pull + pip install + npm rebuild ────────
if [ "$MODE" = "online" ]; then
    echo " [1/4] Pulling latest changes from GitHub..."
    if ! git pull origin main; then
        echo " [!] Git pull failed. Check internet connection."
        echo "     Continuing with restart only..."
    else
        echo " OK - Code updated."
    fi
    echo ""

    echo " [2/4] Updating Python dependencies..."
    $PYTHON_CMD -m pip install -q -r "$PROJECT_DIR/backend/requirements.txt" && echo " OK" || echo " [!] pip install failed - continuing"
    echo ""

    echo " [3/4] Rebuilding frontend..."
    cd "$PROJECT_DIR/frontend"
    if npm ci --silent && npm run build; then
        echo " OK - Frontend rebuilt."
    else
        echo " [!] Frontend build failed — using existing dist."
    fi
    cd "$PROJECT_DIR"

# ── OFFLINE MODE: just restart ───────────────────────────────
else
    echo " [1/4] Skipping git pull (offline mode)"
    echo " [2/4] Skipping pip install (offline mode)"

    # Only rebuild frontend if dist is missing or corrupted
    if [ ! -f "$PROJECT_DIR/frontend/dist/index.html" ]; then
        echo " [3/4] Frontend dist missing — rebuilding..."
        if command -v npm > /dev/null 2>&1; then
            cd "$PROJECT_DIR/frontend"
            npm ci --silent && npm run build && echo " OK - Frontend built." || echo " [!] Build failed."
            cd "$PROJECT_DIR"
        else
            echo " [!] npm not found and dist is missing. Cannot serve frontend."
        fi
    else
        echo " [3/4] Frontend dist OK — skipping rebuild."
    fi
fi

echo ""

# ── Restart service or server ────────────────────────────────
echo " [4/4] Restarting server..."
if systemctl is-enabled coffee-sorter > /dev/null 2>&1; then
    sudo systemctl restart coffee-sorter
    sleep 2
    if systemctl is-active --quiet coffee-sorter; then
        echo " OK - Service restarted."
    else
        echo " [!] Service failed to restart."
        echo "     Check: sudo journalctl -u coffee-sorter -n 30"
    fi
else
    pkill -f "uvicorn backend.main" 2>/dev/null
    pkill -f "gunicorn" 2>/dev/null
    sleep 1
    mkdir -p "$PROJECT_DIR/logs"
    nohup $PYTHON_CMD -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
        > "$PROJECT_DIR/logs/server.log" 2>&1 &
    echo " OK - Server started (PID: $!)"
fi

echo ""
echo " ============================================"
echo "   Done! System is running."
echo "   http://localhost:8000/launcher"
echo " ============================================"
echo ""
