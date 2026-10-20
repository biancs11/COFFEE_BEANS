#!/bin/bash
# ============================================================
#  pull_and_restart.sh
#  Run this on the Pi to pull latest changes from GitHub
#  and restart the server automatically.
#
#  Usage:
#    bash ~/COFFEE_BEANS/scripts/pull_and_restart.sh
#
#  Or from your Windows PC via SSH:
#    ssh coffeebean@192.168.1.84 "bash ~/COFFEE_BEANS/scripts/pull_and_restart.sh"
# ============================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

echo ""
echo " ============================================"
echo "   Pull latest changes from GitHub"
echo " ============================================"
echo ""

# ── Git pull ─────────────────────────────────────────────────
echo " [1/4] Pulling latest changes..."
git pull origin main
if [ $? -ne 0 ]; then
    echo " [!] Git pull failed. Check your internet connection."
    exit 1
fi
echo " OK - Code updated."
echo ""

# ── Activate venv ────────────────────────────────────────────
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    . "$PROJECT_DIR/venv/bin/activate"
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# ── Install any new Python dependencies ──────────────────────
echo " [2/4] Updating Python dependencies..."
$PYTHON_CMD -m pip install -q -r "$PROJECT_DIR/backend/requirements.txt"
echo " OK"
echo ""

# ── Rebuild frontend if src changed ──────────────────────────
echo " [3/4] Rebuilding frontend..."
cd "$PROJECT_DIR/frontend"
npm ci --silent && npm run build
if [ $? -ne 0 ]; then
    echo " [!] Frontend build failed."
    exit 1
fi
echo " OK - Frontend rebuilt."
echo ""
cd "$PROJECT_DIR"

# ── Restart service or server ────────────────────────────────
echo " [4/4] Restarting server..."
if systemctl is-enabled coffee-sorter > /dev/null 2>&1; then
    sudo systemctl restart coffee-sorter
    sleep 2
    if systemctl is-active --quiet coffee-sorter; then
        echo " OK - Service restarted."
    else
        echo " [!] Service failed to restart. Check: sudo journalctl -u coffee-sorter -n 30"
    fi
else
    pkill -f "uvicorn backend.main" 2>/dev/null
    pkill -f "gunicorn" 2>/dev/null
    sleep 1
    nohup $PYTHON_CMD -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
        > "$PROJECT_DIR/logs/server.log" 2>&1 &
    echo " OK - Server restarted (PID: $!)"
fi

echo ""
echo " ============================================"
echo "   Update complete!"
echo "   http://localhost:8000/launcher"
echo " ============================================"
echo ""
